"""Train reproducible LightGBM models for Hanoi temperature forecasts.

The model-ready table is already split chronologically and has features scaled
from training data only. This module trains one regressor for each forecast
horizon, uses validation only for early stopping, and reports the final scores
on the untouched 2022--2025 test period.

Run from the repository root::

    python -m src.training.train_temperature
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from src.preprocessing.config import HORIZONS, ROOT
from src.preprocessing.features import TARGETS
from src.preprocessing.sequences import load_model_ready, tabular_xy, target_scaler

DEFAULT_MODEL_DIR = ROOT / "models" / "temperature_lightgbm"
DEFAULT_REPORT_DIR = ROOT / "outputs" / "reports"
RANDOM_SEED = 42
ACCURACY_TOLERANCES_C = (1.0, 2.0)


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    """Return human-readable regression metrics in degrees Celsius."""
    return {
        "mae_c": float(mean_absolute_error(actual, predicted)),
        "rmse_c": float(root_mean_squared_error(actual, predicted)),
    }


def accuracy_within_tolerance(actual: np.ndarray, predicted: np.ndarray, tolerance_c: float) -> float:
    """Percentage of forecasts within a specified absolute-error tolerance."""
    if tolerance_c <= 0:
        raise ValueError("tolerance_c must be positive")
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.shape != predicted.shape:
        raise ValueError("actual and predicted must have the same shape")
    if actual.size == 0:
        raise ValueError("actual and predicted must not be empty")
    return float(np.mean(np.abs(actual - predicted) <= tolerance_c) * 100)


def persistence_forecast(frame: pd.DataFrame, temperature_mean: float, temperature_std: float) -> np.ndarray:
    """Naive baseline: use T2M observed at t, restored from its z-score."""
    return frame["T2M"].to_numpy(dtype=float) * temperature_std + temperature_mean


def build_regressor(n_estimators: int, learning_rate: float, n_jobs: int) -> lgb.LGBMRegressor:
    """Create the common estimator configuration for every horizon."""
    return lgb.LGBMRegressor(
        objective="regression", n_estimators=n_estimators, learning_rate=learning_rate,
        num_leaves=31, min_child_samples=30, subsample=0.8, colsample_bytree=0.9,
        reg_lambda=1.0, random_state=RANDOM_SEED, n_jobs=n_jobs, verbosity=-1,
    )


def train_all(df: pd.DataFrame, *, model_dir: Path, n_estimators: int = 300,
              learning_rate: float = 0.05, early_stopping_rounds: int = 100,
              n_jobs: int = -1) -> pd.DataFrame:
    """Fit four independent models and persist their native LightGBM files.

    Fitting horizons separately lets each model stop at the validation round
    appropriate to its own difficulty. Targets remain in degrees Celsius, so
    all metrics are directly interpretable.
    """
    X_train, y_train = tabular_xy(df, "train")
    X_val, y_val = tabular_xy(df, "val")
    X_test, y_test = tabular_xy(df, "test")
    temperature_mean, temperature_std = target_scaler()
    model_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    for horizon, target in zip(HORIZONS, TARGETS):
        model = build_regressor(n_estimators, learning_rate, n_jobs)
        model.fit(
            X_train, y_train[target], eval_X=X_val, eval_y=y_val[target], eval_metric="l1",
            callbacks=[lgb.early_stopping(early_stopping_rounds, verbose=False)],
        )
        best_iteration = model.best_iteration_ or n_estimators
        model_path = model_dir / f"t2m_t_plus_{horizon}h.txt"
        model.booster_.save_model(str(model_path), num_iteration=best_iteration)

        val_pred = model.predict(X_val, num_iteration=best_iteration)
        test_pred = model.predict(X_test, num_iteration=best_iteration)
        baseline_test = persistence_forecast(X_test, temperature_mean, temperature_std)
        val_metrics = regression_metrics(y_val[target], val_pred)
        test_metrics = regression_metrics(y_test[target], test_pred)
        baseline_metrics = regression_metrics(y_test[target], baseline_test)
        records.append({
            "horizon_hours": horizon, "target": target, "best_iteration": int(best_iteration),
            "validation_mae_c": val_metrics["mae_c"], "validation_rmse_c": val_metrics["rmse_c"],
            "test_mae_c": test_metrics["mae_c"], "test_rmse_c": test_metrics["rmse_c"],
            "persistence_test_mae_c": baseline_metrics["mae_c"],
            "persistence_test_rmse_c": baseline_metrics["rmse_c"],
            "test_accuracy_within_1c_pct": accuracy_within_tolerance(y_test[target], test_pred, 1.0),
            "test_accuracy_within_2c_pct": accuracy_within_tolerance(y_test[target], test_pred, 2.0),
            "model_path": str(model_path.relative_to(ROOT)),
        })
    return pd.DataFrame(records)


def write_report(metrics: pd.DataFrame, report_dir: Path, args: argparse.Namespace) -> tuple[Path, Path]:
    """Write compact CSV and JSON artifacts suitable for README/reporting."""
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "temperature_lightgbm_metrics.csv"
    json_path = report_dir / "temperature_lightgbm_metrics.json"
    metrics.to_csv(csv_path, index=False, float_format="%.6f")
    payload = {
        "model": "LightGBM Regressor (one model per horizon)",
        "features": "26 tabular features from hanoi_t2m_model_ready.csv",
        "selection": "Early stopping on chronological validation split (2019--2021), MAE metric.",
        "evaluation": "Final scores on untouched chronological test split (2022--2025).",
        "accuracy_definition": {
            "test_accuracy_within_1c_pct": "Percent of test forecasts with absolute error <= 1 degree C.",
            "test_accuracy_within_2c_pct": "Percent of test forecasts with absolute error <= 2 degrees C.",
        },
        "parameters": {"n_estimators_max": args.n_estimators, "learning_rate": args.learning_rate,
                       "early_stopping_rounds": args.early_stopping_rounds, "random_seed": RANDOM_SEED},
        "results": metrics.to_dict(orient="records"),
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--early-stopping-rounds", type=int, default=100)
    parser.add_argument("--n-jobs", type=int, default=-1)
    args = parser.parse_args()
    if args.n_estimators < 1 or args.early_stopping_rounds < 1 or args.learning_rate <= 0:
        parser.error("n-estimators, early-stopping-rounds and learning-rate must be positive")

    metrics = train_all(load_model_ready(), model_dir=args.model_dir.resolve(), n_estimators=args.n_estimators,
                        learning_rate=args.learning_rate, early_stopping_rounds=args.early_stopping_rounds,
                        n_jobs=args.n_jobs)
    csv_path, json_path = write_report(metrics, args.report_dir.resolve(), args)
    print(metrics.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    print(f"\nMetrics: {csv_path}\nReport: {json_path}")


if __name__ == "__main__":
    main()
