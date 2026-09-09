"""Normalize Yosys witness traces into portable top-input-only stimulus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


class WitnessError(ValueError):
    """Raised when a formal witness cannot be normalized safely."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _clean_name(path: list[str]) -> str | None:
    if len(path) != 1:
        return None
    return path[0].lstrip("\\")


def _decode_steps(document: dict[str, Any]) -> list[dict[str, tuple[int, int]]]:
    signals = [signal for signal in document["signals"] if not signal["init_only"]]
    expected_bits = sum(int(signal["width"]) for signal in signals)
    decoded: list[dict[str, tuple[int, int]]] = []

    for index, step in enumerate(document["steps"]):
        packed = step["bits"]
        if len(packed) < expected_bits:
            raise WitnessError(
                f"step {index} has {len(packed)} bits; expected at least {expected_bits}"
            )
        lsb_first = list(reversed(packed[-expected_bits:]))
        cursor = 0
        values: dict[str, tuple[int, int]] = {}
        for signal in signals:
            width = int(signal["width"])
            name = _clean_name(signal["path"])
            raw_bits = lsb_first[cursor : cursor + width]
            cursor += width
            if name is None:
                continue
            value = 0
            known_mask = 0
            for bit_index, bit in enumerate(raw_bits):
                if bit in ("0", "1"):
                    known_mask |= 1 << bit_index
                    if bit == "1":
                        value |= 1 << bit_index
                elif bit not in ("x", "?"):
                    raise WitnessError(f"step {index} signal {name} contains invalid bit {bit!r}")
            values[name] = (value, known_mask)
        decoded.append(values)
    return decoded


def _hex(value: int, width: int) -> str:
    digits = max(1, (width + 3) // 4)
    return f"0x{value:0{digits}x}"


def normalize_yosys_witness(
    witness_path: Path,
    manifest: dict[str, Any],
    target_spec_path: Path,
    schema_path: Path,
    *,
    solver: str,
) -> dict[str, Any]:
    document = json.loads(witness_path.read_text(encoding="utf-8"))
    if document.get("format") != "Yosys Witness Trace":
        raise WitnessError(f"unsupported witness format: {document.get('format')!r}")

    decoded_steps = _decode_steps(document)
    input_widths = dict(manifest["ports"]["inputs"])
    generated = set(manifest["generated_signals"])
    reset_name = manifest["reset"]["signal"]
    reset_active = int(manifest["reset"]["active_level"])

    witness_names = {
        name
        for signal in document["signals"]
        if not signal["init_only"]
        if (name := _clean_name(signal["path"])) is not None
    }
    missing = sorted(set(input_widths) - witness_names)
    if missing:
        raise WitnessError(f"witness is missing top-level inputs: {', '.join(missing)}")

    reset_steps_omitted = 0
    for values in decoded_steps:
        reset_value, reset_mask = values[reset_name]
        if reset_mask != 1:
            raise WitnessError("reset is not fully constrained in the witness")
        if reset_value != reset_active:
            break
        reset_steps_omitted += 1
    replay_steps = decoded_steps[reset_steps_omitted:]
    if not replay_steps:
        raise WitnessError("witness never releases reset")

    replay_names = sorted(set(input_widths) - generated)
    cycles = []
    for cycle_index, values in enumerate(replay_steps):
        assignments = {}
        for name in replay_names:
            width = int(input_widths[name])
            value, known_mask = values[name]
            assignments[name] = {
                "value": _hex(value, width),
                "known_mask": _hex(known_mask, width),
            }
        cycles.append({"cycle": cycle_index, "assignments": assignments})

    rtl_source = manifest["rtl"]["sources"][0]
    stimulus = {
        "schema_version": "1.0",
        "metadata": {
            "benchmark_id": manifest["benchmark"]["id"],
            "target_id": manifest["targets"][0]["id"],
            "target_spec_sha256": _sha256(target_spec_path),
            "rtl_commit": manifest["upstream"]["commit"],
            "rtl_sha256": rtl_source["sha256"],
            "formal_depth": int(manifest["formal"]["depth"]),
            "solver": solver,
            "source_witness_sha256": _sha256(witness_path),
            "unknown_policy": "zero_fill_preserve_mask",
            "reset_steps_omitted": reset_steps_omitted,
        },
        "input_signals": [
            {"name": name, "width": int(input_widths[name])} for name in replay_names
        ],
        "cycles": cycles,
    }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(stimulus, schema)
    return stimulus
