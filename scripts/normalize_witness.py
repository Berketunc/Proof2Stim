#!/usr/bin/env python3
"""Normalize a Yosys witness into schema-valid Proof2Stim JSON."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from proof2stim.manifest import load_manifest
from proof2stim.witness import normalize_yosys_witness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("witness", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--target-spec", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--solver", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--witness-copy", type=Path)
    args = parser.parse_args()

    stimulus = normalize_yosys_witness(
        args.witness,
        load_manifest(args.manifest),
        args.target_spec,
        args.schema,
        solver=args.solver,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(stimulus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.witness_copy:
        args.witness_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.witness, args.witness_copy)
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
