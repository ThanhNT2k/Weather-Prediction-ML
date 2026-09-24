"""Checks for cleaning integrity, interpolation and reproducible identity."""

import csv
import hashlib
import io
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from src.preprocessing import cleaning as cleaner


def row(hour, temperature=20):
    return {"timestamp": f"2023-01-01T{hour:02}:00:00Z", "city": "Hanoi",
            "latitude": cleaner.LATITUDE, "longitude": cleaner.LONGITUDE,
            "T2M": temperature, "PRECTOTCORR": 0, "RH2M": 70,
            "PS": 101, "WS2M": 2, "WD2M": 350, "ALLSKY_SFC_SW_DWN": 100}


def write_input(directory, rows):
    path = Path(directory) / "raw.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


class CleaningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        audit_class = cleaner.DataAudit
        patcher = patch.object(cleaner, "DataAudit", side_effect=lambda stage, config, code, log_dir:
                               audit_class(stage, config, code, temporary.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_interpolation_edges_and_circular_wind(self):
        self.assertEqual(cleaner.fill_series([None, 10, None, 20, None]), [10, 10, 15, 20, 20])
        self.assertEqual(cleaner.fill_series([350, None, 10], circular=True), [350, 0, 10])
        with self.assertRaises(ValueError):
            cleaner.fill_series([None, None])

    def test_fill_values_nonfinite_and_physical_bounds(self):
        for value, parameter in [(-999, "T2M"), ("NaN", "PS"), ("inf", "WS2M"),
                                 (-1, "PRECTOTCORR"), (101, "RH2M"), (361, "WD2M"),
                                 (0, "PS"), ("", "T2M")]:
            with self.subTest(value=value, parameter=parameter):
                self.assertIsNone(cleaner.numeric_value(value, parameter, {-999}))
        self.assertEqual(cleaner.numeric_value(360, "WD2M", {-999}), 0)
        self.assertEqual(cleaner.numeric_value(-5, "T2M", {-999}), -5)

    def test_dedup_gap_lineage_and_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_input(directory, [row(2, 30), row(0, 10), row(0, 10)])
            original = source.read_bytes()
            path, report = cleaner.clean(source, Path(directory) / "processed", min_rows=2)
            rows = list(csv.DictReader(io.StringIO(path.read_text())))
            self.assertEqual([float(r["T2M"]) for r in rows], [10, 20, 30])
            self.assertEqual(rows[0]["source_row_numbers"], "2|3")
            self.assertEqual(rows[1]["is_inserted_hour"], "1")
            self.assertEqual(rows[1]["is_imputed"], "1")
            self.assertEqual(report["duplicates_removed"], 1)
            self.assertEqual(report["inserted_hours"], 1)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(report["dataset_id"], "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
            second_path, second_report = cleaner.clean(source, Path(directory) / "processed", min_rows=2)
            self.assertEqual(report["dataset_id"], second_report["dataset_id"])
            self.assertEqual(path, second_path)

    def test_record_identity_survives_reordering_and_value_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_input(directory, [row(0), row(1)])
            path, _ = cleaner.clean(source, Path(directory) / "processed", min_rows=2)
            before = list(csv.DictReader(io.StringIO(path.read_text())))
            write_input(directory, [row(1, 25), row(0, 30)])
            path, _ = cleaner.clean(source, Path(directory) / "processed", min_rows=2)
            after = list(csv.DictReader(io.StringIO(path.read_text())))
            self.assertEqual([r["record_id"] for r in before], [r["record_id"] for r in after])
            self.assertNotEqual(before[0]["T2M"], after[0]["T2M"])

    def test_conflicting_duplicates_fail_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_input(directory, [row(0), row(0, 30)])
            output = Path(directory) / "processed"
            with self.assertRaisesRegex(ValueError, "Conflicting duplicate"):
                cleaner.clean(source, output, min_rows=1)
            self.assertFalse(output.exists())

    def test_missing_hours_cannot_inflate_minimum_observed_row_count(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_input(directory, [row(0), row(23)])
            with self.assertRaisesRegex(ValueError, "unique observed rows"):
                cleaner.clean(source, Path(directory) / "processed", min_rows=10)

    def test_timezone_normalization_and_naive_rejection(self):
        self.assertEqual(cleaner.record_id("2023-01-01T07:00:00+07:00"),
                         cleaner.record_id("2023-01-01T00:00:00Z"))
        self.assertEqual(cleaner.normalize_timestamp("2023-01-01T07:00:00+07:00"),
                         cleaner.normalize_timestamp("2023-01-01T00:00:00Z"))
        for stamp in ("2023-01-01T00:00:00", "2023-01-01T00:30:00Z"):
            with self.assertRaises(ValueError):
                cleaner.normalize_timestamp(stamp)

    def test_output_gmt7_rolls_into_next_year_preserving_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            observation = row(23)
            observation["timestamp"] = "2024-12-31T23:00:00Z"
            source = write_input(directory, [observation])
            path, report = cleaner.clean(source, Path(directory) / "processed", min_rows=1)
            result = list(csv.DictReader(io.StringIO(path.read_text())))[0]
            self.assertEqual(result["timestamp"], "2025-01-01T06:00:00+07:00")
            self.assertEqual(result["record_id"], cleaner.record_id(observation["timestamp"]))
            self.assertEqual(report["time_standard"], "UTC+07:00")
            self.assertEqual(report["timezone"], "Asia/Ho_Chi_Minh")
            self.assertEqual(report["start"], result["timestamp"])
            self.assertEqual(report["end"], result["timestamp"])

    def test_entire_missing_column_and_wrong_station_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            source = write_input(directory, [row(0, -999), row(1, -999)])
            with self.assertRaisesRegex(ValueError, "T2M"):
                cleaner.clean(source, Path(directory) / "processed", min_rows=2)
            invalid = row(0)
            invalid["city"] = "Danang"
            source = write_input(directory, [invalid])
            with self.assertRaisesRegex(ValueError, "Hanoi"):
                cleaner.clean(source, Path(directory) / "processed", min_rows=1)


if __name__ == "__main__":
    unittest.main()
