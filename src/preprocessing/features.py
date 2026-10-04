"""Step 2 - features, multi-horizon targets, time split and scaling.

python -m src.preprocessing.features

Output is one continuous hourly table (scaled features + targets in °C + a
`split` column), so the same rows serve Linear Regression (tabular columns)
and LSTM/GRU (sliding windows over the sequence columns, see sequences.py).
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing.cleaning import load_cleaned
from src.preprocessing.config import (CLEANED_DIR, HORIZONS, PROCESSED_DIR, REPORT_DIR, SEQ_LEN, SPLITS, STEM,
                                      TEMPERATURE_LAGS, TIMEZONE, VARS)

VERSION = "2.0"
MODEL_READY = PROCESSED_DIR / "hanoi_t2m_model_ready.csv"
SCALER_PATH = PROCESSED_DIR / "scaler.json"
METADATA_PATH = PROCESSED_DIR / "hanoi_t2m_model_ready.metadata.json"

CYCLIC_FEATURES = ["hour_sin", "hour_cos", "doy_sin", "doy_cos"]
# Per-hour inputs for LSTM/GRU: the network learns its own lags from the window.
SEQUENCE_FEATURES = ["T2M", "RH2M", "DEWPOINT", "PS", "WS2M", "WIND_U", "WIND_V",
                     "PRECTOTCORR_log1p", "ALLSKY_SFC_SW_DWN", *CYCLIC_FEATURES]
# Linear Regression sees one row, so history must be given explicitly as columns.
HISTORY_FEATURES = [*(f"T2M_lag_{k}h" for k in TEMPERATURE_LAGS),
                    "T2M_roll_mean_24h", "T2M_roll_min_24h", "T2M_roll_max_24h",
                    "PS_diff_3h", "PS_diff_24h", "PRECTOTCORR_sum_24h_log1p", "ALLSKY_sum_24h"]
TABULAR_FEATURES = [*SEQUENCE_FEATURES, *HISTORY_FEATURES]
TARGETS = [f"T2M_t+{h}h" for h in HORIZONS]
# Already bounded in [-1, 1]; scaling them would only blur their meaning.
UNSCALED_FEATURES = list(CYCLIC_FEATURES)
SCALED_FEATURES = [c for c in TABULAR_FEATURES if c not in UNSCALED_FEATURES]


def dewpoint(temperature, humidity):
    """Magnus formula (Alduchov & Eskridge 1996), °C."""
    a, b = 17.625, 243.04
    gamma = np.log(humidity.clip(lower=1) / 100) + a * temperature / (b + temperature)
    return b * gamma / (a - gamma)


def add_features(clean):
    """Every feature at row t uses only hours <= t (no look-ahead)."""
    df = clean[VARS].copy()
    df["DEWPOINT"] = dewpoint(df["T2M"], df["RH2M"])
    # Meteorological convention: WD2M is where the wind blows FROM, so the
    # vector points the opposite way. u > 0 = towards east, v > 0 = towards north.
    radians = np.deg2rad(df["WD2M"])
    df["WIND_U"] = -df["WS2M"] * np.sin(radians)
    df["WIND_V"] = -df["WS2M"] * np.cos(radians)
    df["PRECTOTCORR_log1p"] = np.log1p(df["PRECTOTCORR"])

    hour = df.index.hour
    day = df.index.dayofyear - 1 + hour / 24
    df["hour_sin"], df["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * day / 365.25), np.cos(2 * np.pi * day / 365.25)

    for k in TEMPERATURE_LAGS:
        df[f"T2M_lag_{k}h"] = df["T2M"].shift(k)
    window = df["T2M"].rolling(24, min_periods=24)
    df["T2M_roll_mean_24h"], df["T2M_roll_min_24h"], df["T2M_roll_max_24h"] = window.mean(), window.min(), window.max()
    df["PS_diff_3h"] = df["PS"].diff(3)
    df["PS_diff_24h"] = df["PS"].diff(24)
    df["PRECTOTCORR_sum_24h_log1p"] = np.log1p(df["PRECTOTCORR"].rolling(24, min_periods=24).sum())
    df["ALLSKY_sum_24h"] = df["ALLSKY_SFC_SW_DWN"].rolling(24, min_periods=24).sum()

    for h, name in zip(HORIZONS, TARGETS):
        df[name] = df["T2M"].shift(-h)
    return df


def assign_split(df, quality_bad):
    """Label each forecast time t as train / val / test / none.

    A row is a usable sample only if its whole span [t-SEQ_LEN+1, t+max(h)]
    is real (no inserted/interpolated hour) and every feature/target exists.
    Rows whose t+24h target falls into the next period are purged, so no
    target value is shared between two splits.
    """
    max_h = max(HORIZONS)
    bad = quality_bad.astype(int)
    bad_past = bad.rolling(SEQ_LEN, min_periods=SEQ_LEN).max().fillna(1).astype(bool)
    bad_future = bad[::-1].rolling(max_h, min_periods=1).max()[::-1].shift(-1).fillna(1).astype(bool)
    complete = df[[*TABULAR_FEATURES, *TARGETS]].notna().all(axis=1)
    usable = complete & ~bad_past & ~bad_future

    split = pd.Series("none", index=df.index)
    target_time = df.index + pd.Timedelta(hours=max_h)
    for name, (start, end) in SPLITS.items():
        start, end = pd.Timestamp(start, tz=TIMEZONE), pd.Timestamp(end, tz=TIMEZONE)
        inside = (df.index >= start) & (target_time <= end)
        split[usable & inside] = name
    return split


def fit_scaler(df, split):
    """z-score parameters from TRAIN rows only (val/test must stay unseen)."""
    train = df.loc[split.eq("train"), SCALED_FEATURES]
    std = train.std(ddof=0).mask(lambda s: s < 1e-9, 1.0)  # a constant column stays constant instead of dividing by 0
    params = {c: {"mean": float(train[c].mean()), "std": float(std[c])} for c in SCALED_FEATURES}
    params["__target__"] = {"mean": float(df.loc[split.eq("train"), "T2M"].mean()),
                            "std": float(df.loc[split.eq("train"), "T2M"].std(ddof=0)),
                            "columns": TARGETS, "note": "Targets are stored in °C; use for LSTM/GRU target scaling."}
    return params


def apply_scaler(df, params):
    out = df.copy()
    for c in SCALED_FEATURES:
        out[c] = (out[c] - params[c]["mean"]) / params[c]["std"]
    return out


def build(clean):
    """clean (hourly, local time) -> (model_ready, scaler params, unscaled features)."""
    features = add_features(clean)
    quality_bad = clean["is_inserted_hour"].eq(1) | clean["is_imputed"].eq(1) | clean[VARS].isna().any(axis=1)
    features["split"] = assign_split(features, quality_bad)
    params = fit_scaler(features, features["split"])
    scaled = apply_scaler(features, params)
    model_ready = scaled[["split", *TABULAR_FEATURES, *TARGETS]]
    return model_ready, params, features


def summarize(model_ready):
    counts = model_ready["split"].value_counts().to_dict()
    ranges = {}
    for name in SPLITS:
        part = model_ready.index[model_ready["split"].eq(name)]
        ranges[name] = {"rows": int(len(part)), "first_t": str(part.min()), "last_t": str(part.max())}
    return {k: int(v) for k, v in counts.items()}, ranges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=CLEANED_DIR / f"{STEM}_clean.csv")
    parser.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    args = parser.parse_args()
    model_ready, params, _ = build(load_cleaned(args.input))
    counts, ranges = summarize(model_ready)

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / MODEL_READY.name
    table = model_ready.reset_index()
    table["timestamp"] = table["timestamp"].map(lambda t: t.isoformat())
    table.to_csv(csv_path, index=False, float_format="%.6g")
    (out_dir / SCALER_PATH.name).write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {
        "version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(args.input.resolve()), "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "timezone": TIMEZONE, "rows": len(table), "horizons_hours": HORIZONS, "seq_len": SEQ_LEN,
        "targets": TARGETS, "target_unit": "°C (unscaled)",
        "sequence_features": SEQUENCE_FEATURES, "tabular_features": TABULAR_FEATURES,
        "scaled_features": SCALED_FEATURES, "unscaled_features": UNSCALED_FEATURES,
        "scaler": "z-score, fit on split == 'train' only; parameters in scaler.json",
        "splits": SPLITS, "split_counts": counts, "split_ranges": ranges,
        "usage": "Use rows with split in {train,val,test}. 'none' rows are warm-up/purged/tail hours that "
                 "remain only so LSTM/GRU windows can look back across them.",
    }
    text = json.dumps(metadata, ensure_ascii=False, indent=2)
    (out_dir / METADATA_PATH.name).write_text(text, encoding="utf-8")
    if out_dir == PROCESSED_DIR.resolve():
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        (REPORT_DIR / "features_report.json").write_text(text, encoding="utf-8")
        (REPORT_DIR / "scaler.json").write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(csv_path), "split_counts": counts}, indent=2))


if __name__ == "__main__":
    main()
