"""Clean Hanoi NASA POWER data, preserving stable IDs and source lineage."""

import argparse
import bisect
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from src.data_collection.nasa_power import LATITUDE, LONGITUDE, PARAMETERS
from src.data_audit import DataAudit, DEFAULT_LOG_DIR, file_info

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/raw/nasa_power/hanoi_hourly_20230101_20241231.csv"
DEFAULT_OUTPUT = ROOT / "data/cleaned/nasa_power"
STATION_ID = "NASA_POWER_HANOI_21.0285_105.8542"
VERSION = "1.1"
# Vietnam uses UTC+07:00 throughout the dataset; no external tzdata required.
VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


def record_id(timestamp):
    """Identity does not depend on row order, file name or weather values."""
    timestamp = normalize_timestamp(timestamp).strftime("%Y-%m-%dT%H:00:00Z")
    return str(uuid5(NAMESPACE_URL, f"nasa-power/hourly/{STATION_ID}/{timestamp}"))


def normalize_timestamp(value):
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include an explicit timezone")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise ValueError("Timestamp must be aligned to an exact hour")
    return parsed


def numeric_value(value, parameter, fill_values):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result in fill_values:
        return None
    if parameter == "T2M" and result < -273.15:
        return None
    if parameter == "RH2M" and not 0 <= result <= 100:
        return None
    if parameter == "WD2M":
        return result % 360 if 0 <= result <= 360 else None
    if parameter == "PS" and result <= 0:
        return None
    if parameter in ("PRECTOTCORR", "WS2M", "ALLSKY_SFC_SW_DWN") and result < 0:
        return None
    return result


def fill_series(values, circular=False):
    """Interpolate inside gaps; use nearest valid value at either edge.

    Wind direction follows the shortest angular path across north (0 degrees).
    """
    valid = [index for index, value in enumerate(values) if value is not None]
    if not valid:
        raise ValueError("Cannot impute a parameter with no valid observations")
    result = list(values)
    for index, value in enumerate(values):
        if value is not None:
            continue
        position = bisect.bisect_left(valid, index)
        if position == 0:
            result[index] = values[valid[0]]  # bfill at the leading edge
        elif position == len(valid):
            result[index] = values[valid[-1]]  # ffill at the trailing edge
        else:
            left, right = valid[position - 1], valid[position]
            difference = values[right] - values[left]
            if circular:
                difference = (difference + 180) % 360 - 180
            interpolated = values[left] + difference * (index - left) / (right - left)
            result[index] = interpolated % 360 if circular else interpolated
    return result


def write_atomic(path, content):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        stream.write(content)
    temporary.replace(path)


def clean(input_path=DEFAULT_INPUT, output_dir=DEFAULT_OUTPUT, min_rows=10000, log_dir=DEFAULT_LOG_DIR):
    with DataAudit("cleaning", {"input": str(input_path), "output_dir": str(output_dir),
                               "min_rows": min_rows, "cleaning_version": VERSION}, __file__, log_dir) as audit:
        return _clean(input_path, output_dir, min_rows, audit)


def _clean(input_path, output_dir, min_rows, audit):
    input_path, output_dir = Path(input_path).resolve(), Path(output_dir).resolve()
    if min_rows < 1:
        raise ValueError("min_rows must be positive")
    raw_bytes = input_path.read_bytes()
    source_hash = hashlib.sha256(raw_bytes).hexdigest()
    audit.event("INPUT", "Đọc dữ liệu nguồn, không chỉnh sửa file gốc", **file_info(input_path))
    metadata_path = input_path.with_suffix(".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    fill_values = {-999.0}
    fill_values.update(source["fill_value"] for source in metadata.get("sources", []) if source.get("fill_value") is not None)
    reader = csv.DictReader(io.StringIO(raw_bytes.decode("utf-8-sig"), newline=""))
    required = {"timestamp", "city", "latitude", "longitude", *PARAMETERS}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(f"Missing CSV columns: {sorted(required - set(reader.fieldnames or []))}")
    observations, lineage = {}, {}
    input_rows = duplicates = wind_normalized = 0
    for row_number, raw in enumerate(reader, start=1):
        input_rows += 1
        if None in raw:
            raise ValueError(f"Malformed CSV record {row_number}")
        if raw["city"].strip() != "Hanoi" or not (
            math.isclose(float(raw["latitude"]), LATITUDE, abs_tol=0.000001)
            and math.isclose(float(raw["longitude"]), LONGITUDE, abs_tol=0.000001)
        ):
            raise ValueError(f"Record {row_number}: expected the configured Hanoi location")
        timestamp = normalize_timestamp(raw["timestamp"])
        try:
            wind_normalized += float(raw["WD2M"]) == 360
        except (TypeError, ValueError):
            pass
        values = tuple(numeric_value(raw[key], key, fill_values) for key in PARAMETERS)
        if timestamp in observations:
            if observations[timestamp] != values:
                raise ValueError(f"Conflicting duplicate at {timestamp.isoformat()}")
            duplicates += 1
            lineage[timestamp].append(row_number)
        else:
            observations[timestamp] = values
            lineage[timestamp] = [row_number]
    if not observations:
        raise ValueError("Input CSV has no observations")
    first, last = min(observations), max(observations)
    if metadata.get("start") and metadata.get("end"):
        first = datetime.fromisoformat(metadata["start"]).replace(tzinfo=timezone.utc)
        last = datetime.fromisoformat(metadata["end"]).replace(tzinfo=timezone.utc) + timedelta(hours=23)
        if first > last or min(observations) < first or max(observations) > last:
            raise ValueError("Input timestamps conflict with metadata date range")
    timestamps = [first + timedelta(hours=i) for i in range(int((last - first).total_seconds() // 3600) + 1)]
    if len(observations) < min_rows:
        raise ValueError(f"Only {len(observations)} unique observed rows; minimum is {min_rows}")
    audit.event("VALIDATED", "Kiểm tra vị trí Hà Nội, chuẩn hóa thời điểm, sắp xếp và loại dòng trùng giống nhau",
                input_rows=input_rows, unique_observed_rows=len(observations), duplicates_removed=duplicates,
                inserted_hours=len(timestamps)-len(observations), wind_360_to_0_input_rows=wind_normalized)
    columns = {
        key: [observations.get(stamp, (None,) * len(PARAMETERS))[index] for stamp in timestamps]
        for index, key in enumerate(PARAMETERS)
    }
    cleaned = {}
    for key in PARAMETERS:
        try:
            cleaned[key] = fill_series(columns[key], circular=key == "WD2M")
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from exc
    fieldnames = ["record_id", "station_id", "timestamp", "city", "latitude", "longitude", *PARAMETERS,
                  "is_imputed", "imputed_columns", "is_inserted_hour", "source_row_numbers"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    imputed_rows = 0
    for index, stamp in enumerate(timestamps):
        timestamp = stamp.astimezone(VIETNAM_TIMEZONE).isoformat(timespec="seconds")
        imputed = [key for key in PARAMETERS if columns[key][index] is None]
        imputed_rows += bool(imputed)
        writer.writerow({
            "record_id": record_id(timestamp), "station_id": STATION_ID, "timestamp": timestamp,
            "city": "Hanoi", "latitude": LATITUDE, "longitude": LONGITUDE,
            **{key: cleaned[key][index] for key in PARAMETERS},
            "is_imputed": int(bool(imputed)), "imputed_columns": "|".join(imputed) or "none",
            "is_inserted_hour": int(stamp not in observations),
            "source_row_numbers": "|".join(map(str, lineage.get(stamp, []))) or "none",
        })
    content = stream.getvalue()
    output_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    stem = f"hanoi_hourly_{first:%Y%m%d}_{last:%Y%m%d}_clean"
    csv_path = output_dir / f"{stem}.csv"
    if csv_path.resolve() == input_path or output_dir.is_relative_to(ROOT / "data/raw"):
        raise ValueError("Cleaned output must not overwrite or reside in raw data")
    report = {
        "dataset_id": f"sha256:{output_hash}", "cleaning_version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(input_path), "source_sha256": source_hash,
        "source_metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest() if metadata_path.exists() else None,
        "station_id": STATION_ID, "record_id_scheme": "UUID5(NAMESPACE_URL, nasa-power/hourly/{station_id}/{UTC timestamp})",
        "time_standard": "UTC+07:00", "timezone": "Asia/Ho_Chi_Minh",
        "start": timestamps[0].astimezone(VIETNAM_TIMEZONE).isoformat(),
        "end": timestamps[-1].astimezone(VIETNAM_TIMEZONE).isoformat(),
        "source_time_standard": "UTC", "filename_date_basis": "source UTC dates",
        "input_rows": input_rows, "unique_observed_rows": len(observations), "output_rows": len(timestamps),
        "duplicates_removed": duplicates, "inserted_hours": len(timestamps) - len(observations),
        "imputed_rows": imputed_rows,
        "imputed_values": {key: sum(value is None for value in columns[key]) for key in PARAMETERS},
        "remaining_missing_values": 0, "minimum_observed_rows": min_rows,
        "meets_10000_observed_rows": len(observations) >= 10000,
        "parameters": metadata.get("parameters", {}),
        "imputation": "Linear interpolation; leading bfill, trailing ffill; shortest angular interpolation for WD2M.",
        "evaluation_note": "Retrospective cleaned data. For forecasting evaluation, split raw data by time first and prevent interpolation across splits or future observations. Do not use imputed values as evaluation ground truth.",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report["audit_run_id"] = audit.run_id
    report["audit_log"] = str(audit.path)
    audit.event("TRANSFORMED", "Hoàn tất làm sạch và chuyển giờ GMT+7 trong bộ nhớ",
                rules={"invalid_values": "Ô trống, không phải số, NaN/Infinity, fill value và ngoài miền vật lý → thiếu",
                       "interpolation": report["imputation"], "timezone": "UTC → GMT+7, giữ cùng thời điểm",
                       "identity": "record_id ổn định theo station_id và thời điểm UTC"},
                output_rows=len(timestamps), imputed_rows=imputed_rows, imputed_values=report["imputed_values"],
                remaining_missing_values=0, start=report["start"], end=report["end"])
    audit.event("WRITE_PLANNED", "Chuẩn bị xuất CSV sạch", previous_output=file_info(csv_path),
                new_sha256=output_hash)
    write_atomic(csv_path, content)
    audit.event("WRITTEN", "Đã ghi CSV sạch", **file_info(csv_path))
    write_atomic(output_dir / f"{stem}.metadata.json", json.dumps(report, ensure_ascii=False, indent=2))
    audit.event("WRITTEN", "Đã ghi metadata và liên kết log", **file_info(output_dir / f"{stem}.metadata.json"))
    return csv_path, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-rows", type=int, default=10000)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()
    try:
        path, report = clean(args.input, args.output_dir, args.min_rows, args.log_dir)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"Cleaning failed: {exc}\n")
    print(json.dumps({"output": str(path), "rows": report["output_rows"],
                      "duplicates_removed": report["duplicates_removed"],
                      "inserted_hours": report["inserted_hours"], "imputed_rows": report["imputed_rows"],
                      "audit_log": report["audit_log"]}, indent=2))


if __name__ == "__main__":
    main()
