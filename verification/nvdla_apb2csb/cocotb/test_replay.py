"""Replay normalized formal stimulus on the original, unmodified RTL."""

from __future__ import annotations

import json
import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from proof2stim.replay import ApbCsbLegalityChecker
from proof2stim.targets import CycleSample, DelayedReadMonitor

EXPECTED_INPUTS = {
    "csb2nvdla_ready",
    "nvdla2csb_data",
    "nvdla2csb_valid",
    "paddr",
    "penable",
    "psel",
    "pwdata",
    "pwrite",
}


def drive_idle(dut) -> None:
    for name in EXPECTED_INPUTS:
        getattr(dut, name).value = 0


def sample(dut) -> CycleSample:
    return CycleSample(
        psel=int(dut.psel.value),
        penable=int(dut.penable.value),
        pwrite=int(dut.pwrite.value),
        csb2nvdla_valid=int(dut.csb2nvdla_valid.value),
        csb2nvdla_ready=int(dut.csb2nvdla_ready.value),
        nvdla2csb_valid=int(dut.nvdla2csb_valid.value),
        nvdla2csb_data=int(dut.nvdla2csb_data.value),
        pready=int(dut.pready.value),
        prdata=int(dut.prdata.value),
        paddr=int(dut.paddr.value),
        pwdata=int(dut.pwdata.value),
    )


def validate_and_drive(dut, stimulus: dict, cycle: dict) -> None:
    declared = {item["name"]: int(item["width"]) for item in stimulus["input_signals"]}
    assert set(declared) == EXPECTED_INPUTS
    assignments = cycle["assignments"]
    assert set(assignments) == EXPECTED_INPUTS

    for name, encoded in assignments.items():
        width = declared[name]
        full_mask = (1 << width) - 1
        value = int(encoded["value"], 16)
        known_mask = int(encoded["known_mask"], 16)
        assert value & ~full_mask == 0
        assert known_mask & ~full_mask == 0
        assert value & ~known_mask == 0, f"{name} did not zero-fill unknown bits"
        getattr(dut, name).value = value


@cocotb.test()
async def replay_formal_witness(dut) -> None:
    stimulus_path = Path(os.environ["STIMULUS_JSON"])
    stimulus = json.loads(stimulus_path.read_text(encoding="utf-8"))

    cocotb.start_soon(Clock(dut.pclk, 10, unit="ns").start())
    drive_idle(dut)
    dut.prstn.value = 0
    await Timer(1, unit="ns")
    await RisingEdge(dut.pclk)
    await RisingEdge(dut.pclk)
    dut.prstn.value = 1

    monitor = DelayedReadMonitor()
    legality = ApbCsbLegalityChecker()
    for expected_cycle, cycle in enumerate(stimulus["cycles"]):
        assert cycle["cycle"] == expected_cycle
        validate_and_drive(dut, stimulus, cycle)
        await Timer(1, unit="ns")
        observed = sample(dut)
        legality.observe(observed)
        monitor.observe(observed)
        await RisingEdge(dut.pclk)

    checks = {
        "schema_version": "1.0",
        "legality_passed": legality.legal,
        "legality_errors": legality.errors,
        "target_hit": monitor.hit,
        "data_checks_passed": monitor.returned_data_matches,
        "accepted_reads": legality.accepted_reads,
        "responses": legality.responses,
        "outstanding_read_at_end": legality.outstanding_read,
        "duplicate_request": monitor.duplicate_request,
    }
    checks_path = Path(os.environ["REPLAY_CHECKS_JSON"])
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert checks["legality_passed"], "; ".join(legality.errors)
    assert checks["accepted_reads"] == 1
    assert checks["responses"] == 1
    assert not checks["outstanding_read_at_end"]
    assert checks["target_hit"]
    assert checks["data_checks_passed"]
    assert not checks["duplicate_request"]
