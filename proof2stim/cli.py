"""Proof2Stim command-line interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from proof2stim.manifest import ManifestError, load_manifest, verify_sources
from proof2stim.pipeline import PipelineError, run_pipeline


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
