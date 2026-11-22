import json
from pathlib import Path


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    securities = data.get("securities")
    if not isinstance(securities, list) or not securities:
        raise ValueError("The configuration must contain a non-empty 'securities' list")

    for item in securities:
        if not isinstance(item, dict):
            raise ValueError("Each security entry must be an object")
        identifier = item.get("identifier")
        identifier_type = item.get("identifierType")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("A security entry needs a non-empty 'identifier'")
        if identifier_type not in {"ISIN", "WKN", "NAME"}:
            raise ValueError(
                f"Unsupported identifierType '{identifier_type}'. "
                "Use ISIN, WKN, or NAME."
            )

    return data
