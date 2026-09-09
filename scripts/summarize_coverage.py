#!/usr/bin/env python3
"""Create a compact deterministic result from a Verilator coverage database."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proof2stim.coverage import summarize_coverage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=("baseline", "replay"))
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--target-hit", action="store_true")
    args = parser.parse_args()

    summary = summarize_coverage(args.coverage)
    result = {
        "schema_version": "1.0",
        "kind": args.kind,
        "benchmark_id": args.benchmark_id,
        "target": {"id": args.target_id, "hit": args.target_hit},
        "coverage": {
            "source": args.coverage.name,
            **summary,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
