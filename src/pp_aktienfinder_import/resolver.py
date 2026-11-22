import xml.etree.ElementTree as ET
from pathlib import Path


def resolve_wkns(
    securities: list[dict],
    portfolio_xml: str | Path | None,
) -> tuple[list[dict], list[str]]:
    resolved: list[dict] = []
    errors: list[str] = []

    wkn_map: dict[str, str] = {}
    if portfolio_xml:
        path = Path(portfolio_xml)
        if not path.is_file():
            errors.append(f"Portfolio XML not found: {path}")
        else:
            root = ET.parse(path).getroot()
            for element in root.iter():
                wkn = element.attrib.get("wkn") or element.attrib.get("WKN")
                isin = element.attrib.get("isin") or element.attrib.get("ISIN")
                if wkn and isin:
                    wkn_map[wkn.strip().upper()] = isin.strip().upper()

                for child in element:
                    tag = child.tag.rsplit("}", 1)[-1].lower()
                    if tag in {"wkn", "isin"}:
                        continue

    for item in securities:
        identifier = item["identifier"].strip()
        kind = item["identifierType"]

        if kind == "WKN":
            isin = wkn_map.get(identifier.upper())
            if not isin:
                errors.append(
                    f"{identifier}: WKN could not be resolved. "
                    "Add 'portfolioXml' or change the entry to identifierType 'ISIN'."
                )
                continue
            resolved.append(
                {
                    "identifier": isin,
                    "identifierType": "ISIN",
                    "sourceIdentifier": identifier,
                    "sourceIdentifierType": "WKN",
                }
            )
        elif kind in {"ISIN", "NAME"}:
            resolved.append(dict(item))
        else:
            errors.append(f"{identifier}: unsupported identifier type '{kind}'")

    return resolved, errors
