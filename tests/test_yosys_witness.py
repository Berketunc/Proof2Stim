import json
import tempfile
import unittest
from pathlib import Path

from proof2stim.witness import normalize_yosys_witness


class YosysWitnessTests(unittest.TestCase):
    def test_excludes_generated_signals_and_zero_fills_unknowns(self) -> None:
        witness = {
            "format": "Yosys Witness Trace",
            "generator": "test",
            "clocks": [],
            "signals": [
                {"path": ["\\data"], "width": 2, "offset": 0, "init_only": False},
                {"path": ["\\pclk"], "width": 1, "offset": 0, "init_only": False},
                {"path": ["\\prstn"], "width": 1, "offset": 0, "init_only": False},
            ],
            # Packed in reverse signal-bit order: reset, clock, data[1:0].
            "steps": [{"bits": "00x1"}, {"bits": "101x"}],
        }
        manifest = {
            "benchmark": {"id": "bench"},
            "upstream": {"commit": "a" * 40},
            "rtl": {"sources": [{"sha256": "b" * 64}]},
            "ports": {"inputs": {"data": 2, "pclk": 1, "prstn": 1}},
            "generated_signals": ["pclk", "prstn"],
            "reset": {"signal": "prstn", "active_level": 0},
            "formal": {"depth": 8},
            "targets": [{"id": "target"}],
        }
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            witness_path = root / "trace.yw"
            target_path = root / "target.yaml"
            schema_path = root / "schema.json"
            witness_path.write_text(json.dumps(witness), encoding="utf-8")
            target_path.write_text("target", encoding="utf-8")
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            stimulus = normalize_yosys_witness(
                witness_path,
                manifest,
                target_path,
                schema_path,
                solver="test-solver",
            )

        self.assertEqual([item["name"] for item in stimulus["input_signals"]], ["data"])
        self.assertEqual(stimulus["metadata"]["reset_steps_omitted"], 1)
        self.assertEqual(
            stimulus["cycles"][0]["assignments"]["data"],
            {"value": "0x2", "known_mask": "0x2"},
        )


if __name__ == "__main__":
    unittest.main()
