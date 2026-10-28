"""Small unit tests for temperature-model helpers that do not fit a model."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing.features import TABULAR_FEATURES
from src.training.predict_temperature import parse_timestamp, predict_row, select_row
from src.training.train_temperature import accuracy_within_tolerance, persistence_forecast, regression_metrics


class TemperatureTrainingTests(unittest.TestCase):
    def test_persistence_restores_temperature_from_z_score(self):
        frame = pd.DataFrame({"T2M": [-1.0, 0.0, 2.0]})
        np.testing.assert_allclose(persistence_forecast(frame, 20.0, 3.0), [17.0, 20.0, 26.0])

    def test_regression_metrics_are_zero_for_exact_forecast(self):
        self.assertEqual(regression_metrics(np.array([1.0, 2.0]), np.array([1.0, 2.0])),
                         {"mae_c": 0.0, "rmse_c": 0.0})

    def test_accuracy_within_tolerance_counts_boundary_as_correct(self):
        actual = np.array([20.0, 20.0, 20.0, 20.0])
        predicted = np.array([19.0, 20.2, 21.0, 21.1])
        self.assertEqual(accuracy_within_tolerance(actual, predicted, 1.0), 75.0)
        self.assertEqual(accuracy_within_tolerance(actual, predicted, 2.0), 100.0)

    def test_accuracy_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            accuracy_within_tolerance(np.array([]), np.array([]), 1.0)
        with self.assertRaises(ValueError):
            accuracy_within_tolerance(np.array([1.0]), np.array([1.0]), 0.0)
        with self.assertRaises(ValueError):
            accuracy_within_tolerance(np.array([1.0]), np.array([1.0, 2.0]), 1.0)

    def test_naive_timestamp_is_hanoi_time(self):
        self.assertEqual(str(parse_timestamp("2024-01-01 00:00:00")), "2024-01-01 00:00:00+07:00")

    def test_default_demo_row_has_all_targets(self):
        index = pd.date_range("2024-01-01", periods=2, freq="h", tz="Asia/Ho_Chi_Minh")
        frame = pd.DataFrame({"T2M_t+1h": [1.0, 2.0], "T2M_t+6h": [1.0, 2.0],
                              "T2M_t+12h": [1.0, np.nan], "T2M_t+24h": [1.0, np.nan]}, index=index)
        timestamp, _ = select_row(frame, None)
        self.assertEqual(timestamp, index[0])

    def test_select_row_rejects_missing_timestamp(self):
        index = pd.date_range("2024-01-01", periods=1, freq="h", tz="Asia/Ho_Chi_Minh")
        frame = pd.DataFrame({target: [1.0] for target in ("T2M_t+1h", "T2M_t+6h", "T2M_t+12h", "T2M_t+24h")},
                             index=index)
        with self.assertRaises(ValueError):
            select_row(frame, "2025-01-01T00:00:00+07:00")

    def test_predict_row_explains_when_model_is_missing(self):
        row = pd.Series({feature: 0.0 for feature in TABULAR_FEATURES})
        row["T2M_t+1h"] = 20.0
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                predict_row(row, Path(directory))


if __name__ == "__main__":
    unittest.main()
