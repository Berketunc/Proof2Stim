import tempfile
import unittest
from pathlib import Path

from proof2stim.coverage import summarize_coverage


class VerilatorCoverageTests(unittest.TestCase):
    def test_groups_typed_records_and_ignores_metadata(self) -> None:
        content = (
            "# SystemC::Coverage-3\n"
            "C '\x01f\x02dut.v\x01l\x0210\x01t\x02line\x01o\x02block' 3\n"
            "C '\x01f\x02dut.v\x01l\x0211\x01t\x02line\x01o\x02block' 0\n"
            "C '\x01f\x02dut.v\x01l\x0212\x01t\x02toggle\x01o\x02x:0->1' 1\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.dat"
            path.write_text(content, encoding="utf-8")
            summary = summarize_coverage(path)

        self.assertEqual(summary["metrics"]["line"], {"covered": 1, "total": 2, "percent": 50.0})
        self.assertEqual(
            summary["metrics"]["toggle"],
            {"covered": 1, "total": 1, "percent": 100.0},
        )


if __name__ == "__main__":
    unittest.main()
