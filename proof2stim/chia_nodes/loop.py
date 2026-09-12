"""CHIA graph for the verified Proof2Stim stage sequence."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import ray
from chia.base.ChiaFunction import get

from proof2stim.chia_nodes.stages import (
    baseline_coverage,
    convert_witness,
    decide_acceptance,
    formal_solve,
    replay_stimulus,
)
from proof2stim.manifest import load_manifest, sha256_file
from proof2stim.pipeline import PipelineError


def run_preflight(manifest: dict[str, Any], project_root: Path) -> None:
    """Run manifest-declared dependency checks in the CHIA driver."""

    for command in manifest["pipeline"]["preflight"]:
        returncode = subprocess.run(command, cwd=project_root, check=False).returncode
        if returncode:
            raise PipelineError(
                f"preflight command failed with exit code {returncode}: {' '.join(command)}"
            )


def run_chia_graph(
    manifest_path: Path,
    project_root: Path,
    profile_dir: Path | None = None,
) -> dict[str, Any]:
    """Dispatch the Proof2Stim graph and return its accepted terminal result."""

    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    root = project_root.resolve()
    manifest_file = manifest_path.resolve()
    manifest = load_manifest(manifest_file)
    run_preflight(manifest, root)
    manifest_argument = str(manifest_file)
    root_argument = str(root)
    tag_prefix = f"{manifest['benchmark']['id']}:{manifest['targets'][0]['id']}"

    baseline_ref = baseline_coverage.chia_remote(
        manifest_argument,
        root_argument,
        _chia_tag=f"{tag_prefix}:baseline",
    )
    formal_ref = formal_solve.chia_remote(
        manifest_argument,
        root_argument,
        _chia_tag=f"{tag_prefix}:formal",
    )
    witness_ref = convert_witness.chia_remote(
        manifest_argument,
        root_argument,
        formal_ref,
        _chia_tag=f"{tag_prefix}:normalize",
    )
    replay_ref = replay_stimulus.chia_remote(
        manifest_argument,
        root_argument,
        witness_ref,
        _chia_tag=f"{tag_prefix}:replay",
    )
    acceptance = get(
        decide_acceptance.chia_remote(
            manifest_argument,
            root_argument,
            baseline_ref,
            formal_ref,
            replay_ref,
            _chia_tag=f"{tag_prefix}:acceptance",
        )
    )

    verdict_path = root / manifest["pipeline"]["acceptance_result"]
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    if not verdict.get("accepted"):
        raise PipelineError(f"CHIA graph produced a rejected verdict: {verdict_path}")
    stages = [
        get(baseline_ref),
        get(formal_ref),
        get(witness_ref),
        get(replay_ref),
        acceptance,
    ]
    result = {
        "schema_version": "1.0",
        "benchmark_id": manifest["benchmark"]["id"],
        "target_id": manifest["targets"][0]["id"],
        "accepted": True,
        "started_utc": started_at.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "duration_seconds": round(time.perf_counter() - started_clock, 6),
        "orchestrator": {
            "name": "CHIA",
            "version": version("chialoops"),
            "commit": "a2c4dae46528055efa59444d54832336851f633f",
            "ray_version": ray.__version__,
        },
        "profile_directory": (
            str(profile_dir.resolve().relative_to(root)) if profile_dir else None
        ),
        "stages": stages,
        "artifacts": {
            "acceptance_result": str(verdict_path.relative_to(root)),
            "acceptance_sha256": sha256_file(verdict_path),
        },
        "model_usage": [],
        "estimated_model_cost_usd": 0.0,
    }
    output = root / manifest["pipeline"]["chia_run_record"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
