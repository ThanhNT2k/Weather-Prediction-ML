"""Offline regression tests for acquisition integrity and resumable downloads."""

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from src.data_collection import nasa_power as nasa


def payload(start, end):
    return {
        "header": {"time_standard": "UTC", "fill_value": -999.0},
        "geometry": {"coordinates": [nasa.LONGITUDE, nasa.LATITUDE, 10]},
        "parameters": {key: {"units": "test"} for key in nasa.PARAMETERS},
        "properties": {"parameter": {
            key: {hour: 1.0 for hour in nasa.hour_keys(start, end)}
            for key in nasa.PARAMETERS
        }},
    }


class CollectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        audit_class = nasa.DataAudit
        patcher = patch.object(nasa, "DataAudit", side_effect=lambda stage, config, code, log_dir:
                               audit_class(stage, config, code, temporary.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_month_boundaries_include_leap_day(self):
        ranges = list(nasa.month_ranges(date(2024, 1, 31), date(2024, 3, 1)))
        self.assertEqual(ranges, [
            (date(2024, 1, 31), date(2024, 1, 31)),
            (date(2024, 2, 1), date(2024, 2, 29)),
            (date(2024, 3, 1), date(2024, 3, 1)),
        ])

    def test_rejects_incomplete_hours_wrong_timezone_and_missing_parameter(self):
        day = date(2023, 1, 1)
        for defect in ("hour", "timezone", "parameter"):
            with self.subTest(defect=defect):
                data = payload(day, day)
                if defect == "hour":
                    del data["properties"]["parameter"]["T2M"]["2023010100"]
                elif defect == "timezone":
                    data["header"]["time_standard"] = "LST"
                else:
                    del data["properties"]["parameter"]["PS"]
                with self.assertRaises(ValueError):
                    nasa.validate_payload(data, day, day)

    def test_raw_fill_values_preserved_and_cache_reused(self):
        day = date(2023, 1, 1)
        data = payload(day, day)
        data["properties"]["parameter"]["T2M"]["2023010100"] = -999.0
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(nasa, "fetch_json", return_value=data) as fetch:
                csv_path, report = nasa.collect(day, day, directory)
                self.assertEqual(report["row_count"], 24)
                self.assertEqual(report["missing_values"]["T2M"], 1)
                self.assertIn("-999.0", csv_path.read_text())
                self.assertIn("2023-01-01T00:00:00Z", csv_path.read_text())
                self.assertFalse(report["meets_raw_10000_rows"])
                nasa.collect(day, day, directory)
                fetch.assert_called_once()
                original_files = {p: p.read_bytes() for p in Path(directory).rglob('*') if p.is_file()}
                snapshot_path, _ = nasa.collect(day, day, directory, refresh=True)
                self.assertIn("snapshots", snapshot_path.parts)
                self.assertTrue(snapshot_path.is_file())
                for original, content in original_files.items():
                    self.assertEqual(original.read_bytes(), content)
                self.assertEqual(fetch.call_count, 2)
            metadata = next(Path(directory).glob("*.metadata.json"))
            self.assertEqual(json.loads(metadata.read_text())["duplicate_rows"], 0)

    def test_invalid_response_does_not_publish_csv_or_cache(self):
        day = date(2023, 1, 1)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(nasa, "fetch_json", return_value={}):
                with self.assertRaises(ValueError):
                    nasa.collect(day, day, directory)
            self.assertEqual(list(Path(directory).rglob("*.json")), [])
            self.assertEqual(list(Path(directory).glob("*.csv")), [])

    def test_existing_raw_artifact_cannot_be_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw.json"
            nasa.atomic_write(path, '{"T2M": 20}')
            before = path.read_bytes()
            nasa.atomic_write(path, '{"T2M":20}')
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(FileExistsError):
                nasa.atomic_write(path, '{"T2M": 30}')
            self.assertEqual(path.read_bytes(), before)

    def test_bad_date_range_fails_before_network_request(self):
        with patch.object(nasa, "fetch_json") as fetch:
            with self.assertRaises(ValueError):
                nasa.collect(date(2024, 1, 1), date(2023, 1, 1))
            fetch.assert_not_called()

    def test_retry_server_error_but_not_invalid_request(self):
        for code, expected_calls in ((503, 3), (422, 1)):
            with self.subTest(code=code):
                error = HTTPError(nasa.API_URL, code, "test", {}, None)
                with patch.object(nasa, "urlopen", side_effect=error) as request:
                    with patch.object(nasa.time, "sleep"):
                        with self.assertRaises(RuntimeError):
                            nasa.fetch_json(nasa.API_URL, retries=2)
                self.assertEqual(request.call_count, expected_calls)


if __name__ == "__main__":
    unittest.main()
