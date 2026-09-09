import unittest
from unittest import mock

from proof2stim import doctor


class DoctorTests(unittest.TestCase):
    def test_missing_required_tool_is_reported(self) -> None:
        spec = doctor.ToolSpec("formal", "does-not-exist", ("--version",), True, "test")
        with mock.patch("proof2stim.doctor.shutil.which", return_value=None):
            result = doctor.inspect_tool(spec)
        self.assertFalse(result.available)
        self.assertTrue(result.required)
        self.assertEqual(result.error, "not found")

    def test_text_report_names_missing_tools(self) -> None:
        report = {
            "ready": False,
            "missing_required": ["yosys"],
            "tools": [
                {
                    "name": "yosys",
                    "required": True,
                    "available": False,
                    "path": None,
                    "version": None,
                    "purpose": "formal",
                    "error": "not found",
                }
            ],
        }
        rendered = doctor.render_text(report)
        self.assertIn("MISSING", rendered)
        self.assertIn("yosys", rendered)


if __name__ == "__main__":
    unittest.main()
