"""Prepare deterministic prompts and validate untrusted model proposals."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from proof2stim.manifest import load_manifest, sha256_file, verify_sources

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPT = PROJECT_ROOT / "prompts/gemini/target-harness-v1.md"
DEFAULT_PROPOSAL_SCHEMA = PROJECT_ROOT / "schemas/target-harness-proposal-v1.schema.json"
DEFAULT_REQUEST_SCHEMA = PROJECT_ROOT / "schemas/model-request-v1.schema.json"


class ProposalValidationError(ValueError):
    """Raised when a request or proposal crosses a declared trust boundary."""


def sha256_text(value: str) -> str:
    """Hash a UTF-8 string."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def project_file(root: Path, value: str | Path) -> Path:
    """Resolve an existing file without permitting project-root traversal."""

    path = Path(value)
    candidate = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not candidate.is_relative_to(root):
        raise ProposalValidationError(f"path escapes project root: {value}")
    if not candidate.is_file():
        raise ProposalValidationError(f"required file does not exist: {value}")
    return candidate


def relative_path(root: Path, path: Path) -> str:
    """Return a normalized project-relative artifact path."""

    return str(path.resolve().relative_to(root))


def _numbered_source(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    width = max(4, len(str(len(lines))))
    return "\n".join(f"{number:0{width}d}: {line}" for number, line in enumerate(lines, 1))


def _target_entry(manifest: dict[str, Any], target_id: str) -> dict[str, Any]:
    for entry in manifest["targets"]:
        if entry["id"] == target_id:
            return entry
    raise ProposalValidationError(f"target is not declared by manifest: {target_id}")


def prepare_request(
    manifest_path: Path,
    target_id: str,
    baseline_path: Path,
    *,
    project_root: Path = PROJECT_ROOT,
    prompt_path: Path | None = None,
    proposal_schema_path: Path | None = None,
) -> dict[str, Any]:
    """Build a reviewable request without contacting any model service."""

    root = project_root.resolve()
    manifest_file = project_file(root, manifest_path)
    baseline_file = project_file(root, baseline_path)
    manifest = load_manifest(manifest_file)
    source_errors = verify_sources(manifest, root)
    if source_errors:
        raise ProposalValidationError("; ".join(source_errors))
    assistance = manifest["assistance"]
    if assistance["provider"] != "google-vertex-ai":
        raise ProposalValidationError("manifest assistance provider is not Google Vertex AI")
    prompt_file = project_file(root, prompt_path or assistance["prompt"]["path"])
    proposal_schema_file = project_file(
        root, proposal_schema_path or assistance["response_schema"]["path"]
    )
    if sha256_file(prompt_file) != assistance["prompt"]["sha256"]:
        raise ProposalValidationError("manifest prompt hash does not match prompt file")
    if sha256_file(proposal_schema_file) != assistance["response_schema"]["sha256"]:
        raise ProposalValidationError("manifest response schema hash does not match schema file")

    target = _target_entry(manifest, target_id)
    target_file = project_file(root, target["specification"])
    try:
        target_document = yaml.safe_load(target_file.read_text(encoding="utf-8"))
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))
        proposal_schema = json.loads(proposal_schema_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ProposalValidationError(f"invalid proposal input: {exc}") from exc
    if not isinstance(target_document, dict):
        raise ProposalValidationError("target specification root must be an object")
    if target_document.get("id") != target_id:
        raise ProposalValidationError("target specification identity does not match request")
    if target_document.get("benchmark_id") != manifest["benchmark"]["id"]:
        raise ProposalValidationError("target specification benchmark does not match manifest")
    if baseline.get("benchmark_id") != manifest["benchmark"]["id"]:
        raise ProposalValidationError("baseline benchmark does not match manifest")
    if baseline.get("kind") != "baseline" or baseline.get("target", {}).get("id") != target_id:
        raise ProposalValidationError("baseline target identity does not match request")
    if baseline["target"].get("hit") is not False:
        raise ProposalValidationError("requested target is not an uncovered baseline gap")

    rtl_sections: list[str] = []
    input_artifacts = {
        relative_path(root, manifest_file): sha256_file(manifest_file),
        relative_path(root, target_file): sha256_file(target_file),
        relative_path(root, baseline_file): sha256_file(baseline_file),
        relative_path(root, prompt_file): sha256_file(prompt_file),
        relative_path(root, proposal_schema_file): sha256_file(proposal_schema_file),
    }
    for source in manifest["rtl"]["sources"]:
        source_file = project_file(root, source["path"])
        rtl_sections.append(f"### {source['path']}\n\n{_numbered_source(source_file)}")
        input_artifacts[source["path"]] = sha256_file(source_file)

    context = {
        "benchmark": manifest["benchmark"],
        "rtl": {
            "top": manifest["rtl"]["top"],
            "parameters": manifest["rtl"]["parameters"],
        },
        "clock": manifest["clock"],
        "reset": manifest["reset"],
        "ports": manifest["ports"],
        "formal": manifest["formal"],
        "requested_target": target_document,
        "baseline_coverage": baseline,
    }
    prompt = prompt_file.read_text(encoding="utf-8")
    replacements = {
        "{{CONTEXT_JSON}}": json.dumps(context, indent=2, sort_keys=True),
        "{{RTL_SOURCES}}": "\n\n".join(rtl_sections),
        "{{RESPONSE_SCHEMA_JSON}}": json.dumps(proposal_schema, indent=2, sort_keys=True),
    }
    for marker, value in replacements.items():
        if prompt.count(marker) != 1:
            raise ProposalValidationError(f"prompt must contain exactly one {marker} marker")
        prompt = prompt.replace(marker, value)

    request = {
        "schema_version": "1.0",
        "task": assistance["task"],
        "prompt_version": assistance["prompt"]["version"],
        "benchmark_id": manifest["benchmark"]["id"],
        "target_id": target_id,
        "manifest": relative_path(root, manifest_file),
        "baseline": relative_path(root, baseline_file),
        "created_utc": datetime.now(UTC).isoformat(),
        "prompt": prompt,
        "prompt_sha256": sha256_text(prompt),
        "estimated_input_tokens": max(1, (len(prompt.encode("utf-8")) + 3) // 4),
        "conservative_input_token_bound": len(prompt.encode("utf-8"))
        + len(json.dumps(proposal_schema).encode("utf-8")),
        "response_schema": relative_path(root, proposal_schema_file),
        "response_schema_sha256": sha256_file(proposal_schema_file),
        "input_artifacts": dict(sorted(input_artifacts.items())),
        "generation_config": assistance["generation_config"],
        "provider_controls": assistance["provider_controls"],
    }
    request_schema = json.loads(DEFAULT_REQUEST_SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(request, request_schema)
    except jsonschema.ValidationError as exc:
        raise ProposalValidationError(f"generated request is invalid: {exc.message}") from exc
    return request


def validate_proposal(
    proposal: dict[str, Any],
    request: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
) -> list[str]:
    """Validate model output structurally and against repository-owned facts."""

    root = project_root.resolve()
    schema_file = project_file(root, request["response_schema"])
    if sha256_file(schema_file) != request["response_schema_sha256"]:
        raise ProposalValidationError("response schema hash does not match request")
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(proposal, schema)
    except jsonschema.ValidationError as exc:
        raise ProposalValidationError(f"proposal schema violation: {exc.message}") from exc

    if proposal["benchmark_id"] != request["benchmark_id"]:
        raise ProposalValidationError("proposal benchmark does not match request")
    if proposal["requested_target_id"] != request["target_id"]:
        raise ProposalValidationError("proposal target does not match request")

    manifest = load_manifest(project_file(root, request["manifest"]))
    sources = {
        entry["path"]: project_file(root, entry["path"]) for entry in manifest["rtl"]["sources"]
    }
    for evidence in proposal["rtl_evidence"]:
        source = sources.get(evidence["source_path"])
        if source is None:
            raise ProposalValidationError(
                f"evidence cites undeclared RTL: {evidence['source_path']}"
            )
        line_count = len(source.read_text(encoding="utf-8").splitlines())
        if evidence["start_line"] > evidence["end_line"]:
            raise ProposalValidationError("evidence start_line exceeds end_line")
        if evidence["end_line"] > line_count:
            raise ProposalValidationError(
                f"evidence line {evidence['end_line']} exceeds "
                f"{evidence['source_path']} length {line_count}"
            )

    inputs = set(manifest["ports"]["inputs"])
    known_signals = inputs | set(manifest["ports"]["outputs"])

    def require_known(items: list[dict[str, Any]], allowed: set[str], label: str) -> None:
        for item in items:
            unknown = set(item["signal_refs"]) - allowed
            if unknown:
                names = ", ".join(sorted(unknown))
                raise ProposalValidationError(f"{label} references disallowed signals: {names}")

    require_known(proposal["candidate_targets"], known_signals, "candidate target")
    require_known(proposal["harness"]["assumptions"], inputs, "assumption")
    require_known(proposal["harness"]["assertions"], known_signals, "assertion")
    require_known([proposal["harness"]["cover"]], known_signals, "cover")

    target_ids = [item["id"] for item in proposal["candidate_targets"]]
    property_ids = [
        item["id"] for key in ("assumptions", "assertions") for item in proposal["harness"][key]
    ]
    if len(target_ids) != len(set(target_ids)):
        raise ProposalValidationError("candidate target identifiers must be unique")
    if len(property_ids) != len(set(property_ids)):
        raise ProposalValidationError("assumption and assertion identifiers must be unique")

    return [
        "json_schema",
        "identity",
        "rtl_evidence",
        "signal_scope",
        "identifier_uniqueness",
        "acceptance_boundary",
    ]


def validate_request(
    request: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
) -> None:
    """Reject a malformed, stale, or tampered request before provider access."""

    root = project_root.resolve()
    request_schema = json.loads(DEFAULT_REQUEST_SCHEMA.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(request, request_schema)
    except jsonschema.ValidationError as exc:
        raise ProposalValidationError(f"request schema violation: {exc.message}") from exc
    if sha256_text(request["prompt"]) != request["prompt_sha256"]:
        raise ProposalValidationError("prompt hash does not match request")
    for path, expected_hash in request["input_artifacts"].items():
        if sha256_file(project_file(root, path)) != expected_hash:
            raise ProposalValidationError(f"request input hash mismatch: {path}")
    schema_file = project_file(root, request["response_schema"])
    if sha256_file(schema_file) != request["response_schema_sha256"]:
        raise ProposalValidationError("response schema hash does not match request")
    expected = prepare_request(
        Path(request["manifest"]),
        request["target_id"],
        Path(request["baseline"]),
        project_root=root,
    )
    pinned_fields = (
        "task",
        "prompt_version",
        "benchmark_id",
        "target_id",
        "manifest",
        "baseline",
        "prompt",
        "prompt_sha256",
        "estimated_input_tokens",
        "conservative_input_token_bound",
        "response_schema",
        "response_schema_sha256",
        "input_artifacts",
        "generation_config",
        "provider_controls",
    )
    for field in pinned_fields:
        if request[field] != expected[field]:
            raise ProposalValidationError(f"request field no longer matches pinned inputs: {field}")


def parse_proposal(text: str) -> dict[str, Any]:
    """Parse a JSON-only model response."""

    try:
        proposal = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProposalValidationError(f"model response is not JSON: {exc}") from exc
    if not isinstance(proposal, dict):
        raise ProposalValidationError("model response root must be an object")
    return proposal
