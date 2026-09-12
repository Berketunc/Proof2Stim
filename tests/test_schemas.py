import json
import unittest
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_json_schemas_parse(self) -> None:
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(path=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(document["type"], "object")
                self.assertIn("$schema", document)

    def test_latest_pipeline_run_matches_schema(self) -> None:
        schema = json.loads(
            (ROOT / "schemas/pipeline-run-v1.schema.json").read_text(encoding="utf-8")
        )
        run = json.loads(
            (ROOT / "results/nvdla_apb2csb/pipeline_run.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(run, schema)

    @unittest.skipUnless(
        (ROOT / "results/nvdla_apb2csb/chia_run.json").is_file(),
        "CHIA integration result has not been generated",
    )
    def test_latest_chia_run_matches_schema(self) -> None:
        schema = json.loads((ROOT / "schemas/chia-run-v1.schema.json").read_text(encoding="utf-8"))
        run = json.loads((ROOT / "results/nvdla_apb2csb/chia_run.json").read_text(encoding="utf-8"))
        jsonschema.validate(run, schema)


if __name__ == "__main__":
    unittest.main()
