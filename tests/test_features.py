"""Forecast alignment, causal features, quality filtering and schema integrity."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.data_collection.nasa_power import LATITUDE, LONGITUDE
from src.preprocessing.cleaning import clean
from src.preprocessing.features import build_features, DERIVED_FEATURES


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.logs = self.root / "logs"
        rows = []
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        for i in range(72):
            rows.append({"timestamp": (start + timedelta(hours=i)).isoformat(), "city": "Hanoi",
                         "latitude": LATITUDE, "longitude": LONGITUDE, "T2M": i,
                         "PRECTOTCORR": 0.1 if i % 2 else 0.2, "RH2M": 70,
                         "PS": 100 + i / 10, "WS2M": 2, "WD2M": 90, "ALLSKY_SFC_SW_DWN": 100})
        raw = self.root / "raw.csv"
        with raw.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        self.source, _ = clean(raw, self.root / "cleaned", min_rows=1, log_dir=self.logs)

    def build(self, horizon=1):
        path, report = build_features(self.source, self.root / "processed", horizon=horizon,
                                      min_rows=1, log_dir=self.logs)
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f)), report

    def change_source(self, callback):
        with self.source.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        callback(rows)
        with self.source.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        metadata_path = self.source.with_suffix(".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["dataset_id"] = "sha256:" + hashlib.sha256(self.source.read_bytes()).hexdigest()
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    def test_alignment_rolling_local_time_and_threshold(self):
        rows, report = self.build()
        self.assertEqual(len(rows), 72 - 24 - 1)
        first = rows[0]
        self.assertEqual(first["timestamp"], "2023-01-02T07:00:00+07:00")
        self.assertEqual(first["target_timestamp"], "2023-01-02T08:00:00+07:00")
        for field, expected in {"hour": 7, "dayofweek": 0, "season": 0, "T2M_lag_1h": 23,
                                "T2M_lag_24h": 0, "T2M_rolling_mean_3h": 23,
                                "T2M_rolling_mean_24h": 12.5, "PS_diff_3h": 0.3,
                                "target_temperature": 25, "rain_flag": 0}.items():
            self.assertAlmostEqual(float(first[field]), expected)
        self.assertEqual(rows[1]["rain_flag"], "1")
        self.assertEqual(len(first), 35)
        self.assertEqual(len(report["feature_columns"]), 21)
        self.assertIn("SUCCEEDED", Path(report["audit_log"]).read_text(encoding="utf-8"))

    def test_future_changes_do_not_change_current_features(self):
        before, _ = self.build()
        def alter(rows):
            for row in rows[25:]:
                row["T2M"] = "99"
        self.change_source(alter)
        after, _ = self.build()
        for key in ["T2M", *DERIVED_FEATURES]:
            self.assertEqual(before[0][key], after[0][key])
        self.assertNotEqual(before[0]["target_temperature"], after[0]["target_temperature"])

    def test_imputed_windows_and_targets_excluded(self):
        def alter(rows):
            rows[30]["is_imputed"] = "1"
            rows[30]["imputed_columns"] = "T2M"
        self.change_source(alter)
        rows, report = self.build()
        self.assertEqual(report["quality_rows_removed"], 26)  # target at 30, then t=30..54
        self.assertEqual(len(rows), 47 - 26)

    def test_custom_horizon(self):
        rows, _ = self.build(horizon=6)
        self.assertEqual(len(rows), 42)
        self.assertEqual(float(rows[0]["target_temperature"]), 30)
        self.assertEqual(rows[0]["target_timestamp"], "2023-01-02T13:00:00+07:00")

    def test_tamper_missing_hours_and_minimum_rows_rejected(self):
        with self.assertRaisesRegex(ValueError, "minimum"):
            build_features(self.source, self.root / "processed", log_dir=self.logs)
        self.source.write_text(self.source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.build()
        self.change_source(lambda rows: rows.pop(30))
        with self.assertRaisesRegex(ValueError, "continuous"):
            self.build()


if __name__ == "__main__":
    unittest.main()
