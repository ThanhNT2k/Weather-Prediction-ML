"""Step 1 - clean Hanoi NASA POWER hourly data: python -m src.preprocessing.cleaning.

raw (UTC) -> audit -> local time -> invalid values to NaN -> duplicates ->
continuous hourly axis -> short-gap interpolation -> outlier flags (kept).
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.data_audit import DataAudit, DEFAULT_LOG_DIR, file_info
from src.preprocessing.config import (CLEANED_DIR, FALLBACK_RAW_PATH, FILL_VALUES, MAX_INTERPOLATE_HOURS,
                                      PHYSICAL_BOUNDS, RAW_PATH, REPORT_DIR, ROBUST_Z_LIMIT, ROOT, STEM,
                                      TIMEZONE, VARS)

VERSION = "2.0"
CLEAN_COLUMNS = ["timestamp", *VARS, "is_inserted_hour", "is_imputed", "imputed_columns", "outlier_flags"]


def default_input():
    return RAW_PATH if RAW_PATH.exists() else FALLBACK_RAW_PATH


def read_raw(path):
    """Read every column as text so blanks/garbage are counted, not silently parsed."""
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def audit_raw(raw):
    """Profile the file before touching it (what the report calls 'before cleaning')."""
    numeric = raw[VARS].apply(pd.to_numeric, errors="coerce")
    blank = raw[VARS].apply(lambda s: s.str.strip().eq("")).sum()
    return {
        "rows": len(raw),
        "columns": list(raw.columns),
        "exact_duplicate_rows": int(raw.duplicated().sum()),
        "duplicate_timestamps": int(raw["timestamp"].duplicated().sum()),
        "blank_cells": blank.astype(int).to_dict(),
        "unparseable_cells": (numeric.isna() & ~raw[VARS].apply(lambda s: s.str.strip().eq(""))).sum().astype(int).to_dict(),
        "fill_value_cells": numeric.isin(FILL_VALUES).sum().astype(int).to_dict(),
        "describe": numeric.describe().round(3).to_dict(),
    }


def parse_timestamps(text):
    """Timestamps must carry an explicit offset and sit on exact hours."""
    if not text.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).all():
        raise ValueError("Every timestamp must include an explicit timezone offset")
    parsed = pd.to_datetime(text, utc=True, errors="coerce", format="ISO8601")
    if parsed.isna().any():
        raise ValueError(f"{int(parsed.isna().sum())} timestamps cannot be parsed")
    if parsed.ne(parsed.dt.floor("h")).any():
        raise ValueError("Timestamps must be aligned to exact hours")
    return parsed.dt.tz_convert(TIMEZONE)


def gap_lengths(missing):
    """Length of the NaN run each hour belongs to (0 for observed hours)."""
    run_id = missing.ne(missing.shift()).cumsum()
    return missing.groupby(run_id).transform("sum").where(missing, 0).astype(int)


def interpolate_short_gaps(frame, max_hours=MAX_INTERPOLATE_HOURS):
    """Time-interpolate interior gaps of <= max_hours; longer gaps stay NaN.

    Wind direction is interpolated through its (u, v) vector so 350° -> 10°
    passes north instead of sweeping back through 180°.
    """
    out = frame.copy()
    filled = pd.DataFrame(False, index=frame.index, columns=VARS)
    linear = [c for c in VARS if c != "WD2M"]
    for column in linear:
        missing = frame[column].isna()
        eligible = missing & gap_lengths(missing).le(max_hours)
        candidate = frame[column].interpolate(method="time", limit_area="inside")
        eligible &= candidate.notna()
        out.loc[eligible, column] = candidate[eligible]
        filled[column] = eligible
    radians = np.deg2rad(frame["WD2M"])
    u = np.sin(radians).interpolate(method="time", limit_area="inside")
    v = np.cos(radians).interpolate(method="time", limit_area="inside")
    missing = frame["WD2M"].isna()
    eligible = missing & gap_lengths(missing).le(max_hours) & u.notna()
    out.loc[eligible, "WD2M"] = (np.rad2deg(np.arctan2(u, v)) % 360)[eligible].round(1)
    filled["WD2M"] = eligible
    return out, filled


def seasonal_robust_z(series):
    """|x - median| / (1.4826 * MAD) inside the same (month, local hour) group.

    Grouping by season and hour stops a normal 12°C winter morning from being
    judged against summer afternoons. Groups with MAD = 0 (night radiation) are
    skipped instead of dividing by zero.
    """
    keys = [series.index.month, series.index.hour]
    median = series.groupby(keys).transform("median")
    deviation = (series - median).abs()
    mad = deviation.groupby(keys).transform("median")
    return deviation / (1.4826 * mad.replace(0, np.nan))


def flag_outliers(frame):
    """Return one row per flagged cell. Flags are evidence for review, not deletions."""
    tables = []
    for column in ["T2M", "RH2M", "PS", "WS2M", "ALLSKY_SFC_SW_DWN"]:
        z = seasonal_robust_z(frame[column])
        hit = z.gt(ROBUST_Z_LIMIT)
        tables.append(pd.DataFrame({"timestamp": frame.index[hit], "variable": column,
                                    "value": frame.loc[hit, column].to_numpy(),
                                    "robust_z": z[hit].round(2).to_numpy(), "rule": "seasonal_robust_z>5"}))
    # Rain is zero-inflated (MAD = 0 almost everywhere): flag the top 0.1% wet hours instead.
    rain = frame["PRECTOTCORR"]
    limit = rain[rain > 0.1].quantile(0.999)
    hit = rain.gt(limit)
    tables.append(pd.DataFrame({"timestamp": frame.index[hit], "variable": "PRECTOTCORR",
                                "value": rain[hit].to_numpy(), "robust_z": np.nan,
                                "rule": f"wet_hour_q99.9>{limit:.2f}"}))
    # Temperature cannot physically jump > 8°C within one hour at 2 m.
    jump = frame["T2M"].diff().abs()
    hit = jump.gt(8)
    tables.append(pd.DataFrame({"timestamp": frame.index[hit], "variable": "T2M",
                                "value": frame.loc[hit, "T2M"].to_numpy(), "robust_z": np.nan,
                                "rule": "hourly_jump>8C"}))
    return pd.concat(tables, ignore_index=True).sort_values(["timestamp", "variable"]).reset_index(drop=True)


def clean_frame(raw):
    """Pure transformation used by the CLI and the tests. Returns (clean, report, flags)."""
    required = {"timestamp", *VARS}
    if not required.issubset(raw.columns):
        raise ValueError(f"Missing CSV columns: {sorted(required - set(raw.columns))}")
    report = {"before": audit_raw(raw), "steps": {}}
    work = pd.DataFrame({"timestamp": parse_timestamps(raw["timestamp"])})

    invalid, wind_360 = {}, 0
    for column in VARS:
        values = pd.to_numeric(raw[column], errors="coerce")
        low, high = PHYSICAL_BOUNDS[column]
        bad = values.isna() | ~np.isfinite(values) | values.isin(FILL_VALUES) | ~values.between(low, high)
        invalid[column] = int(bad.sum())
        work[column] = values.mask(bad)
    wind_360 = int(work["WD2M"].eq(360).sum())
    work["WD2M"] = work["WD2M"].replace(360.0, 0.0)
    report["steps"]["invalid_to_nan"] = invalid
    report["steps"]["wind_direction_360_to_0"] = wind_360

    exact = work.duplicated()
    work = work.loc[~exact]
    conflicts = work["timestamp"].duplicated(keep=False)
    if conflicts.any():
        raise ValueError(f"{int(conflicts.sum())} rows share a timestamp but disagree on values")
    report["steps"]["exact_duplicates_removed"] = int(exact.sum())

    work = work.set_index("timestamp").sort_index()
    full_index = pd.date_range(work.index[0], work.index[-1], freq="h", name="timestamp")
    inserted = ~full_index.isin(work.index)
    work = work.reindex(full_index)
    report["steps"]["inserted_hours"] = int(inserted.sum())

    missing_before = work[VARS].isna()
    work, filled = interpolate_short_gaps(work)
    report["steps"]["missing_cells_before_fill"] = missing_before.sum().astype(int).to_dict()
    report["steps"]["interpolated_cells"] = filled.sum().astype(int).to_dict()
    report["steps"]["missing_cells_after_fill"] = work[VARS].isna().sum().astype(int).to_dict()

    flags = flag_outliers(work)
    report["steps"]["outlier_flags_kept"] = flags.groupby("rule").size().astype(int).to_dict()

    work["is_inserted_hour"] = inserted.astype(int)
    work["is_imputed"] = filled.any(axis=1).astype(int)
    work["imputed_columns"] = filled.apply(lambda row: "|".join(row.index[row]) or "none", axis=1)
    flagged = flags.groupby("timestamp")["variable"].agg(lambda s: "|".join(sorted(set(s))))
    work["outlier_flags"] = flagged.reindex(work.index).fillna("none")
    report["after"] = {"rows": len(work), "start": str(work.index[0]), "end": str(work.index[-1]),
                       "describe": work[VARS].describe().round(3).to_dict()}
    return work, report, flags


def clean(input_path=None, output_dir=CLEANED_DIR, min_rows=10000, log_dir=DEFAULT_LOG_DIR):
    input_path = default_input() if input_path is None else input_path
    with DataAudit("cleaning", {"input": str(input_path), "output_dir": str(output_dir),
                               "min_rows": min_rows, "cleaning_version": VERSION}, __file__, log_dir) as audit:
        input_path, output_dir = Path(input_path).resolve(), Path(output_dir).resolve()
        if output_dir.is_relative_to(ROOT / "data/raw"):
            raise ValueError("Cleaned output must not be written into data/raw")
        audit.event("INPUT", "Đọc dữ liệu nguồn (chỉ đọc)", **file_info(input_path))
        cleaned, report, flags = clean_frame(read_raw(input_path))
        if cleaned[VARS].notna().all(axis=1).sum() < min_rows:
            raise ValueError(f"Fewer than {min_rows} complete hourly rows after cleaning")
        audit.event("TRANSFORMED", "Làm sạch xong", **report["steps"])

        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"{STEM}_clean.csv"
        if csv_path == input_path:
            raise ValueError("Refusing to overwrite the input file")
        out = cleaned.reset_index()
        out["timestamp"] = out["timestamp"].map(lambda t: t.isoformat())
        out[CLEAN_COLUMNS].to_csv(csv_path, index=False, encoding="utf-8")
        flags_path = output_dir / f"{STEM}_outlier_flags.csv"
        flags.assign(timestamp=flags["timestamp"].map(lambda t: t.isoformat())).to_csv(flags_path, index=False)
        report.update({"cleaning_version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
                       "source": file_info(input_path), "timezone": TIMEZONE,
                       "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                       "audit_log": str(audit.path)})
        metadata = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        csv_path.with_suffix(".metadata.json").write_text(metadata, encoding="utf-8")
        if output_dir == CLEANED_DIR.resolve():  # small, human-readable copy kept in Git
            REPORT_DIR.mkdir(parents=True, exist_ok=True)
            (REPORT_DIR / "cleaning_report.json").write_text(metadata, encoding="utf-8")
        audit.event("WRITTEN", "Đã ghi CSV sạch, cờ ngoại lệ và metadata", **file_info(csv_path))
        return csv_path, report


def load_cleaned(path=None):
    path = CLEANED_DIR / f"{STEM}_clean.csv" if path is None else Path(path)
    frame = pd.read_csv(path, encoding="utf-8")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(TIMEZONE)
    return frame.set_index("timestamp")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=CLEANED_DIR)
    parser.add_argument("--min-rows", type=int, default=10000)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()
    path, report = clean(args.input, args.output_dir, args.min_rows, args.log_dir)
    print(json.dumps({"output": str(path), "rows": report["after"]["rows"], **report["steps"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
