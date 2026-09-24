"""Audit trails survive failures and retain previous run history."""
from pathlib import Path
import tempfile
import unittest
from src.data_audit import DataAudit
from src.preprocessing.cleaning import clean


class AuditTests(unittest.TestCase):
    def test_each_run_has_separate_log_and_failure_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            with DataAudit("test", {}, __file__, directory) as first:
                first.event("STEP", "Đã kiểm tra dữ liệu", rows=10)
            original = first.path.read_bytes()
            with self.assertRaisesRegex(ValueError, "bad data"):
                with DataAudit("test", {}, __file__, directory) as second:
                    raise ValueError("bad data")
            self.assertNotEqual(first.path, second.path)
            self.assertEqual(first.path.read_bytes(), original)
            self.assertIn("SUCCEEDED", first.path.read_text(encoding="utf-8"))
            failed = second.path.read_text(encoding="utf-8")
            self.assertIn("FAILED", failed)
            self.assertIn("bad data", failed)
            self.assertNotIn("SUCCEEDED", failed)

    def test_clean_failure_creates_log_before_input_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory) / "logs"
            with self.assertRaises(FileNotFoundError):
                clean(Path(directory) / "missing.csv", Path(directory) / "cleaned", log_dir=logs)
            entries = list(logs.glob("*.log"))
            self.assertEqual(len(entries), 1)
            self.assertIn("FileNotFoundError", entries[0].read_text(encoding="utf-8"))

    def test_invalid_log_destination_prevents_data_work(self):
        with tempfile.TemporaryDirectory() as directory:
            not_a_directory = Path(directory) / "file"
            not_a_directory.write_text("keep")
            with self.assertRaises(OSError):
                clean(Path(directory) / "missing.csv", log_dir=not_a_directory)
            self.assertEqual(not_a_directory.read_text(), "keep")
