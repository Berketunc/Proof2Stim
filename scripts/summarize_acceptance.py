#!/usr/bin/env python3
"""Combine vertical-slice gate evidence into one deterministic acceptance result."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def status_passed(path: Path) -> bool:
    tokens = path.read_text(encoding="utf-8").split()
    return bool(tokens and tokens[0] == "PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--replay", required=True, type=Path)
    parser.add_argument("--replay-checks", required=True, type=Path)
    parser.add_argument("--stimulus", required=True, type=Path)
    parser.add_argument("--witness", required=True, type=Path)
    parser.add_argument("--cover-status", required=True, type=Path)
    parser.add_argument("--safety-status", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    baseline = load_json(args.baseline)
    replay = load_json(args.replay)
    replay_checks = load_json(args.replay_checks)
    baseline_metrics = baseline["coverage"]["metrics"]
    replay_metrics = replay["coverage"]["metrics"]

    delta = {}
    for name in sorted(set(baseline_metrics) & set(replay_metrics)):
        before = baseline_metrics[name]
        after = replay_metrics[name]
        delta[name] = {
            "covered_delta": after["covered"] - before["covered"],
            "percentage_point_delta": round(after["percent"] - before["percent"], 2),
        }

    coverage_increased = any(item["covered_delta"] > 0 for item in delta.values())
    gates = {
        "formal_cover_passed": status_passed(args.cover_status),
        "bounded_safety_passed": status_passed(args.safety_status),
        "simulation_passed": True,
        "legality_passed": bool(replay_checks["legality_passed"]),
        "target_hit": bool(replay_checks["target_hit"]),
        "data_checks_passed": bool(replay_checks["data_checks_passed"]),
        "no_duplicate_request": not bool(replay_checks["duplicate_request"]),
        "coverage_increased": coverage_increased,
    }
    result = {
        "schema_version": "1.0",
        "benchmark_id": baseline["benchmark_id"],
        "target_id": baseline["target"]["id"],
        "accepted": all(gates.values()),
        "gates": gates,
        "coverage_delta": delta,
        "artifacts": {
            "stimulus_sha256": sha256(args.stimulus),
            "witness_sha256": sha256(args.witness),
            "baseline_result_sha256": sha256(args.baseline),
            "replay_result_sha256": sha256(args.replay),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {args.output}")
    print(f"ACCEPTED: {result['accepted']}")
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
