import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "summarize_acceptance.py"
SPEC = importlib.util.spec_from_file_location("summarize_acceptance", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AcceptanceSummaryTests(unittest.TestCase):
    def test_symbiyosys_pass_status_accepts_trailing_counters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "status"
            status.write_text("PASS 0 1\n", encoding="utf-8")
            self.assertTrue(MODULE.status_passed(status))

    def test_non_pass_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "status"
            status.write_text("UNKNOWN 4 0\n", encoding="utf-8")
            self.assertFalse(MODULE.status_passed(status))


if __name__ == "__main__":
    unittest.main()
