"""Persistent per-run audit trail shared by data pipeline stages."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = ROOT / "outputs/logs/data"
LOCAL_TIME = timezone(timedelta(hours=7))


def file_info(path):
    path = Path(path).resolve()
    return {"path": str(path), "exists": path.is_file(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None}


class DataAudit:
    """Start before work and append steps; a missing end means an interrupted run."""

    def __init__(self, stage, configuration, code_path, log_dir=DEFAULT_LOG_DIR):
        self.run_id = datetime.now(LOCAL_TIME).strftime("%Y%m%dT%H%M%S%f") + "_" + uuid4().hex[:8]
        directory = Path(log_dir).resolve()
        if directory.is_relative_to(ROOT / "data/raw"):
            raise ValueError("Audit logs must be outside immutable raw data")
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{self.run_id}_{stage}.log"
        self.path.touch(exist_ok=False)
        self.event("STARTED", "Bắt đầu xử lý dữ liệu", run_id=self.run_id, stage=stage,
                   configuration=configuration, code=file_info(code_path))

    def event(self, status, message, **details):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(f"[{datetime.now(LOCAL_TIME).isoformat()}] {status}: {message}\n")
            if details:
                stream.write(json.dumps(details, ensure_ascii=False, indent=2, default=str) + "\n")
            stream.flush()

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if error is not None:
            self.event("FAILED", "Xử lý thất bại; xem các bước trước để biết file nào đã được ghi",
                       error_type=kind.__name__, error=str(error))
        else:
            self.event("SUCCEEDED", "Hoàn tất xử lý dữ liệu")
        return False
