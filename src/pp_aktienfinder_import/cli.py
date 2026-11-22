import argparse
import asyncio
import json
import sys
import logging
from pathlib import Path

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider
from mcp.client.streamable_http import (
    create_mcp_http_client,
    streamable_http_client,
)
from mcp.shared.auth import OAuthClientMetadata

from .config import load_config
from .oauth import MemoryTokenStorage, open_browser, receive_authorization_code
from .resolver import resolve_wkns
from .taxonomy import (
    breakdown_document,
    hierarchical_country_document,
    holdings_document,
)


MCP_URL = "https://aktienfinder.net/mcp"
REDACTED_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "token",
    "password",
    "secret",
    "cookie",
    "set-cookie",
}


def configure_communication_log(path: Path) -> logging.Logger:
    logger = logging.getLogger("aktienfinder-mcp")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if str(key).lower() in REDACTED_KEYS
            else redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact(child) for child in value]
    return value


def log_json(logger: logging.Logger, event: str, payload) -> None:
    logger.info(
        "%s %s",
        event,
        json.dumps(redact(payload), ensure_ascii=False, sort_keys=True),
    )


def call_result_payload(result) -> dict:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured

    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    if not parts:
        raise RuntimeError("The MCP tool returned no readable payload")

    try:
        return json.loads("\n".join(parts))
    except json.JSONDecodeError as exc:
        raise RuntimeError("The MCP tool returned data that was not valid JSON") from exc


async def fetch_data(config: dict) -> dict:
    log_path = Path("aktienfinder-live.log")
    communication_log = configure_communication_log(log_path)
    log_json(
        communication_log,
        "MCP_START",
        {
            "server": MCP_URL,
            "identifiers": [item["identifier"] for item in config["securities"]],
            "transport": "streamable-http",
        },
    )
    storage = MemoryTokenStorage()
    metadata = OAuthClientMetadata(
        redirect_uris=["http://127.0.0.1:8765/callback"],
        scope="mcp offline_access",
        client_name="Portfolio Performance Aktienfinder Import",
        grant_types=["authorization_code", "refresh_token"],
        token_endpoint_auth_method="none",
        application_type="native",
    )
    auth = OAuthClientProvider(
        server_url=MCP_URL,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=open_browser,
        callback_handler=receive_authorization_code,
    )

    securities, resolution_errors = resolve_wkns(
        config["securities"],
        config.get("portfolioXml"),
    )
    if resolution_errors:
        raise ValueError("\n".join(resolution_errors))

    identifiers = [item["identifier"] for item in securities]
    result: dict[str, dict] = {
        "breakdowns": {},
        "holdings": {},
    }
    taxonomy_options = config.get("taxonomy", {})

    async with create_mcp_http_client(auth=auth) as http_client:
        async with streamable_http_client(
            MCP_URL,
            http_client=http_client,
        ) as streams:
            read_stream, write_stream = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                log_json(communication_log, "MCP_INITIALIZED", {"ok": True})

                for dimension, enabled in (
                    ("Country", taxonomy_options.get("country", True)),
                    ("Region", taxonomy_options.get("region", True)),
                    ("Sector", taxonomy_options.get("sector", True)),
                    ("Industry", taxonomy_options.get("industry", False)),
                ):
                    if enabled:
                        request_arguments = {
                            "namesOrIsins": identifiers,
                            "dimension": dimension,
                        }
                        log_json(
                            communication_log,
                            "MCP_TOOL_REQUEST get_etf_breakdown",
                            request_arguments,
                        )
                        response = await session.call_tool(
                            "get_etf_breakdown",
                            request_arguments,
                        )
                        if response.is_error:
                            log_json(
                                communication_log,
                                "MCP_TOOL_ERROR get_etf_breakdown",
                                {"dimension": dimension, "isError": True},
                            )
                            raise RuntimeError(
                                f"get_etf_breakdown({dimension}) failed"
                            )
                        payload = call_result_payload(response)
                        log_json(
                            communication_log,
                            "MCP_TOOL_RESPONSE get_etf_breakdown",
                            payload,
                        )
                        result["breakdowns"][dimension] = payload

                if taxonomy_options.get("holdings", True):
                    top_holdings = int(taxonomy_options.get("topHoldings", 10))
                    if top_holdings < 1 or top_holdings > 100:
                        raise ValueError("topHoldings must be between 1 and 100")

                    for start in range(0, len(identifiers), 3):
                        block = identifiers[start : start + 3]
                        offset = 0
                        while True:
                            response = await session.call_tool(
                                "get_etf_holdings",
                                {
                                    "namesOrIsins": block,
                                    "offset": offset,
                                },
                            )
                            if response.is_error:
                                log_json(
                                    communication_log,
                                    "MCP_TOOL_ERROR get_etf_holdings",
                                    {"isError": True, "offset": offset},
                                )
                                raise RuntimeError("get_etf_holdings failed")
                            page = call_result_payload(response)
                            log_json(
                                communication_log,
                                "MCP_TOOL_RESPONSE get_etf_holdings",
                                page,
                            )
                            for item in page.get("Items", []):
                                key = item.get("Isin") or item.get("Name")
                                existing = result["holdings"].setdefault(
                                    key,
                                    {
                                        "Isin": item.get("Isin"),
                                        "Name": item.get("Name"),
                                        "Holdings": [],
                                    },
                                )
                                existing["Holdings"].extend(item.get("Holdings", [])[:top_holdings])

                            if not page.get("Truncated"):
                                break
                            offset = page.get("NextOffset")
                            if offset is None:
                                raise RuntimeError(
                                    "The holdings response is truncated but has no NextOffset"
                                )

    return result


def build_documents(
    config: dict,
    fetched: dict,
) -> list[tuple[str, dict]]:
    documents: list[tuple[str, dict]] = []

    for dimension, payload in fetched["breakdowns"].items():
        name = {
            "Country": "Country",
            "Region": "Region",
            "Sector": "Sector",
            "Industry": "Industry",
        }[dimension]

        for item in payload.get("Items", []):
            isin = str(item.get("Isin", "")).strip()
            etf_name = str(item.get("Name", "")).strip()
            if not isin:
                continue
            identifiers = {"isin": isin}
            if etf_name:
                identifiers["name"] = etf_name

            documents.append(
                (
                    f"{name.lower()}-{isin}.json",
                    hierarchical_country_document(
                        item.get("Items", []),
                        identifiers,
                    )
                    if dimension == "Country"
                    else breakdown_document(
                        name,
                        dimension,
                        item.get("Items", []),
                        identifiers,
                    ),
                )
            )

    top_holdings = int(config.get("taxonomy", {}).get("topHoldings", 10))
    for isin, item in fetched["holdings"].items():
        isin_value = str(isin).strip()
        name = str(item.get("Name", "")).strip()
        identifiers = {"isin": isin_value} if isin_value else {}
        if name:
            identifiers["name"] = name
        holdings = sorted(
            item["Holdings"],
            key=lambda value: float(value.get("WeightPercent", 0)),
            reverse=True,
        )[:top_holdings]
        if holdings:
            documents.append(
                (
                    f"holding-{isin_value or name}.json",
                    holdings_document("Holding", holdings, identifiers),
                )
            )

    return documents


def write_documents(documents: list[tuple[str, dict]], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for filename, document in documents:
        safe_name = "".join(
            character
            if character.isascii() and (character.isalnum() or character in "-_.")
            else "-"
            for character in filename
        )
        path = output / safe_name
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {path}")


def preview_documents(documents: list[tuple[str, dict]]) -> None:
    for filename, document in documents:
        print(f"\n{filename}")
        print(json.dumps(document, ensure_ascii=False, indent=2))


def combine_documents(documents: list[tuple[str, dict]]) -> dict:
    combined: dict[str, dict] = {}

    for _filename, document in documents:
        taxonomy_name = document["name"]

        if taxonomy_name == "Country":
            is_hierarchical = any(
                "children" in category
                for category in document.get("categories", [])
            )
            if not is_hierarchical:
                category_names = {
                    category["key"]: category["name"]
                    for category in document.get("categories", [])
                }
                country_instruments = []
                country_categories = {}
                for instrument in document.get("instruments", []):
                    items = [
                        {
                            "Name": category_names[assignment["key"]],
                            "WeightPercent": assignment["weight"],
                        }
                        for assignment in instrument.get("categories", [])
                    ]
                    hierarchy = hierarchical_country_document(
                        items,
                        instrument["identifiers"],
                    )
                    country_instruments.extend(hierarchy["instruments"])
                    for category in hierarchy["categories"]:
                        existing = country_categories.setdefault(category["key"], category)
                        if existing is not category:
                            existing_children = {
                                child["key"]: child
                                for child in existing["children"]
                            }
                            for child in category["children"]:
                                existing_children.setdefault(child["key"], child)
                            existing["children"] = list(existing_children.values())
                document = {
                    "name": "Country",
                    "categories": list(country_categories.values()),
                    "instruments": country_instruments,
                }

        taxonomy = combined.setdefault(
            taxonomy_name,
            {
                "name": taxonomy_name,
                "categories": [],
                "instruments": [],
            },
        )

        categories_by_key = {category["key"]: category for category in taxonomy["categories"]}
        for category in document.get("categories", []):
            existing = categories_by_key.setdefault(category["key"], category)
            if existing is not category and "children" in existing:
                existing_children = {
                    child["key"]: child
                    for child in existing["children"]
                }
                for child in category.get("children", []):
                    existing_children.setdefault(child["key"], child)
                existing["children"] = list(existing_children.values())
        taxonomy["categories"] = list(categories_by_key.values())

        instrument_by_isin = {
            instrument["identifiers"].get("isin"): instrument
            for instrument in taxonomy["instruments"]
            if instrument.get("identifiers", {}).get("isin")
        }
        for instrument in document.get("instruments", []):
            isin = instrument["identifiers"].get("isin")
            existing = instrument_by_isin.get(isin)
            if existing is None:
                taxonomy["instruments"].append(instrument)
                instrument_by_isin[isin] = instrument
            else:
                existing_categories = {
                    assignment["key"]: assignment
                    for assignment in existing["categories"]
                }
                for assignment in instrument["categories"]:
                    existing_categories.setdefault(
                        assignment["key"],
                        assignment,
                    )
                existing["categories"] = list(existing_categories.values())

    return combined


def write_combined_document(
    documents: list[tuple[str, dict]],
    output: Path,
    filename: str = "pp-taxonomies.json",
) -> Path:
    combined = combine_documents(documents)
    output.mkdir(parents=True, exist_ok=True)
    path = output / filename
    path.write_text(
        json.dumps(list(combined.values()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote combined taxonomy file {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create Portfolio Performance taxonomy JSON from aktienfinder.net"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("example-securities.json"),
        help="JSON file containing ISIN/NAME entries and taxonomy options",
    )
    parser.add_argument(
        "--portfolio-xml",
        type=Path,
        help="Optional classic PP XML file used to resolve WKN entries",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory for PP taxonomy JSON files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and print the data plan without authentication",
    )
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--preview",
        action="store_true",
        help="Print generated taxonomy JSON after fetching",
    )
    output_mode.add_argument(
        "--single-file",
        action="store_true",
        help="Write all taxonomies into one pp-taxonomies.json import file",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        config = load_config(args.config)
        if args.portfolio_xml:
            config["portfolioXml"] = str(args.portfolio_xml)

        securities, resolution_errors = resolve_wkns(
            config["securities"],
            config.get("portfolioXml"),
        )
        if resolution_errors:
            raise ValueError("\n".join(resolution_errors))

        print(f"Validated {len(securities)} security entries")
        for item in securities:
            source = item.get("sourceIdentifier")
            print(
                f"- {source or item['identifier']} "
                f"({item['identifierType']}: {item['identifier']})"
            )

        if args.dry_run:
            print("Dry run completed. No browser login was opened.")
            return 0

        fetched = asyncio.run(fetch_data(config))
        documents = build_documents(config, fetched)
        if not documents:
            print("No taxonomy documents were generated.")
            return 0

        if args.preview:
            preview_documents(documents)
        elif args.single_file:
            write_combined_document(documents, args.output)
        else:
            write_documents(documents, args.output)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
