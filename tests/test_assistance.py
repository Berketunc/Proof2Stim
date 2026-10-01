import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from proof2stim.assistance.proposal import (
    ProposalValidationError,
    parse_proposal,
    prepare_request,
    validate_proposal,
    validate_request,
)
from proof2stim.assistance.vertex import (
    estimated_cost_usd,
    invoke_vertex_proposal,
    maximum_request_cost_usd,
)
from proof2stim.cli import main

ROOT = Path(__file__).resolve().parents[1]
RTL_PATH = "third_party/nvdla/vmod/nvdla/apb2csb/NV_NVDLA_apb2csb.v"


def valid_proposal() -> dict:
    return {
        "schema_version": "1.0",
        "benchmark_id": "nvdla_apb2csb",
        "requested_target_id": "delayed_read_roundtrip_v1",
        "executive_summary": "Review the delayed read handshake with explicit environment bounds.",
        "rtl_evidence": [
            {
                "source_path": RTL_PATH,
                "start_line": 1,
                "end_line": 2,
                "observation": "The supplied source defines the bridge under review.",
            }
        ],
        "candidate_targets": [
            {
                "id": "delayed_read_with_backpressure_v2",
                "description": "A read request stalls before acceptance and later completes.",
                "baseline_gap": "The baseline does not issue reads.",
                "rationale": "Exercises both request and response wait behavior.",
                "signal_refs": ["psel", "penable", "pwrite", "pready"],
                "event_sequence": [
                    "A selected read enters the APB access phase.",
                    "The CSB request stalls and is then accepted.",
                    "A later response completes the APB transfer.",
                ],
            }
        ],
        "harness": {
            "assumptions": [
                {
                    "id": "legal_apb_select",
                    "description": "APB enable is asserted only while select is asserted.",
                    "signal_refs": ["penable", "psel"],
                    "rationale": "Constrains the environment to legal APB phases.",
                    "overconstraint_risk": "low",
                }
            ],
            "assertions": [
                {
                    "id": "read_completes_on_response",
                    "description": "An active read completes when a response is valid.",
                    "signal_refs": ["psel", "penable", "pwrite", "nvdla2csb_valid", "pready"],
                    "rationale": "Checks the externally visible bridge behavior.",
                }
            ],
            "cover": {
                "description": "Cover a stalled read followed by a delayed response.",
                "signal_refs": [
                    "psel",
                    "penable",
                    "pwrite",
                    "csb2nvdla_ready",
                    "nvdla2csb_valid",
                    "pready",
                ],
                "rationale": "Matches the requested semantic target.",
            },
            "unknowns": ["The external response latency distribution is unspecified."],
            "validation_steps": [
                "Review every assumption for overconstraint.",
                "Run bounded cover and separate safety tasks.",
                "Replay any witness on the original RTL.",
            ],
        },
        "final_acceptance": "requires_tool_validation",
    }


class AssistanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request = prepare_request(
            Path("manifests/nvdla_apb2csb.yaml"),
            "delayed_read_roundtrip_v1",
            Path("results/nvdla_apb2csb/baseline.json"),
            project_root=ROOT,
        )

    def test_request_is_deterministic_except_for_timestamp(self) -> None:
        repeated = prepare_request(
            Path("manifests/nvdla_apb2csb.yaml"),
            "delayed_read_roundtrip_v1",
            Path("results/nvdla_apb2csb/baseline.json"),
            project_root=ROOT,
        )
        self.assertEqual(self.request["prompt_sha256"], repeated["prompt_sha256"])
        self.assertEqual(self.request["prompt"], repeated["prompt"])
        self.assertNotIn("{{CONTEXT_JSON}}", repeated["prompt"])
        self.assertIn("0001:", repeated["prompt"])
        validate_request(repeated, project_root=ROOT)

    def test_tampered_prompt_is_rejected(self) -> None:
        request = copy.deepcopy(self.request)
        request["prompt"] += "tampered"
        with self.assertRaisesRegex(ProposalValidationError, "prompt hash"):
            validate_request(request, project_root=ROOT)

    def test_valid_proposal_passes_all_six_checks(self) -> None:
        checks = validate_proposal(valid_proposal(), self.request, project_root=ROOT)
        self.assertEqual(6, len(checks))

    def test_unknown_signal_is_rejected(self) -> None:
        proposal = valid_proposal()
        proposal["harness"]["cover"]["signal_refs"].append("invented_internal_state")
        with self.assertRaisesRegex(ProposalValidationError, "disallowed signals"):
            validate_proposal(proposal, self.request, project_root=ROOT)

    def test_output_signal_in_assumption_is_rejected(self) -> None:
        proposal = valid_proposal()
        proposal["harness"]["assumptions"][0]["signal_refs"].append("pready")
        with self.assertRaisesRegex(ProposalValidationError, "assumption"):
            validate_proposal(proposal, self.request, project_root=ROOT)

    def test_invalid_evidence_range_is_rejected(self) -> None:
        proposal = valid_proposal()
        proposal["rtl_evidence"][0]["end_line"] = 1_000_000
        with self.assertRaisesRegex(ProposalValidationError, "exceeds"):
            validate_proposal(proposal, self.request, project_root=ROOT)

    def test_duplicate_property_identifier_is_rejected(self) -> None:
        proposal = valid_proposal()
        duplicate = copy.deepcopy(proposal["harness"]["assertions"][0])
        proposal["harness"]["assertions"].append(duplicate)
        with self.assertRaisesRegex(ProposalValidationError, "identifiers must be unique"):
            validate_proposal(proposal, self.request, project_root=ROOT)

    def test_non_json_response_is_rejected(self) -> None:
        with self.assertRaisesRegex(ProposalValidationError, "not JSON"):
            parse_proposal("```json\n{}\n```")


class VertexAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.request = prepare_request(
            Path("manifests/nvdla_apb2csb.yaml"),
            "delayed_read_roundtrip_v1",
            Path("results/nvdla_apb2csb/baseline.json"),
            project_root=ROOT,
        )

    def test_cost_calculation_and_preflight_cap(self) -> None:
        self.assertEqual(0.004, estimated_cost_usd(1000, 1000, 1.0, 3.0))
        client = Mock()
        with self.assertRaisesRegex(ProposalValidationError, "exceeds cap"):
            invoke_vertex_proposal(
                self.request,
                project="test-project",
                location="test-location",
                model="test-model",
                input_usd_per_million=1000.0,
                output_usd_per_million=1000.0,
                cost_cap_usd=0.000001,
                project_root=ROOT,
                client=client,
            )
        client.models.generate_content.assert_not_called()

    def test_mocked_vertex_response_is_validated_and_metered(self) -> None:
        response = Mock()
        response.text = json.dumps(valid_proposal())
        response.usage_metadata = {
            "prompt_token_count": 1200,
            "candidates_token_count": 300,
            "thoughts_token_count": 100,
            "cached_content_token_count": 0,
            "total_token_count": 1500,
        }
        client = Mock()
        client.models.generate_content.return_value = response
        result = invoke_vertex_proposal(
            self.request,
            project="test-project",
            location="test-location",
            model="test-model",
            input_usd_per_million=1.0,
            output_usd_per_million=3.0,
            cost_cap_usd=1.0,
            project_root=ROOT,
            client=client,
        )
        self.assertEqual(0.0024, result["estimated_cost_usd"])
        self.assertEqual(1500, result["usage"]["total_tokens"])
        config = client.models.generate_content.call_args.kwargs["config"]
        self.assertIn("response_json_schema", config)
        self.assertEqual(
            maximum_request_cost_usd(self.request, 1.0, 3.0),
            result["maximum_request_cost_usd"],
        )

    def test_cli_refuses_unconfirmed_call(self) -> None:
        self.assertEqual(
            2,
            main(
                [
                    "run-gemini",
                    "--request",
                    "missing.json",
                    "--project",
                    "p",
                    "--location",
                    "l",
                    "--model",
                    "m",
                    "--input-usd-per-million",
                    "1",
                    "--output-usd-per-million",
                    "1",
                    "--cost-cap-usd",
                    "1",
                ]
            ),
        )

    @patch("proof2stim.cli.invoke_vertex_proposal")
    def test_cli_writes_validated_run_artifacts(self, invoke: Mock) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as directory:
            run_dir = Path(directory)
            request_path = run_dir / "request.json"
            request_path.write_text(
                json.dumps(self.request, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            invoke.return_value = {
                "proposal": valid_proposal(),
                "started_utc": "2026-09-13T10:00:00+00:00",
                "finished_utc": "2026-09-13T10:00:01+00:00",
                "latency_seconds": 1.0,
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "thinking_tokens": 0,
                    "cached_input_tokens": 0,
                    "total_tokens": 150,
                },
                "estimated_cost_usd": 0.00025,
                "validation_checks": [
                    "json_schema",
                    "identity",
                    "rtl_evidence",
                    "signal_scope",
                    "identifier_uniqueness",
                    "acceptance_boundary",
                ],
                "maximum_request_cost_usd": 0.1,
            }
            output_dir = run_dir / "output"
            returncode = main(
                [
                    "run-gemini",
                    "--request",
                    str(request_path.relative_to(ROOT)),
                    "--project",
                    "test-project",
                    "--location",
                    "test-location",
                    "--model",
                    "test-model",
                    "--input-usd-per-million",
                    "1",
                    "--output-usd-per-million",
                    "3",
                    "--cost-cap-usd",
                    "1",
                    "--output-dir",
                    str(output_dir.relative_to(ROOT)),
                    "--confirm-paid-call",
                ]
            )
            self.assertEqual(0, returncode)
            self.assertTrue((output_dir / "proposal.json").is_file())
            run = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual("requires_formal_and_replay", run["final_acceptance"])


if __name__ == "__main__":
    unittest.main()
