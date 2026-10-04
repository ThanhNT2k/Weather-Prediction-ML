"""Cleaning: timezone, invalid values, duplicates, gaps, circular wind, outliers kept."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing import cleaning as cleaner


def raw_frame(hours=72, start="2023-01-01T00:00:00Z"):
    times = pd.date_range(start, periods=hours, freq="h")
    return pd.DataFrame({
        "timestamp": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times],
        "city": "Hanoi", "latitude": "21.0285", "longitude": "105.8542",
        "T2M": [str(20 + np.sin(i / 24 * 2 * np.pi)) for i in range(hours)],
        "PRECTOTCORR": "0", "RH2M": "70", "PS": "101", "WS2M": "2", "WD2M": "350",
        "ALLSKY_SFC_SW_DWN": "100",
    })


class CleaningTests(unittest.TestCase):
    def test_utc_converted_to_vietnam_time(self):
        clean, _, _ = cleaner.clean_frame(raw_frame())
        self.assertEqual(str(clean.index[0]), "2023-01-01 07:00:00+07:00")
        self.assertTrue(clean.index.to_series().diff().dropna().eq(pd.Timedelta(hours=1)).all())

    def test_timestamp_without_offset_is_rejected(self):
        raw = raw_frame()
        raw.loc[3, "timestamp"] = "2023-01-01T03:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            cleaner.clean_frame(raw)

    def test_invalid_values_become_nan_then_short_gaps_interpolated(self):
        raw = raw_frame()
        raw.loc[10, "T2M"] = "-999"
        raw.loc[11, "RH2M"] = "130"
        raw.loc[12, "PS"] = "abc"
        clean, report, _ = cleaner.clean_frame(raw)
        self.assertEqual(report["steps"]["invalid_to_nan"]["T2M"], 1)
        self.assertEqual(report["steps"]["invalid_to_nan"]["RH2M"], 1)
        self.assertEqual(report["steps"]["invalid_to_nan"]["PS"], 1)
        before, after = float(raw.loc[9, "T2M"]), float(raw.loc[11, "T2M"])
        self.assertAlmostEqual(clean["T2M"].iloc[10], (before + after) / 2)
        self.assertEqual(clean["is_imputed"].sum(), 3)
        self.assertEqual(clean["imputed_columns"].iloc[11], "RH2M")

    def test_long_gap_stays_missing(self):
        raw = raw_frame()
        raw.loc[20:25, "T2M"] = ""  # 6 hours > MAX_INTERPOLATE_HOURS
        clean, report, _ = cleaner.clean_frame(raw)
        self.assertEqual(clean["T2M"].isna().sum(), 6)
        self.assertEqual(report["steps"]["interpolated_cells"]["T2M"], 0)

    def test_missing_hour_is_inserted_and_flagged(self):
        raw = raw_frame().drop(index=30).reset_index(drop=True)
        clean, report, _ = cleaner.clean_frame(raw)
        self.assertEqual(len(clean), 72)
        self.assertEqual(report["steps"]["inserted_hours"], 1)
        self.assertEqual(clean["is_inserted_hour"].sum(), 1)

    def test_wind_interpolates_across_north_and_360_becomes_0(self):
        raw = raw_frame()
        raw.loc[5, "WD2M"], raw.loc[6, "WD2M"], raw.loc[7, "WD2M"] = "350", "", "10"
        raw.loc[8, "WD2M"] = "360"
        clean, report, _ = cleaner.clean_frame(raw)
        self.assertAlmostEqual(clean["WD2M"].iloc[6] % 360, 0.0, places=1)  # not 180°
        self.assertEqual(clean["WD2M"].iloc[8], 0)
        self.assertEqual(report["steps"]["wind_direction_360_to_0"], 1)

    def test_exact_duplicates_removed_conflicts_rejected(self):
        raw = raw_frame()
        clean, report, _ = cleaner.clean_frame(pd.concat([raw, raw.iloc[[4]]], ignore_index=True))
        self.assertEqual(report["steps"]["exact_duplicates_removed"], 1)
        conflict = raw.iloc[[4]].copy()
        conflict["T2M"] = "35"
        with self.assertRaisesRegex(ValueError, "disagree"):
            cleaner.clean_frame(pd.concat([raw, conflict], ignore_index=True))

    def test_statistical_outliers_are_flagged_not_removed(self):
        raw = raw_frame(hours=24 * 40)
        raw["T2M"] = [str(20 + 0.1 * (i % 7)) for i in range(len(raw))]
        raw.loc[500, "T2M"] = "38"
        clean, _, flags = cleaner.clean_frame(raw)
        self.assertEqual(clean["T2M"].iloc[500], 38)
        self.assertIn("T2M", clean["outlier_flags"].iloc[500])
        self.assertTrue(((flags.variable == "T2M") & (flags.value == 38)).any())

    def test_clean_writes_csv_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.csv"
            raw_frame().to_csv(source, index=False)
            path, report = cleaner.clean(source, root / "cleaned", min_rows=1, log_dir=root / "logs")
            loaded = cleaner.load_cleaned(path)
            self.assertEqual(list(loaded.columns), cleaner.CLEAN_COLUMNS[1:])
            self.assertTrue(path.with_suffix(".metadata.json").exists())
            self.assertEqual(report["after"]["rows"], 72)


if __name__ == "__main__":
    unittest.main()
