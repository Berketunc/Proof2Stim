"""Deterministic reset/write baseline; intentionally contains no APB reads."""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from proof2stim.targets import CycleSample, DelayedReadMonitor


def drive_idle(dut) -> None:
    dut.csb2nvdla_ready.value = 0
    dut.nvdla2csb_data.value = 0
    dut.nvdla2csb_valid.value = 0
    dut.paddr.value = 0
    dut.penable.value = 0
    dut.psel.value = 0
    dut.pwdata.value = 0
    dut.pwrite.value = 0


async def reset_dut(dut) -> None:
    drive_idle(dut)
    dut.prstn.value = 0
    await Timer(1, unit="ns")
    await RisingEdge(dut.pclk)
    await RisingEdge(dut.pclk)
    dut.prstn.value = 1
    await RisingEdge(dut.pclk)


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
    )


@cocotb.test()
async def reset_returns_bridge_to_idle(dut) -> None:
    cocotb.start_soon(Clock(dut.pclk, 10, unit="ns").start())
    await reset_dut(dut)
    await Timer(1, unit="ns")

    assert int(dut.csb2nvdla_valid.value) == 0
    assert int(dut.csb2nvdla_nposted.value) == 0
    assert int(dut.pready.value) == 1


@cocotb.test()
async def write_stalls_then_completes_with_correct_mapping(dut) -> None:
    cocotb.start_soon(Clock(dut.pclk, 10, unit="ns").start())
    await reset_dut(dut)
    monitor = DelayedReadMonitor()

    address = 0x0001_2340
    data = 0xA5C3_7E19

    # APB setup phase.
    dut.psel.value = 1
    dut.penable.value = 0
    dut.pwrite.value = 1
    dut.paddr.value = address
    dut.pwdata.value = data
    dut.csb2nvdla_ready.value = 0
    await RisingEdge(dut.pclk)

    # APB access phase, stalled by CSB ready low.
    dut.penable.value = 1
    await Timer(1, unit="ns")
    stalled = sample(dut)
    monitor.observe(stalled)
    assert stalled.csb2nvdla_valid == 1
    assert stalled.pready == 0
    assert int(dut.csb2nvdla_addr.value) == ((address >> 2) & 0xFFFF)
    assert int(dut.csb2nvdla_wdat.value) == data
    assert int(dut.csb2nvdla_write.value) == 1
    assert int(dut.csb2nvdla_nposted.value) == 0

    # A ready CSB endpoint completes the write.
    dut.csb2nvdla_ready.value = 1
    await Timer(1, unit="ns")
    completed = sample(dut)
    monitor.observe(completed)
    assert completed.csb2nvdla_valid == 1
    assert completed.pready == 1
    await RisingEdge(dut.pclk)

    dut.psel.value = 0
    dut.penable.value = 0
    dut.pwrite.value = 0
    dut.csb2nvdla_ready.value = 0

    # This baseline deliberately never performs a read.
    assert not monitor.hit
    assert monitor.accepted_requests == 0
