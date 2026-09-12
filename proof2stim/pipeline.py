"""Deterministic, content-addressed execution of Proof2Stim stages."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from proof2stim.manifest import sha256_file

CommandRunner = Callable[[Sequence[str], Path], int]


class PipelineError(RuntimeError):
    """Raised when a pipeline contract or stage fails."""


def _project_path(project_root: Path, relative: str) -> Path:
    root = project_root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise PipelineError(f"path escapes project root: {relative}")
    return candidate


def _file_hashes(project_root: Path, paths: Sequence[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in paths:
        path = _project_path(project_root, relative)
        if not path.is_file():
            raise PipelineError(f"required file does not exist: {relative}")
        hashes[relative] = sha256_file(path)
    return hashes


def _stage_key(stage: Mapping[str, Any], input_hashes: Mapping[str, str]) -> str:
    payload = {
        "schema_version": "1.0",
        "stage_id": stage["id"],
        "command": stage["command"],
        "inputs": input_hashes,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot read JSON artifact {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise PipelineError(f"JSON artifact must contain an object: {path}")
    return document


def _default_execute(command: Sequence[str], project_root: Path) -> int:
    return subprocess.run(command, cwd=project_root, check=False).returncode


def execute_manifest_stage(
    manifest: Mapping[str, Any],
    project_root: Path,
    stage_id: str,
    *,
    dependencies: Sequence[Mapping[str, Any]] = (),
    execute: CommandRunner = _default_execute,
) -> dict[str, Any]:
    """Execute one manifest stage for an external orchestrator such as CHIA."""

    for dependency in dependencies:
        if dependency.get("status") != "passed":
            raise PipelineError(
                f"stage {stage_id} received failed dependency: {dependency.get('id', 'unknown')}"
            )
    try:
        stage = next(item for item in manifest["pipeline"]["stages"] if item["id"] == stage_id)
    except StopIteration as exc:
        raise PipelineError(f"unknown pipeline stage: {stage_id}") from exc

    root = project_root.resolve()
    started = time.perf_counter()
    input_hashes = _file_hashes(root, stage["inputs"])
    key = _stage_key(stage, input_hashes)
    print(f"CHIA RUN: {stage_id} ({key[:12]})", flush=True)
    returncode = execute(stage["command"], root)
    if returncode:
        raise PipelineError(
            f"stage {stage_id} failed with exit code {returncode}: {' '.join(stage['command'])}"
        )
    return {
        "id": stage_id,
        "status": "passed",
        "cache_key": key,
        "command": stage["command"],
        "duration_seconds": round(time.perf_counter() - started, 6),
        "returncode": returncode,
        "inputs": input_hashes,
        "outputs": _file_hashes(root, stage["outputs"]),
    }


def _git_metadata(project_root: Path) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if commit.returncode or status.returncode:
        return {"commit": None, "dirty": None}
    return {"commit": commit.stdout.strip(), "dirty": bool(status.stdout.strip())}


def _cache_valid(
    entry: Path,
    stage_id: str,
    key: str,
    outputs: Sequence[str],
) -> bool:
    metadata_path = entry / "metadata.json"
    if not metadata_path.is_file():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        expected_hashes = metadata["outputs"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return False
    if metadata.get("stage_id") != stage_id or metadata.get("key") != key:
        return False
    if set(expected_hashes) != set(outputs):
        return False
    for relative in outputs:
        cached = entry / "files" / relative
        if not cached.is_file() or sha256_file(cached) != expected_hashes[relative]:
            return False
    return True


def _restore_outputs(entry: Path, project_root: Path, outputs: Sequence[str]) -> None:
    for relative in outputs:
        source = entry / "files" / relative
        destination = _project_path(project_root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _store_outputs(
    entry: Path,
    project_root: Path,
    stage_id: str,
    key: str,
    input_hashes: Mapping[str, str],
    outputs: Sequence[str],
) -> dict[str, str]:
    output_hashes = _file_hashes(project_root, outputs)
    if entry.exists():
        shutil.rmtree(entry)
    for relative in outputs:
        destination = entry / "files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_project_path(project_root, relative), destination)
    metadata = {
        "schema_version": "1.0",
        "stage_id": stage_id,
        "key": key,
        "inputs": dict(input_hashes),
        "outputs": output_hashes,
    }
    (entry / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_hashes


def _write_run_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_pipeline(
    manifest: Mapping[str, Any],
    project_root: Path,
    *,
    use_cache: bool = True,
    skip_preflight: bool = False,
    execute: CommandRunner = _default_execute,
) -> dict[str, Any]:
    """Run configured stages and return the machine-readable run record."""

    if "pipeline" not in manifest:
        raise PipelineError("manifest has no pipeline configuration")
    pipeline = manifest["pipeline"]
    root = project_root.resolve()
    cache_root = _project_path(root, pipeline["cache_dir"])
    run_record_path = _project_path(root, pipeline["run_record"])
    run_history_dir = _project_path(root, pipeline["run_history_dir"])
    acceptance_path = _project_path(root, pipeline["acceptance_result"])
    versions_path = _project_path(root, pipeline["versions_file"])
    stages = pipeline["stages"]
    stage_ids = [stage["id"] for stage in stages]
    if len(stage_ids) != len(set(stage_ids)):
        raise PipelineError("pipeline stage ids must be unique")

    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    run_id = (
        f"{manifest['benchmark']['id']}-{started_at.strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    target_path = _project_path(root, manifest["targets"][0]["specification"])
    record: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "benchmark_id": manifest["benchmark"]["id"],
        "target_id": manifest["targets"][0]["id"],
        "started_utc": started_at.isoformat(),
        "status": "running",
        "accepted": False,
        "cache_enabled": use_cache,
        "preflight": [],
        "stages": [],
        "model_usage": [],
        "estimated_model_cost_usd": 0.0,
        "git": _git_metadata(root),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "configuration": {
            "simulation_seed": pipeline["simulation_seed"],
            "formal": manifest["formal"],
            "versions_file": pipeline["versions_file"],
            "versions_sha256": sha256_file(versions_path),
        },
        "upstream": {
            "repository": manifest["upstream"]["repository"],
            "ref": manifest["upstream"]["ref"],
            "commit": manifest["upstream"]["commit"],
            "license": manifest["benchmark"]["license"],
            "license_path": manifest["upstream"]["license_path"],
            "license_sha256": manifest["upstream"]["license_sha256"],
            "sources": manifest["rtl"]["sources"],
        },
        "target_specification": {
            "path": manifest["targets"][0]["specification"],
            "sha256": sha256_file(target_path),
        },
    }

    try:
        if not skip_preflight:
            for command in pipeline["preflight"]:
                command_started = time.perf_counter()
                print(f"PREFLIGHT: {' '.join(command)}", flush=True)
                returncode = execute(command, root)
                record["preflight"].append(
                    {
                        "command": command,
                        "duration_seconds": round(time.perf_counter() - command_started, 6),
                        "returncode": returncode,
                    }
                )
                if returncode:
                    raise PipelineError(
                        f"preflight command failed with exit code {returncode}: {' '.join(command)}"
                    )

        for stage in stages:
            stage_started = time.perf_counter()
            stage_id = stage["id"]
            input_hashes = _file_hashes(root, stage["inputs"])
            key = _stage_key(stage, input_hashes)
            entry = cache_root / manifest["benchmark"]["id"] / stage_id / key
            cache_hit = use_cache and _cache_valid(entry, stage_id, key, stage["outputs"])
            stage_record = {
                "id": stage_id,
                "status": "running",
                "cache_hit": cache_hit,
                "cache_key": key,
                "command": stage["command"],
                "duration_seconds": 0.0,
                "returncode": None,
                "inputs": input_hashes,
                "outputs": {},
            }
            if cache_hit:
                print(f"CACHE HIT: {stage_id} ({key[:12]})", flush=True)
                _restore_outputs(entry, root, stage["outputs"])
                output_hashes = _file_hashes(root, stage["outputs"])
            else:
                print(f"RUN: {stage_id} ({key[:12]})", flush=True)
                returncode = execute(stage["command"], root)
                stage_record["returncode"] = returncode
                if returncode:
                    stage_record["status"] = "failed"
                    stage_record["duration_seconds"] = round(time.perf_counter() - stage_started, 6)
                    record["stages"].append(stage_record)
                    raise PipelineError(
                        f"stage {stage_id} failed with exit code {returncode}: "
                        f"{' '.join(stage['command'])}"
                    )
                output_hashes = _file_hashes(root, stage["outputs"])
                if use_cache:
                    output_hashes = _store_outputs(
                        entry,
                        root,
                        stage_id,
                        key,
                        input_hashes,
                        stage["outputs"],
                    )
            stage_record["status"] = "passed"
            stage_record["duration_seconds"] = round(time.perf_counter() - stage_started, 6)
            stage_record["outputs"] = output_hashes
            record["stages"].append(stage_record)

        acceptance = _load_json(acceptance_path)
        record["accepted"] = bool(acceptance.get("accepted"))
        record["status"] = "passed" if record["accepted"] else "rejected"
        if not record["accepted"]:
            raise PipelineError(f"acceptance result rejected the run: {acceptance_path}")
    except PipelineError as exc:
        record["status"] = "failed" if record["status"] == "running" else record["status"]
        record["error"] = str(exc)
        raise
    finally:
        record["duration_seconds"] = round(time.perf_counter() - started_clock, 6)
        record["finished_utc"] = datetime.now(UTC).isoformat()
        record["exit_status"] = 0 if record["status"] == "passed" else 1
        _write_run_record(run_record_path, record)
        _write_run_record(run_history_dir / f"{run_id}.json", record)

    return record
