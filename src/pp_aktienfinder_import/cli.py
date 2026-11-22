import argparse
import asyncio
import json
import sys
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
from .taxonomy import breakdown_document, holdings_document


MCP_URL = "https://aktienfinder.net/mcp"


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
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                for dimension, enabled in (
                    ("Country", taxonomy_options.get("country", True)),
                    ("Region", taxonomy_options.get("region", True)),
                    ("Sector", taxonomy_options.get("sector", True)),
                    ("Industry", taxonomy_options.get("industry", False)),
                ):
                    if enabled:
                        response = await session.call_tool(
                            "get_etf_breakdown",
                            {
                                "namesOrIsins": identifiers,
                                "dimension": dimension,
                            },
                        )
                        if response.isError:
                            raise RuntimeError(
                                f"get_etf_breakdown({dimension}) failed"
                            )
                        result["breakdowns"][dimension] = call_result_payload(response)

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
                            if response.isError:
                                raise RuntimeError("get_etf_holdings failed")
                            page = call_result_payload(response)
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
                    breakdown_document(
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
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print generated taxonomy JSON after fetching",
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
        else:
            write_documents(documents, args.output)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
