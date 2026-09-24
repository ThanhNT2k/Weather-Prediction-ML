"""Download hourly Hanoi weather: python -m src.data_collection.nasa_power.

Only Python's standard library is required. Raw fill values are preserved;
cleaning and future-target construction belong to the preprocessing package.
"""

import argparse
import calendar
import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import logging
import math
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from uuid import uuid4
from src.data_audit import DataAudit, DEFAULT_LOG_DIR, file_info


API_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PARAMETERS = (
    "T2M", "PRECTOTCORR", "RH2M", "PS", "WS2M", "WD2M",
    "ALLSKY_SFC_SW_DWN",
)
LATITUDE, LONGITUDE = 21.0285, 105.8542
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "data" / "raw" / "nasa_power"
LOGGER = logging.getLogger(__name__)


def month_ranges(start, end):
    """Yield inclusive date ranges without crossing calendar months."""
    while start <= end:
        last = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        stop = min(last, end)
        yield start, stop
        start = stop + timedelta(days=1)


def hour_keys(start, end):
    current = datetime.combine(start, datetime.min.time())
    stop = datetime.combine(end + timedelta(days=1), datetime.min.time())
    while current < stop:
        yield current.strftime("%Y%m%d%H")
        current += timedelta(hours=1)


def request_url(start, end):
    return API_URL + "?" + urlencode({
        "parameters": ",".join(PARAMETERS), "community": "RE",
        "latitude": LATITUDE, "longitude": LONGITUDE,
        "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
        "format": "JSON", "time-standard": "UTC",
    })


def fetch_json(url, timeout=90, retries=3):
    """Retry transient network errors, rate limits and server errors."""
    for attempt in range(retries + 1):
        try:
            with urlopen(url, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code not in (408, 429, 500, 502, 503, 504) or attempt == retries:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                raise RuntimeError(f"NASA HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            if attempt == retries:
                raise RuntimeError(f"NASA request failed: {exc}") from exc
        delay = min(2 ** (attempt + 1), 30)
        LOGGER.warning("Retrying NASA request in %s seconds", delay)
        time.sleep(delay)


def validate_payload(payload, start, end):
    """Reject wrong time standards, absent parameters or incomplete time axes."""
    try:
        series = payload["properties"]["parameter"]
        header = payload["header"]
        metadata = payload["parameters"]
        coordinates = payload["geometry"]["coordinates"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Invalid NASA response: missing data or metadata") from exc
    if header.get("time_standard") != "UTC":
        raise ValueError("NASA response must use UTC")
    if len(coordinates) < 2 or not (
        math.isclose(coordinates[0], LONGITUDE, abs_tol=0.001)
        and math.isclose(coordinates[1], LATITUDE, abs_tol=0.001)
    ):
        raise ValueError("NASA response coordinates do not match Hanoi")
    expected = set(hour_keys(start, end))
    for parameter in PARAMETERS:
        if parameter not in series or parameter not in metadata:
            raise ValueError(f"NASA response missing parameter {parameter}")
        actual = set(series[parameter])
        if actual != expected:
            raise ValueError(
                f"{parameter}: {len(expected - actual)} missing hours, "
                f"{len(actual - expected)} unexpected hours"
            )
        for value in series[parameter].values():
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"Invalid numeric value in {parameter}: {value!r}")
    return series


def atomic_write(path, content):
    """Create raw files only; never modify an existing source artifact."""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            same = json.loads(existing) == json.loads(content)
        elif path.suffix == ".csv":
            same = list(csv.reader(io.StringIO(existing))) == list(csv.reader(io.StringIO(content)))
            # Legacy Windows exports contain blank lines between CSV records.
            if not same:
                same = ([row for row in csv.reader(io.StringIO(existing)) if row]
                        == [row for row in csv.reader(io.StringIO(content)) if row])
        else:
            same = existing == content
        if same:
            return
        raise FileExistsError(f"Raw data is immutable: {path}. Use --refresh for a new snapshot.")
    # Exclusive creation also prevents accidental overwrites from concurrent runs.
    with path.open("x", encoding="utf-8", newline="") as stream:
        stream.write(content)


def collect(start, end, output_dir=DEFAULT_OUTPUT, timeout=90, retries=3, refresh=False, log_dir=DEFAULT_LOG_DIR):
    with DataAudit("collection", {"start": str(start), "end": str(end), "output_dir": str(output_dir),
                                 "timeout": timeout, "retries": retries, "refresh": refresh}, __file__, log_dir) as audit:
        return _collect(start, end, output_dir, timeout, retries, refresh, audit)


def _collect(start, end, output_dir, timeout, retries, refresh, audit):
    if start > end:
        raise ValueError("Start date must not be after end date")
    if start < date(2001, 1, 1) or end >= datetime.now(timezone.utc).date():
        raise ValueError("Dates must be from 2001-01-01 through yesterday (UTC)")
    if timeout <= 0 or retries < 0:
        raise ValueError("Timeout must be positive and retries must be nonnegative")
    output_dir = Path(output_dir)
    if refresh:
        snapshot = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "_" + uuid4().hex[:8]
        output_dir = output_dir / "snapshots" / snapshot
    json_dir = output_dir / "responses"
    json_dir.mkdir(parents=True, exist_ok=True)
    rows, sources = [], []
    missing_values = dict.fromkeys(PARAMETERS, 0)
    parameter_metadata = None
    for first, last in month_ranges(start, end):
        filename = f"hanoi_{first:%Y%m%d}_{last:%Y%m%d}_UTC.json"
        path = json_dir / filename
        url = request_url(first, last)
        cached = path.exists() and not refresh
        LOGGER.info("%s %s to %s", "Reading cache" if cached else "Downloading", first, last)
        payload = json.loads(path.read_text(encoding="utf-8")) if cached else fetch_json(url, timeout, retries)
        series = validate_payload(payload, first, last)
        if not cached:
            atomic_write(path, json.dumps(payload, ensure_ascii=False))
        audit.event("SOURCE", "Dùng lại JSON gốc" if cached else "Tải và lưu JSON gốc mới",
                    url=url, **file_info(path))
        current_metadata = {key: payload["parameters"][key] for key in PARAMETERS}
        if parameter_metadata is not None and current_metadata != parameter_metadata:
            raise ValueError("Parameter metadata changed between chunks; inspect raw responses")
        parameter_metadata = current_metadata
        fill = payload["header"].get("fill_value", -999.0)
        sources.append({"file": str(Path("responses") / filename), "url": url, "fill_value": fill})
        for key in hour_keys(first, last):
            row = {
                "timestamp": datetime.strptime(key, "%Y%m%d%H").strftime("%Y-%m-%dT%H:00:00Z"),
                "city": "Hanoi", "latitude": LATITUDE, "longitude": LONGITUDE,
            }
            for parameter in PARAMETERS:
                value = series[parameter][key]
                row[parameter] = value
                if value is None or value == fill:
                    missing_values[parameter] += 1
            rows.append(row)

    expected_rows = ((end - start).days + 1) * 24
    duplicate_rows = len(rows) - len({(row["city"], row["timestamp"]) for row in rows})
    if len(rows) != expected_rows or duplicate_rows:
        raise ValueError("Collected dataset has missing or duplicate hours")
    stem = f"hanoi_hourly_{start:%Y%m%d}_{end:%Y%m%d}"
    csv_path = output_dir / f"{stem}.csv"
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=["timestamp", "city", "latitude", "longitude", *PARAMETERS])
    writer.writeheader()
    writer.writerows(rows)
    audit.event("WRITE_PLANNED", "Xuất bảng CSV từ JSON, giữ nguyên giá trị NASA",
                previous_output=file_info(csv_path), rows=len(rows), missing_values=missing_values)
    atomic_write(csv_path, stream.getvalue())
    audit.event("OUTPUT", "CSV gốc đã sẵn sàng; không ghi đè file đã có", **file_info(csv_path))
    report = {
        "city": "Hanoi", "latitude": LATITUDE, "longitude": LONGITUDE,
        "start": start.isoformat(), "end": end.isoformat(), "time_standard": "UTC",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows), "expected_rows": expected_rows,
        "missing_hours": 0, "duplicate_rows": duplicate_rows,
        "missing_values": missing_values, "parameters": parameter_metadata,
        "meets_raw_10000_rows": len(rows) >= 10000,
        "note": "Raw data only; recheck the 10000-row requirement after preprocessing and target creation.",
        "sources": sources,
    }
    metadata_path = output_dir / f"{stem}.metadata.json"
    if metadata_path.exists():
        existing_report = json.loads(metadata_path.read_text(encoding="utf-8"))
        report["generated_at"] = existing_report["generated_at"]
    atomic_write(metadata_path, json.dumps(report, ensure_ascii=False, indent=2))
    audit.event("OUTPUT", "Metadata gốc đã sẵn sàng", **file_info(metadata_path))
    LOGGER.info("Saved %s rows to %s; missing values: %s", len(rows), csv_path, missing_values)
    return csv_path, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2023, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2024, 12, 31))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--refresh", action="store_true", help="Download into a new immutable snapshot; preserve existing raw data")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        collect(args.start, args.end, args.output_dir, args.timeout, args.retries, args.refresh, args.log_dir)
    except (ValueError, RuntimeError, OSError) as exc:
        LOGGER.error("Collection failed: %s", exc)
        parser.exit(1)


if __name__ == "__main__":
    main()
