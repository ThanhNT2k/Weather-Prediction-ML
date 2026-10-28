"""Run a saved Hanoi-temperature model for one historical feature row.

This is an offline demonstration: model-ready data contains historical
features at time t. When targets are available, the command also displays the
observed future temperature and the absolute error for each horizon.

Example::

    python -m src.training.predict_temperature --timestamp 2024-09-07T12:00:00+07:00
"""

from __future__ import annotations

import argparse
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from src.preprocessing.config import HORIZONS, ROOT, TIMEZONE
from src.preprocessing.features import TABULAR_FEATURES, TARGETS
from src.preprocessing.sequences import load_model_ready

DEFAULT_MODEL_DIR = ROOT / "models" / "temperature_lightgbm"


def parse_timestamp(value: str) -> pd.Timestamp:
    """Parse an ISO timestamp; naive values are interpreted as Hanoi time."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(TIMEZONE)
    return timestamp.tz_convert(TIMEZONE)


def select_row(df: pd.DataFrame, timestamp: str | None) -> tuple[pd.Timestamp, pd.Series]:
    """Choose a requested row, or the latest row with all four known targets."""
    if timestamp is None:
        candidates = df.dropna(subset=TARGETS)
        if candidates.empty:
            raise ValueError("No row contains all forecast targets for the demo.")
        chosen = candidates.index[-1]
    else:
        chosen = parse_timestamp(timestamp)
        if chosen not in df.index:
            raise ValueError(f"Timestamp not found: {chosen.isoformat()}")
    return chosen, df.loc[chosen]


def predict_row(row: pd.Series, model_dir: Path) -> pd.DataFrame:
    """Load four native LightGBM models and return predictions in degrees C."""
    # A mixed Series (it also holds `split` and targets) becomes object dtype;
    # reconstruct numeric features explicitly before giving them to LightGBM.
    features = pd.DataFrame([row[TABULAR_FEATURES].to_numpy(dtype=float)], columns=TABULAR_FEATURES)
    result = []
    for horizon, target in zip(HORIZONS, TARGETS):
        model_path = model_dir / f"t2m_t_plus_{horizon}h.txt"
        if not model_path.is_file():
            raise FileNotFoundError(f"Missing model: {model_path}. Run train_temperature first.")
        prediction = float(lgb.Booster(model_file=str(model_path)).predict(features)[0])
        actual = row[target]
        item = {"horizon_hours": horizon, "prediction_c": prediction}
        if pd.notna(actual):
            item["actual_c"] = float(actual)
            item["absolute_error_c"] = abs(prediction - float(actual))
        result.append(item)
    return pd.DataFrame(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timestamp", help="ISO time, e.g. 2024-09-07T12:00:00+07:00")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()

    timestamp, row = select_row(load_model_ready(), args.timestamp)
    predictions = predict_row(row, args.model_dir.resolve())
    print(f"Forecast origin: {timestamp.isoformat()} ({row['split']})")
    print(predictions.to_string(index=False, float_format=lambda value: f"{value:.3f}"))


if __name__ == "__main__":
    main()
