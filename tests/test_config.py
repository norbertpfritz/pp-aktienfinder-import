import json
import tempfile
import unittest
from pathlib import Path

from pp_aktienfinder_import.config import load_config
from pp_aktienfinder_import.resolver import resolve_wkns
from pp_aktienfinder_import.taxonomy import breakdown_document
from pp_aktienfinder_import.cli import combine_documents
from pp_aktienfinder_import.taxonomy import hierarchical_country_document


class ConfigTest(unittest.TestCase):
    def test_loads_isins(self) -> None:
        data = {
            "securities": [
                {"identifier": "DE000EWG2LD7", "identifierType": "ISIN"},
                {"identifier": "IE00B4K48X80", "identifierType": "ISIN"},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "securities.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            loaded = load_config(path)

        self.assertEqual(2, len(loaded["securities"]))

    def test_wkn_requires_resolution_source(self) -> None:
        resolved, errors = resolve_wkns(
            [{"identifier": "EWG2LD", "identifierType": "WKN"}],
            None,
        )
        self.assertEqual([], resolved)
        self.assertTrue(errors)

    def test_breakdown_document_has_assignments(self) -> None:
        document = breakdown_document(
            "Country",
            "Country",
            [{"Name": "USA", "WeightPercent": 67.5}],
            {"isin": "IE00B4L5YC18", "name": "Example ETF"},
        )
        self.assertEqual("Country", document["name"])
        self.assertEqual(
            67.5,
            document["instruments"][0]["categories"][0]["weight"],
        )

    def test_combines_taxonomies_by_name(self) -> None:
        first = breakdown_document(
            "Country",
            "Country",
            [{"Name": "USA", "WeightPercent": 70.0}],
            {"isin": "IE00B4X9L533"},
        )
        second = breakdown_document(
            "Country",
            "Country",
            [{"Name": "Deutschland", "WeightPercent": 13.0}],
            {"isin": "IE00B4K48X80"},
        )
        combined = combine_documents([
            ("country-one.json", first),
            ("country-two.json", second),
        ])
        self.assertEqual(["Country"], list(combined))
        self.assertEqual(2, len(combined["Country"]["instruments"]))

    def test_country_document_is_hierarchical(self) -> None:
        document = hierarchical_country_document(
            [
                {"Name": "Deutschland", "WeightPercent": 13.7},
                {"Name": "Frankreich", "WeightPercent": 13.44},
                {"Name": "USA", "WeightPercent": 70.66},
            ],
            {"isin": "IE00B4X9L533"},
        )
        regions = {category["name"]: category for category in document["categories"]}
        self.assertEqual(2, len(regions))
        self.assertIn("Europa (EUR)", regions)
        self.assertIn("Nordamerika", regions)
        self.assertEqual(
            ["Deutschland", "Frankreich"],
            [child["name"] for child in regions["Europa (EUR)"]["children"]],
        )


if __name__ == "__main__":
    unittest.main()
