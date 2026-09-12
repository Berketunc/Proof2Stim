#!/usr/bin/env python3
"""Run the Proof2Stim stage graph on a local or existing CHIA/Ray cluster."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "manifests/nvdla_apb2csb.yaml",
    )
    parser.add_argument(
        "--address",
        help="Ray address; omit to start an isolated local runtime",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=ROOT / "runs/chia-profiles",
    )
    parser.add_argument(
        "--local-resource-slots",
        type=int,
        default=2,
        help="custom proof2stim resource capacity for an isolated local runtime",
    )
    args = parser.parse_args()

    try:
        import ray
        from chia.trace.profiler import start_collector, stop_collector

        from proof2stim.chia_nodes.loop import run_chia_graph
    except ImportError as exc:
        print("CHIA is not installed; install the project with the 'chia' extra", file=sys.stderr)
        print(f"DETAIL: {exc}", file=sys.stderr)
        return 2

    ray_options = {"ignore_reinit_error": True, "namespace": "proof2stim"}
    if args.address:
        ray_options["address"] = args.address
    else:
        if args.local_resource_slots < 1:
            parser.error("--local-resource-slots must be at least 1")
        ray_options["resources"] = {"proof2stim": args.local_resource_slots}
    ray.init(**ray_options)
    args.profile_dir.mkdir(parents=True, exist_ok=True)
    start_collector(log_dir=str(args.profile_dir))
    try:
        result = run_chia_graph(args.manifest, ROOT, args.profile_dir)
    finally:
        stop_collector()
        ray.shutdown()

    print(f"CHIA ACCEPTED: {result['accepted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
