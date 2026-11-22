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
