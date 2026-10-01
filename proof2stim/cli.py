"""Proof2Stim command-line interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import jsonschema

from proof2stim.assistance.proposal import (
    ProposalValidationError,
    prepare_request,
    project_file,
    relative_path,
)
from proof2stim.assistance.vertex import invoke_vertex_proposal
from proof2stim.manifest import ManifestError, load_manifest, sha256_file, verify_sources
from proof2stim.pipeline import PipelineError, run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _output_path(root: Path, value: Path) -> Path:
    path = value.resolve() if value.is_absolute() else (root / value).resolve()
    if not path.is_relative_to(root):
        raise ProposalValidationError(f"output path escapes project root: {value}")
    return path


def _run(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = project_root / manifest_path
    try:
        manifest = load_manifest(manifest_path)
        source_errors = verify_sources(manifest, project_root)
        if source_errors:
            raise PipelineError("; ".join(source_errors))
        record = run_pipeline(
            manifest,
            project_root,
            use_cache=not args.no_cache,
            skip_preflight=args.skip_preflight,
        )
    except (ManifestError, PipelineError) as exc:
        print(f"FAILED: {exc}")
        return 1

    hits = sum(stage["cache_hit"] for stage in record["stages"])
    total = len(record["stages"])
    print(
        f"ACCEPTED: {record['benchmark_id']}/{record['target_id']} "
        f"({hits}/{total} cache hits, {record['duration_seconds']:.3f}s)"
    )
    return 0


def _prepare_gemini(args: argparse.Namespace) -> int:
    root = args.project_root.resolve()
    try:
        request = prepare_request(
            args.manifest,
            args.target_id,
            args.baseline,
            project_root=root,
        )
        output = _output_path(root, args.output)
        _write_json(output, request)
    except (ManifestError, OSError, ProposalValidationError) as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"PREPARED: {relative_path(root, output)}")
    print(f"PROMPT SHA-256: {request['prompt_sha256']}")
    print(f"ESTIMATED INPUT TOKENS: {request['estimated_input_tokens']}")
    print(f"CONSERVATIVE INPUT TOKEN BOUND: {request['conservative_input_token_bound']}")
    print("MODEL CALL: not performed")
    return 0


def _run_gemini(args: argparse.Namespace) -> int:
    if not args.confirm_paid_call:
        print("REFUSED: pass --confirm-paid-call after reviewing project, model, rates, and cap")
        return 2
    root = args.project_root.resolve()
    try:
        request_path = project_file(root, args.request)
        request = json.loads(request_path.read_text(encoding="utf-8"))
        invocation = invoke_vertex_proposal(
            request,
            project=args.project,
            location=args.location,
            model=args.model,
            input_usd_per_million=args.input_usd_per_million,
            output_usd_per_million=args.output_usd_per_million,
            cost_cap_usd=args.cost_cap_usd,
            project_root=root,
        )
        output_dir = _output_path(root, args.output_dir)
        proposal_path = output_dir / "proposal.json"
        _write_json(proposal_path, invocation["proposal"])
        run = {
            "schema_version": "1.0",
            "status": "validated_proposal",
            "benchmark_id": request["benchmark_id"],
            "target_id": request["target_id"],
            "provider": "google-vertex-ai",
            "model": args.model,
            "project": args.project,
            "location": args.location,
            "prompt_version": request["prompt_version"],
            "prompt_sha256": request["prompt_sha256"],
            "response_schema_sha256": request["response_schema_sha256"],
            "started_utc": invocation["started_utc"],
            "finished_utc": invocation["finished_utc"],
            "latency_seconds": invocation["latency_seconds"],
            "generation_config": request["generation_config"],
            "provider_controls": request["provider_controls"],
            "usage": invocation["usage"],
            "pricing_usd_per_million_tokens": {
                "input": args.input_usd_per_million,
                "output": args.output_usd_per_million,
            },
            "estimated_cost_usd": invocation["estimated_cost_usd"],
            "cost_cap_usd": args.cost_cap_usd,
            "artifacts": {
                "request": relative_path(root, request_path),
                "request_sha256": sha256_file(request_path),
                "proposal": relative_path(root, proposal_path),
                "proposal_sha256": sha256_file(proposal_path),
            },
            "validation_checks": invocation["validation_checks"],
            "final_acceptance": "requires_formal_and_replay",
        }
        run_schema = json.loads(
            (root / "schemas/model-proposal-run-v1.schema.json").read_text(encoding="utf-8")
        )
        jsonschema.validate(run, run_schema)
        run_path = output_dir / "run.json"
        _write_json(run_path, run)
    except (
        json.JSONDecodeError,
        jsonschema.ValidationError,
        ManifestError,
        OSError,
        ProposalValidationError,
    ) as exc:
        print(f"FAILED: {exc}")
        return 1
    print(f"VALIDATED PROPOSAL: {relative_path(root, proposal_path)}")
    print(f"MODEL RUN: {relative_path(root, run_path)}")
    print(f"ESTIMATED COST: ${run['estimated_cost_usd']:.6f}")
    print("ACCEPTANCE: pending formal solve and independent replay")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proof2stim")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="execute a manifest's verified pipeline")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--project-root", type=Path, default=Path.cwd())
    run.add_argument("--no-cache", action="store_true", help="execute every stage")
    run.add_argument(
        "--skip-preflight",
        action="store_true",
        help="skip configured dependency checks",
    )
    run.set_defaults(handler=_run)

    prepare = subparsers.add_parser(
        "prepare-gemini",
        help="prepare a deterministic Gemini request without calling a model",
    )
    prepare.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifests/nvdla_apb2csb.yaml"),
    )
    prepare.add_argument("--target-id", default="delayed_read_roundtrip_v1")
    prepare.add_argument(
        "--baseline",
        type=Path,
        default=Path("results/nvdla_apb2csb/baseline.json"),
    )
    prepare.add_argument(
        "--output",
        type=Path,
        default=Path("runs/nvdla_apb2csb/gemini/target-harness-v1/request.json"),
    )
    prepare.add_argument("--project-root", type=Path, default=Path.cwd())
    prepare.set_defaults(handler=_prepare_gemini)

    gemini = subparsers.add_parser(
        "run-gemini",
        help="make one explicitly confirmed, cost-capped Vertex Gemini request",
    )
    gemini.add_argument("--request", type=Path, required=True)
    gemini.add_argument("--project", required=True)
    gemini.add_argument("--location", required=True)
    gemini.add_argument("--model", required=True)
    gemini.add_argument("--input-usd-per-million", type=float, required=True)
    gemini.add_argument("--output-usd-per-million", type=float, required=True)
    gemini.add_argument("--cost-cap-usd", type=float, required=True)
    gemini.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/nvdla_apb2csb/gemini/target-harness-v1"),
    )
    gemini.add_argument("--project-root", type=Path, default=Path.cwd())
    gemini.add_argument("--confirm-paid-call", action="store_true")
    gemini.set_defaults(handler=_run_gemini)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
