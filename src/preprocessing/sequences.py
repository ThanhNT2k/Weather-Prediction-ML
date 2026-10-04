"""Load the model-ready table as model inputs.

    from src.preprocessing.sequences import load_model_ready, tabular_xy, make_sequences
    df = load_model_ready()
    X_train, y_train = tabular_xy(df, "train")            # Linear Regression
    X_seq, y_seq, t = make_sequences(df, "train")          # LSTM / GRU: (n, 48, 13)
"""

import json

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from src.preprocessing.config import SEQ_LEN, TIMEZONE
from src.preprocessing.features import MODEL_READY, SCALER_PATH, SEQUENCE_FEATURES, TABULAR_FEATURES, TARGETS


def load_model_ready(path=MODEL_READY):
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(TIMEZONE)
    return df.set_index("timestamp")


def tabular_xy(df, split):
    rows = df["split"].eq(split)
    return df.loc[rows, TABULAR_FEATURES], df.loc[rows, TARGETS]


def target_scaler(path=SCALER_PATH):
    params = json.loads(path.read_text(encoding="utf-8"))["__target__"]
    return params["mean"], params["std"]


def make_sequences(df, split, seq_len=SEQ_LEN, features=SEQUENCE_FEATURES, scale_target=False,
                   target_stats=None, dtype=np.float32):
    """Window i holds hours [t-seq_len+1, t] for every forecast time t in `split`.

    The table must be the continuous hourly table written by features.py: the
    window may reach back into 'none' rows (warm-up) or the previous split,
    which is allowed because those hours are already known at time t.
    """
    step = df.index.to_series().diff().iloc[1:]
    if not step.eq(pd.Timedelta(hours=1)).all():
        raise ValueError("make_sequences needs the full continuous hourly table")
    anchors = np.flatnonzero(df["split"].eq(split).to_numpy())
    if anchors.size and anchors[0] < seq_len - 1:
        raise ValueError("First sample does not have seq_len hours of history")
    windows = sliding_window_view(df[features].to_numpy(dtype), seq_len, axis=0)  # (N-L+1, F, L), no copy
    X = windows[anchors - seq_len + 1].transpose(0, 2, 1)  # (n, L, F)
    y = df[TARGETS].to_numpy(dtype)[anchors]
    if scale_target:
        mean, std = target_stats or target_scaler()
        y = (y - mean) / std
    if np.isnan(X).any() or np.isnan(y).any():
        raise ValueError("Windows contain NaN; only use split labels written by features.py")
    return X, y, df.index[anchors]
