"""Shared constants for the Hanoi temperature-forecasting data pipeline.

Every number here is a design decision explained in README.md (section 5-7).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STEM = "hanoi_hourly_20010101_20251231"

# Raw NASA POWER download (UTC). When it is not on disk, the committed copy in
# outputs/timeseries_quality_v2 holds the same 219,144 unmodified values (GMT+7).
RAW_PATH = ROOT / "data/raw/nasa_power" / f"{STEM}.csv"
FALLBACK_RAW_PATH = ROOT / "outputs/timeseries_quality_v2" / f"{STEM}_quality_clean.csv"
CLEANED_DIR = ROOT / "data/cleaned/nasa_power"
PROCESSED_DIR = ROOT / "data/processed/nasa_power"
FIGURE_DIR = ROOT / "outputs/figures"
REPORT_DIR = ROOT / "outputs/reports"

TIMEZONE = "Asia/Ho_Chi_Minh"  # GMT+7, no daylight saving
VARS = ["T2M", "PRECTOTCORR", "RH2M", "PS", "WS2M", "WD2M", "ALLSKY_SFC_SW_DWN"]
UNITS = {"T2M": "°C", "PRECTOTCORR": "mm/giờ", "RH2M": "%", "PS": "kPa",
         "WS2M": "m/s", "WD2M": "độ", "ALLSKY_SFC_SW_DWN": "Wh/m²"}
FILL_VALUES = {-999.0, -99.0}

# Physically possible bounds (not "typical" bounds): values outside are sensor or
# file errors, values inside are kept even when rare (cold surges, typhoons).
PHYSICAL_BOUNDS = {
    "T2M": (-10.0, 50.0),          # far outside anything recorded in Hanoi
    "PRECTOTCORR": (0.0, 200.0),   # world hourly record is ~300 mm
    "RH2M": (0.0, 100.0),
    "PS": (90.0, 110.0),           # kPa; Hanoi is near sea level
    "WS2M": (0.0, 75.0),
    "WD2M": (0.0, 360.0),
    "ALLSKY_SFC_SW_DWN": (0.0, 1400.0),  # solar constant is ~1361 W/m²
}
MAX_INTERPOLATE_HOURS = 3   # longer gaps stay NaN and their samples are dropped
ROBUST_Z_LIMIT = 5.0        # seasonal robust z-score flag (report only, never delete)

HORIZONS = [1, 6, 12, 24]   # forecast T2M at t+1h, t+6h, t+12h, t+24h
SEQ_LEN = 48                # LSTM/GRU look-back window (hours)
TEMPERATURE_LAGS = [1, 2, 3, 6, 12, 24]

# Chronological split on the forecast time t (local time). Samples whose target
# t+24h crosses into the next period are purged.
SPLITS = {
    "train": ("2001-01-01", "2018-12-31 23:00"),
    "val": ("2019-01-01", "2021-12-31 23:00"),
    "test": ("2022-01-01", "2026-01-01 06:00"),
}
