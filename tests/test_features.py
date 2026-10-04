"""Features: causality, target alignment, split purging, train-only scaling, sequences."""

import unittest

import numpy as np
import pandas as pd

from src.preprocessing import features as feat
from src.preprocessing.config import SEQ_LEN, TIMEZONE, VARS
from src.preprocessing.sequences import make_sequences, tabular_xy


def clean_frame(start="2018-12-20", end="2019-01-10 23:00"):
    index = pd.date_range(start, end, freq="h", tz=TIMEZONE, name="timestamp")
    n = len(index)
    frame = pd.DataFrame({
        "T2M": np.arange(n, dtype=float), "PRECTOTCORR": np.where(np.arange(n) % 5 == 0, 2.0, 0.0),
        "RH2M": 80.0, "PS": 100 + np.arange(n) / 100, "WS2M": 2.0, "WD2M": 90.0, "ALLSKY_SFC_SW_DWN": 50.0,
    }, index=index)
    frame["is_inserted_hour"] = 0
    frame["is_imputed"] = 0
    return frame


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.clean = clean_frame()
        self.ready, self.params, self.features = feat.build(self.clean)

    def test_targets_are_future_values(self):
        row = self.features.iloc[100]
        for h, name in zip(feat.HORIZONS, feat.TARGETS):
            self.assertEqual(row[name], self.clean["T2M"].iloc[100 + h])

    def test_features_only_use_past(self):
        changed = self.clean.copy()
        changed.iloc[101:, changed.columns.get_loc("T2M")] += 50  # change only the future
        _, _, other = feat.build(changed)
        self.assertTrue(np.allclose(self.features.iloc[100][feat.TABULAR_FEATURES].astype(float),
                                    other.iloc[100][feat.TABULAR_FEATURES].astype(float)))

    def test_wind_vector_follows_meteorological_convention(self):
        # Wind FROM the east (90°) blows towards the west: u < 0, v ≈ 0.
        self.assertAlmostEqual(self.features["WIND_U"].iloc[0], -2.0)
        self.assertAlmostEqual(self.features["WIND_V"].iloc[0], 0.0)

    def test_cyclic_hour_makes_23h_close_to_0h(self):
        at = self.features.between_time("23:00", "23:00").iloc[0]
        nxt = self.features.between_time("00:00", "00:00").iloc[1]
        self.assertLess(np.hypot(at.hour_sin - nxt.hour_sin, at.hour_cos - nxt.hour_cos), 0.3)

    def test_split_is_chronological_and_purged(self):
        split = self.ready["split"]
        train, val = split.index[split.eq("train")], split.index[split.eq("val")]
        self.assertEqual(train[0], self.clean.index[SEQ_LEN - 1])  # warm-up removed
        self.assertLessEqual(train[-1] + pd.Timedelta(hours=24), pd.Timestamp("2018-12-31 23:00", tz=TIMEZONE))
        self.assertEqual(val[0], pd.Timestamp("2019-01-01", tz=TIMEZONE))
        self.assertTrue(split.iloc[-24:].eq("none").all())  # no future label

    def test_imputed_hour_removes_every_window_touching_it(self):
        clean = self.clean.copy()
        clean.iloc[200, clean.columns.get_loc("is_imputed")] = 1
        ready, _, _ = feat.build(clean)
        touched = ready["split"].iloc[200 - 24:200 + SEQ_LEN]
        self.assertTrue(touched.eq("none").all())
        self.assertNotEqual(ready["split"].iloc[200 + SEQ_LEN], "none")

    def test_scaler_fit_on_train_only(self):
        train = self.ready.loc[self.ready["split"].eq("train"), feat.SCALED_FEATURES]
        self.assertTrue(np.allclose(train.mean(), 0, atol=1e-9))
        varying = self.features.loc[self.ready["split"].eq("train"), feat.SCALED_FEATURES].std(ddof=0) > 1e-9
        self.assertTrue(np.allclose(train.loc[:, varying].std(ddof=0), 1, atol=1e-9))
        raw_train = self.features.loc[self.ready["split"].eq("train"), "T2M"]
        self.assertAlmostEqual(self.params["T2M"]["mean"], raw_train.mean())
        self.assertTrue((self.ready[feat.UNSCALED_FEATURES] == self.features[feat.UNSCALED_FEATURES]).all().all())

    def test_tabular_and_sequence_outputs(self):
        X, y = tabular_xy(self.ready, "train")
        self.assertEqual(list(X.columns), feat.TABULAR_FEATURES)
        self.assertEqual(list(y.columns), feat.TARGETS)
        Xs, ys, times = make_sequences(self.ready, "val", target_stats=(0.0, 1.0))
        self.assertEqual(Xs.shape, (len(times), SEQ_LEN, len(feat.SEQUENCE_FEATURES)))
        anchor = self.ready.index.get_loc(times[0])
        expected = self.ready[feat.SEQUENCE_FEATURES].iloc[anchor - SEQ_LEN + 1:anchor + 1].to_numpy(np.float32)
        self.assertTrue(np.allclose(Xs[0], expected))
        self.assertTrue(np.allclose(ys, self.ready.loc[times, feat.TARGETS].to_numpy()))


if __name__ == "__main__":
    unittest.main()
