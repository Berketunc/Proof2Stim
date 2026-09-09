"""Dependency diagnostics with a stable, machine-readable result."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_TOOLCHAIN = PROJECT_ROOT / ".tools" / "oss-cad-suite"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    executable: str
    version_args: tuple[str, ...]
    required: bool
    purpose: str


@dataclass(frozen=True)
class ToolResult:
    name: str
    required: bool
    available: bool
    path: str | None
    version: str | None
    purpose: str
    error: str | None = None


TOOL_SPECS = (
    ToolSpec("git", "git", ("--version",), True, "source provenance"),
    ToolSpec("make", "make", ("--version",), True, "local entry points"),
    ToolSpec("verilator", "verilator", ("--version",), True, "RTL simulation and coverage"),
    ToolSpec("yosys", "yosys", ("-V",), True, "RTL synthesis and formal elaboration"),
    ToolSpec("symbiyosys", "sby", ("--version",), True, "formal orchestration"),
    ToolSpec("boolector", "boolector", ("--version",), True, "bounded SMT solving"),
    ToolSpec("cocotb", "cocotb-config", ("--version",), True, "simulation testbench"),
    ToolSpec("z3", "z3", ("--version",), False, "alternative SMT solver"),
)


def activate_local_toolchain() -> None:
    """Prefer the pinned project-local toolchain when it has been bootstrapped."""
    tool_paths = (LOCAL_TOOLCHAIN / "bin", LOCAL_TOOLCHAIN / "py3bin")
    existing = [str(path) for path in tool_paths if path.is_dir()]
    if existing:
        os.environ["PATH"] = os.pathsep.join((*existing, os.environ.get("PATH", "")))


def _first_line(value: str) -> str:
    return value.strip().splitlines()[0] if value.strip() else "unknown"


def inspect_tool(spec: ToolSpec) -> ToolResult:
    path = shutil.which(spec.executable)
    if path is None:
        return ToolResult(spec.name, spec.required, False, None, None, spec.purpose, "not found")
    try:
        completed = subprocess.run(
            (path, *spec.version_args),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult(spec.name, spec.required, False, path, None, spec.purpose, str(exc))
    combined = completed.stdout or completed.stderr
    if completed.returncode != 0:
        error = _first_line(combined) if combined else f"exit code {completed.returncode}"
        return ToolResult(spec.name, spec.required, False, path, None, spec.purpose, error)
    return ToolResult(spec.name, spec.required, True, path, _first_line(combined), spec.purpose)


def collect_report() -> dict[str, object]:
    activate_local_toolchain()
    results = [inspect_tool(spec) for spec in TOOL_SPECS]
    python_ok = sys.version_info >= (3, 11)
    python_result = ToolResult(
        "python",
        True,
        python_ok,
        sys.executable,
        platform.python_version(),
        "workflow runtime",
        None if python_ok else "Python 3.11 or newer is required",
    )
    results.insert(0, python_result)
    missing_required = [item.name for item in results if item.required and not item.available]
    return {
        "schema_version": "1.0",
        "platform": platform.platform(),
        "ready": not missing_required,
        "missing_required": missing_required,
        "tools": [asdict(item) for item in results],
    }


def render_text(report: dict[str, object]) -> str:
    lines = ["Proof2Stim dependency doctor", ""]
    for item in report["tools"]:
        assert isinstance(item, dict)
        mark = "OK" if item["available"] else ("MISSING" if item["required"] else "OPTIONAL")
        detail = item["version"] or item["error"] or "unknown"
        detail = re.sub(r"\s+", " ", str(detail))
        lines.append(f"{mark:8} {item['name']:12} {detail}")
    lines.append("")
    if report["ready"]:
        lines.append("READY: all required dependencies are available")
    else:
        missing = ", ".join(report["missing_required"])
        lines.append(f"NOT READY: missing required dependencies: {missing}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--strict", action="store_true", help="fail when required tools are missing"
    )
    args = parser.parse_args(argv)
    report = collect_report()
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render_text(report))
    return 1 if args.strict and not report["ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
