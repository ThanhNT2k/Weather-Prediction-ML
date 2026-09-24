"""Build causal hourly features and future targets from cleaned Hanoi data."""

import argparse
import csv
from datetime import datetime, timedelta
import hashlib
import io
import json
import math
from pathlib import Path

from src.data_audit import DataAudit, DEFAULT_LOG_DIR, file_info
from src.data_collection.nasa_power import PARAMETERS
from src.preprocessing.cleaning import ROOT, STATION_ID, record_id, numeric_value, write_atomic

DEFAULT_INPUT = ROOT / "data/cleaned/nasa_power/hanoi_hourly_20230101_20241231_clean.csv"
DEFAULT_OUTPUT = ROOT / "data/processed/nasa_power"
SCHEMA_PATH = ROOT / "docs/data_schema.json"
LOOKBACK = 24
VERSION = "1.0"
DERIVED_FEATURES = ["hour", "month", "dayofweek", "season", "T2M_lag_1h", "T2M_lag_24h",
                    "PRECTOTCORR_lag_1h", "PRECTOTCORR_lag_24h", "PS_diff_3h",
                    "T2M_rolling_mean_3h", "T2M_rolling_mean_24h", "PRECTOTCORR_rolling_sum_24h",
                    "WD2M_sin", "WD2M_cos"]
TARGETS = ["target_temperature", "target_rainfall", "rain_flag"]


def build_features(input_path=DEFAULT_INPUT, output_dir=DEFAULT_OUTPUT, horizon=1,
                   min_rows=10000, log_dir=DEFAULT_LOG_DIR):
    with DataAudit("features", {"input": str(input_path), "output_dir": str(output_dir),
                               "horizon_hours": horizon, "lookback_hours": LOOKBACK,
                               "min_rows": min_rows, "version": VERSION}, __file__, log_dir) as audit:
        if not isinstance(horizon, int) or horizon < 1 or min_rows < 1:
            raise ValueError("horizon and min_rows must be positive integers")
        input_path, output_dir = Path(input_path).resolve(), Path(output_dir).resolve()
        if any(output_dir.is_relative_to(ROOT / "data" / name) for name in ("raw", "cleaned")):
            raise ValueError("Features cannot be written into raw or cleaned data")
        raw_bytes = input_path.read_bytes()
        source_hash = hashlib.sha256(raw_bytes).hexdigest()
        metadata_path = input_path.with_suffix(".metadata.json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata["dataset_id"] != f"sha256:{source_hash}":
            raise ValueError("Cleaned CSV hash does not match its metadata")
        audit.event("INPUT", "Đọc dữ liệu sạch và xác minh hash metadata", **file_info(input_path))
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig")))
        fields = reader.fieldnames or []
        expected_cleaned = [field["name"] for field in schema["fields"] if field["stage"] == "cleaned"]
        if fields != expected_cleaned:
            raise ValueError("Cleaned CSV columns do not match docs/data_schema.json")
        rows = list(reader)
        times, values = [], []
        ids = set()
        for row in rows:
            stamp = datetime.fromisoformat(row["timestamp"])
            if stamp.utcoffset() != timedelta(hours=7) or stamp.minute or stamp.second or stamp.microsecond:
                raise ValueError("Cleaned timestamps must be exact hours in GMT+7")
            if times and stamp - times[-1] != timedelta(hours=1):
                raise ValueError("Cleaned data must be sorted, unique and continuous hourly")
            if row["station_id"] != STATION_ID or row["record_id"] != record_id(row["timestamp"]):
                raise ValueError("Invalid station or record identity")
            if row["record_id"] in ids:
                raise ValueError("Duplicate record_id")
            ids.add(row["record_id"])
            for key in ("is_imputed", "is_inserted_hour"):
                if row[key] not in ("0", "1"):
                    raise ValueError(f"Invalid quality flag {key}")
            if (row["is_imputed"] == "0") != (row["imputed_columns"] == "none"):
                raise ValueError("Inconsistent imputed_columns flag")
            observation = {key: numeric_value(row[key], key, {-999.0}) for key in PARAMETERS}
            if any(value is None for value in observation.values()):
                raise ValueError("Cleaned data contains invalid meteorological values")
            times.append(stamp)
            values.append(observation)
        if len(rows) <= LOOKBACK + horizon:
            raise ValueError("Not enough observations for lookback and horizon")
        rejected_quality = 0
        output = []
        for index in range(LOOKBACK, len(rows) - horizon):
            future = index + horizon
            affected = rows[index - LOOKBACK:index + 1] + [rows[future]]
            if any(row["is_imputed"] == "1" or row["is_inserted_hour"] == "1" for row in affected):
                rejected_quality += 1
                continue
            stamp, current = times[index], values[index]
            derived = {
                "hour": stamp.hour, "month": stamp.month, "dayofweek": stamp.weekday(),
                "season": (stamp.month % 12) // 3,  # 0 winter, 1 spring, 2 summer, 3 autumn
                "T2M_lag_1h": values[index - 1]["T2M"],
                "T2M_lag_24h": values[index - 24]["T2M"],
                "PRECTOTCORR_lag_1h": values[index - 1]["PRECTOTCORR"],
                "PRECTOTCORR_lag_24h": values[index - 24]["PRECTOTCORR"],
                "PS_diff_3h": current["PS"] - values[index - 3]["PS"],
                "T2M_rolling_mean_3h": sum(v["T2M"] for v in values[index - 2:index + 1]) / 3,
                "T2M_rolling_mean_24h": sum(v["T2M"] for v in values[index - 23:index + 1]) / 24,
                "PRECTOTCORR_rolling_sum_24h": sum(v["PRECTOTCORR"] for v in values[index - 23:index + 1]),
                "WD2M_sin": math.sin(math.radians(current["WD2M"])),
                "WD2M_cos": math.cos(math.radians(current["WD2M"])),
            }
            output.append({**rows[index], **derived, "target_timestamp": times[future].isoformat(),
                           "target_temperature": values[future]["T2M"],
                           "target_rainfall": values[future]["PRECTOTCORR"],
                           "rain_flag": int(values[future]["PRECTOTCORR"] > 0.1)})
        audit.event("TRANSFORMED", "Tạo đặc trưng từ dữ liệu đến t và nhãn tại t+h; loại mẫu không đủ điều kiện",
                    input_rows=len(rows), warmup_rows=LOOKBACK, missing_future_rows=horizon,
                    rejected_imputed_windows_or_targets=rejected_quality, output_rows=len(output),
                    horizon_hours=horizon, feature_columns=[*PARAMETERS, *DERIVED_FEATURES],
                    target_columns=TARGETS, rain_threshold_mm_per_hour=0.1)
        if len(output) < min_rows:
            raise ValueError(f"Only {len(output)} valid feature rows; minimum is {min_rows}")
        output_fields = fields + DERIVED_FEATURES + ["target_timestamp", *TARGETS]
        if output_fields != [field["name"] for field in schema["fields"]]:
            raise ValueError("Output columns do not match data schema")
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(output)
        content = stream.getvalue()
        csv_path = output_dir / f"{input_path.stem.removesuffix('_clean')}_features_{horizon}h.csv"
        if csv_path.resolve() == input_path:
            raise ValueError("Cannot overwrite input")
        report = {
            "dataset_id": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "feature_version": VERSION, "schema_version": schema["version"],
            "source": file_info(input_path), "source_metadata": file_info(metadata_path),
            "schema": file_info(SCHEMA_PATH), "horizon_hours": horizon,
            "lookback_hours": LOOKBACK, "time_standard": "UTC+07:00",
            "input_rows": len(rows), "output_rows": len(output), "warmup_rows_removed": LOOKBACK,
            "missing_future_rows_removed": horizon, "quality_rows_removed": rejected_quality,
            "feature_columns": [*PARAMETERS, *DERIVED_FEATURES], "target_columns": TARGETS,
            "start": output[0]["timestamp"], "end": output[-1]["timestamp"],
            "target_end": output[-1]["target_timestamp"],
            "audit_run_id": audit.run_id, "audit_log": str(audit.path),
            "assumption": "All observations through t are available; historical backtesting, not real-time NASA availability.",
            "split_rule": "Split by time; require train target_timestamp < validation start and validation target_timestamp < test start. Never random split.",
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        for path, text in ((csv_path, content), (csv_path.with_suffix(".metadata.json"), json.dumps(report, ensure_ascii=False, indent=2))):
            audit.event("WRITE_PLANNED", "Chuẩn bị ghi dữ liệu đặc trưng hoặc metadata", previous_output=file_info(path))
            write_atomic(path, text)
            audit.event("WRITTEN", "Đã ghi file", **file_info(path))
        return csv_path, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--horizon", type=int, default=1)
    parser.add_argument("--min-rows", type=int, default=10000)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()
    try:
        path, report = build_features(args.input, args.output_dir, args.horizon, args.min_rows, args.log_dir)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Feature engineering failed: {exc}\n")
    print(json.dumps({"output": str(path), "rows": report["output_rows"], "audit_log": report["audit_log"]}, indent=2))


if __name__ == "__main__":
    main()
