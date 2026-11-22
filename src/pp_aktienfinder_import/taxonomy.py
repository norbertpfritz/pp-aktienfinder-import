import re
from typing import Iterable


def stable_key(prefix: str, name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{prefix}-{cleaned or 'unknown'}"


def category_document(
    name: str,
    categories: Iterable[tuple[str, str]],
    instruments: Iterable[dict],
) -> dict:
    category_items = []
    for key, label in categories:
        category_items.append({"name": label, "key": key})

    return {
        "name": name,
        "categories": category_items,
        "instruments": list(instruments),
    }


def breakdown_document(
    name: str,
    dimension: str,
    items: list[dict],
    instrument_identifier: dict,
) -> dict:
    categories = []
    assignments = []

    for item in items:
        label = str(item.get("Name", "")).strip()
        weight = item.get("WeightPercent")
        if not label or not isinstance(weight, (int, float)):
            continue

        key = stable_key(dimension.lower(), label)
        categories.append((key, label))
        assignments.append({"key": key, "weight": weight})

    return category_document(
        name,
        categories,
        [{"identifiers": instrument_identifier, "categories": assignments}],
    )


COUNTRY_REGION_MAPPING = {
    "Europa (EUR)": {
        "Deutschland", "Frankreich", "Niederlande", "Spanien", "Italien",
        "Finnland", "Belgien", "Irland", "Luxemburg", "Portugal", "Österreich",
        "Griechenland", "Slowenien", "Slowakei", "Estland", "Lettland",
        "Litauen", "Zypern", "Malta", "Kroatien",
    },
    "Europa (ex EUR)": {
        "Großbritannien", "Schweiz", "Schweden", "Dänemark", "Norwegen",
        "Polen", "Ungarn", "Tschechische Republik", "Rumänien", "Bulgarien",
        "Türkei", "Russland", "Ukraine", "Island",
    },
    "Nordamerika": {
        "USA", "Kanada", "Mexiko", "Bermuda", "Kaimaninseln", "Panama",
    },
    "Asien": {
        "Japan", "Taiwan", "Südkorea", "China", "Indien", "Hong Kong",
        "Singapur", "Malaysia", "Thailand", "Indonesien", "Philippinen",
        "Saudi-Arabien", "Kuwait", "Israel",
    },
    "Südamerika": {
        "Brasilien", "Peru", "Uruguay", "Chile", "Kolumbien", "Argentinien",
        "Ecuador", "Venezuela",
    },
    "Afrika": {
        "Südafrika", "Nigeria", "Kenia", "Ägypten", "Marokko",
    },
    "Australien": {
        "Australien", "Neuseeland",
    },
}


def country_region(name: str) -> str:
    for region, countries in COUNTRY_REGION_MAPPING.items():
        if name in countries:
            return region
    return "Sonstige"


def hierarchical_country_document(
    items: list[dict],
    instrument_identifier: dict,
) -> dict:
    regions: dict[str, list[dict]] = {}
    assignments = []

    for item in items:
        country = str(item.get("Name", "")).strip()
        weight = item.get("WeightPercent")
        if not country or not isinstance(weight, (int, float)):
            continue

        region = country_region(country)
        country_key = stable_key("country", country)
        regions.setdefault(region, []).append(
            {"name": country, "key": country_key}
        )
        assignments.append({"key": country_key, "weight": weight})

    categories = []
    for region, countries in regions.items():
        region_key = stable_key("country", region)
        categories.append(
            {
                "name": region,
                "key": region_key,
                "children": countries,
            }
        )

    return {
        "name": "Country",
        "categories": categories,
        "instruments": [
            {
                "identifiers": instrument_identifier,
                "categories": assignments,
            }
        ],
    }


def holdings_document(
    name: str,
    holdings: list[dict],
    instrument_identifier: dict,
) -> dict:
    categories = []
    assignments = []

    for holding in holdings:
        label = str(holding.get("Name", "")).strip()
        weight = holding.get("WeightPercent")
        isin = str(holding.get("Isin", "")).strip()
        if not label or not isinstance(weight, (int, float)):
            continue

        key = stable_key("holding", isin or label)
        categories.append((key, label))
        assignments.append({"key": key, "weight": weight})

    return category_document(
        name,
        categories,
        [{"identifiers": instrument_identifier, "categories": assignments}],
    )
