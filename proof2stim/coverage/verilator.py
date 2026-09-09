"""Parse Verilator's typed coverage database into stable summary counts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _metadata_fields(encoded: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in encoded.split("\x01"):
        if "\x02" in item:
            key, value = item.split("\x02", 1)
            fields[key] = value
    return fields


def summarize_coverage(path: Path) -> dict[str, Any]:
    """Return covered/total counts grouped by Verilator coverage type."""
    metrics: dict[str, dict[str, int | float]] = {}
    raw = path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        if not line.startswith("C '"):
            continue
        metadata_end = line.rfind("' ")
        if metadata_end < 3:
            continue
        fields = _metadata_fields(line[3:metadata_end])
        coverage_type = fields.get("t")
        if not coverage_type:
            continue
        try:
            hit_count = int(line[metadata_end + 2 :])
        except ValueError:
            continue
        metric = metrics.setdefault(coverage_type, {"covered": 0, "total": 0})
        metric["total"] = int(metric["total"]) + 1
        if hit_count > 0:
            metric["covered"] = int(metric["covered"]) + 1

    for metric in metrics.values():
        covered = int(metric["covered"])
        total = int(metric["total"])
        metric["percent"] = round((100.0 * covered / total) if total else 0.0, 2)

    return {
        "coverage_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "metrics": dict(sorted(metrics.items())),
    }
