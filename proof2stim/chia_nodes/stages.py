"""CHIA nodes wrapping Proof2Stim's deterministic manifest stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chia.base.ChiaFunction import ChiaFunction
from chia.trace.profiler import get_profiler

from proof2stim.manifest import load_manifest, verify_sources
from proof2stim.pipeline import PipelineError, execute_manifest_stage

NODE_OPTIONS = {
    "num_cpus": 1,
    "resources": {"proof2stim": 1},
    "max_retries": 0,
}


def _unwrap_dependencies(
    dependencies: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    """Unwrap values passed directly from profiled upstream CHIA object refs."""

    profiler = get_profiler()
    return tuple(profiler.on_remote_complete(dependency) for dependency in dependencies)


def _run(
    manifest_path: str,
    project_root: str,
    stage_id: str,
    dependencies: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    manifest_file = Path(manifest_path)
    if not manifest_file.is_absolute():
        manifest_file = root / manifest_file
    manifest = load_manifest(manifest_file)
    source_errors = verify_sources(manifest, root)
    if source_errors:
        raise PipelineError("; ".join(source_errors))
    result = execute_manifest_stage(
        manifest,
        root,
        stage_id,
        dependencies=_unwrap_dependencies(dependencies),
    )
    get_profiler().add_info(
        {
            "proof2stim_stage": stage_id,
            "cache_key": result["cache_key"],
            "output_hashes": result["outputs"],
        }
    )
    return result


@ChiaFunction(**NODE_OPTIONS)
def baseline_coverage(manifest_path: str, project_root: str) -> dict[str, Any]:
    """Run the deterministic seed regression and collect baseline coverage."""

    return _run(manifest_path, project_root, "baseline")


@ChiaFunction(**NODE_OPTIONS)
def formal_solve(manifest_path: str, project_root: str) -> dict[str, Any]:
    """Run bounded cover and the separate bounded safety task."""

    return _run(manifest_path, project_root, "formal")


@ChiaFunction(**NODE_OPTIONS)
def convert_witness(
    manifest_path: str,
    project_root: str,
    formal_result: dict[str, Any],
) -> dict[str, Any]:
    """Normalize a successful formal witness into deterministic stimulus JSON."""

    return _run(manifest_path, project_root, "normalize", (formal_result,))


@ChiaFunction(**NODE_OPTIONS)
def replay_stimulus(
    manifest_path: str,
    project_root: str,
    witness_result: dict[str, Any],
) -> dict[str, Any]:
    """Replay normalized stimulus on the original RTL and run independent checks."""

    return _run(manifest_path, project_root, "replay", (witness_result,))


@ChiaFunction(**NODE_OPTIONS)
def decide_acceptance(
    manifest_path: str,
    project_root: str,
    baseline_result: dict[str, Any],
    formal_result: dict[str, Any],
    replay_result: dict[str, Any],
) -> dict[str, Any]:
    """Combine formal, replay, semantic, legality, data, and coverage gates."""

    return _run(
        manifest_path,
        project_root,
        "acceptance",
        (baseline_result, formal_result, replay_result),
    )
