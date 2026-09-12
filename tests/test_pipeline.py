import json
import tempfile
import unittest
from pathlib import Path

from proof2stim.pipeline import PipelineError, run_pipeline


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        (self.root / "input.txt").write_text("first\n", encoding="utf-8")
        (self.root / "target.yaml").write_text("id: target\n", encoding="utf-8")
        self.calls: list[str] = []
        self.manifest = {
            "benchmark": {"id": "example", "license": "test-only"},
            "upstream": {
                "repository": "https://example.invalid/hardware.git",
                "ref": "main",
                "commit": "0" * 40,
                "license_path": "LICENSE",
                "license_sha256": "0" * 64,
            },
            "rtl": {"sources": []},
            "formal": {
                "mode": "cover",
                "depth": 8,
                "timeout_seconds": 10,
                "engine": "test",
            },
            "targets": [{"id": "target", "specification": "target.yaml"}],
            "pipeline": {
                "cache_dir": ".proof2stim/cache",
                "run_record": "results/run.json",
                "run_history_dir": "runs/example",
                "acceptance_result": "results/acceptance.json",
                "versions_file": "versions.lock",
                "simulation_seed": 1,
                "preflight": [],
                "stages": [
                    {
                        "id": "produce",
                        "command": ["produce"],
                        "inputs": ["input.txt"],
                        "outputs": ["work/intermediate.txt"],
                    },
                    {
                        "id": "acceptance",
                        "command": ["accept"],
                        "inputs": ["work/intermediate.txt"],
                        "outputs": ["results/acceptance.json"],
                    },
                ],
            },
        }
        (self.root / "versions.lock").write_text("test versions\n", encoding="utf-8")

    def execute(self, command, root):
        self.calls.append(command[0])
        if command[0] == "produce":
            output = root / "work/intermediate.txt"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text((root / "input.txt").read_text(encoding="utf-8"), encoding="utf-8")
        elif command[0] == "accept":
            output = root / "results/acceptance.json"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('{"accepted": true}\n', encoding="utf-8")
        return 0

    def test_second_run_restores_every_stage_from_cache(self):
        first = run_pipeline(self.manifest, self.root, execute=self.execute)
        self.assertEqual([False, False], [stage["cache_hit"] for stage in first["stages"]])
        self.assertEqual(["produce", "accept"], self.calls)

        (self.root / "work/intermediate.txt").unlink()
        (self.root / "results/acceptance.json").unlink()
        second = run_pipeline(self.manifest, self.root, execute=self.execute)

        self.assertEqual([True, True], [stage["cache_hit"] for stage in second["stages"]])
        self.assertEqual(["produce", "accept"], self.calls)
        self.assertTrue(json.loads((self.root / "results/acceptance.json").read_text())["accepted"])
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(2, len(list((self.root / "runs/example").glob("*.json"))))

    def test_input_change_invalidates_stage_and_downstream(self):
        run_pipeline(self.manifest, self.root, execute=self.execute)
        (self.root / "input.txt").write_text("second\n", encoding="utf-8")

        second = run_pipeline(self.manifest, self.root, execute=self.execute)

        self.assertEqual([False, False], [stage["cache_hit"] for stage in second["stages"]])
        self.assertEqual(["produce", "accept", "produce", "accept"], self.calls)

    def test_rejects_paths_outside_project_root(self):
        self.manifest["pipeline"]["cache_dir"] = "../cache"
        with self.assertRaisesRegex(PipelineError, "escapes project root"):
            run_pipeline(self.manifest, self.root, execute=self.execute)

    def test_corrupt_cache_entry_is_not_reused(self):
        run_pipeline(self.manifest, self.root, execute=self.execute)
        cached = next(
            (self.root / ".proof2stim/cache/example/produce").glob("*/files/work/intermediate.txt")
        )
        cached.write_text("tampered\n", encoding="utf-8")

        second = run_pipeline(self.manifest, self.root, execute=self.execute)

        self.assertEqual([False, True], [stage["cache_hit"] for stage in second["stages"]])
        self.assertEqual(["produce", "accept", "produce"], self.calls)

    def test_failed_stage_is_recorded(self):
        def fail(_command, _root):
            return 7

        with self.assertRaisesRegex(PipelineError, "exit code 7"):
            run_pipeline(self.manifest, self.root, execute=fail)

        record = json.loads((self.root / "results/run.json").read_text(encoding="utf-8"))
        self.assertEqual("failed", record["status"])
        self.assertEqual(1, record["exit_status"])
        self.assertEqual("failed", record["stages"][0]["status"])
        self.assertEqual(7, record["stages"][0]["returncode"])
