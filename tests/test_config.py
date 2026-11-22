import json
import tempfile
import unittest
from pathlib import Path

from pp_aktienfinder_import.config import load_config
from pp_aktienfinder_import.resolver import resolve_wkns
from pp_aktienfinder_import.taxonomy import breakdown_document


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


if __name__ == "__main__":
    unittest.main()
