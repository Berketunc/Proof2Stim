"""Independent monitor for the NVDLA APB-to-CSB delayed-read target."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CycleSample:
    """Signals observed during one stable APB access cycle."""

    psel: int
    penable: int
    pwrite: int
    csb2nvdla_valid: int
    csb2nvdla_ready: int
    nvdla2csb_valid: int
    nvdla2csb_data: int
    pready: int
    prdata: int
    paddr: int = 0
    pwdata: int = 0


@dataclass
class DelayedReadMonitor:
    """Recognize the target without observing DUT internals."""

    saw_access: bool = False
    stalled_cycles: int = 0
    request_accepted: bool = False
    outstanding: bool = False
    waited_for_response: bool = False
    response_seen: bool = False
    response_data: int | None = None
    accepted_requests: int = 0
    duplicate_request: bool = False
    protocol_error: str | None = None
    returned_data_matches: bool = False
    hit: bool = False

    def observe(self, sample: CycleSample) -> None:
        read_access = bool(sample.psel and sample.penable and not sample.pwrite)
        request = bool(read_access and sample.csb2nvdla_valid)
        accepted = bool(request and sample.csb2nvdla_ready)
        response = bool(sample.nvdla2csb_valid)

        if read_access:
            self.saw_access = True
        if self.saw_access and request and not sample.csb2nvdla_ready:
            self.stalled_cycles += 1

        if accepted:
            self.accepted_requests += 1
            if self.outstanding:
                self.duplicate_request = True
            elif self.stalled_cycles:
                self.request_accepted = True
                self.outstanding = True

        if accepted and response:
            self.protocol_error = "response coincided with request acceptance"

        if self.outstanding and read_access and not sample.pready and not response:
            self.waited_for_response = True

        if response:
            if not self.outstanding:
                self.protocol_error = self.protocol_error or "response without outstanding read"
            elif self.waited_for_response:
                self.response_seen = True
                self.response_data = sample.nvdla2csb_data & 0xFFFF_FFFF
                self.outstanding = False

        completion = bool(read_access and sample.pready)
        if completion and self.response_seen:
            self.returned_data_matches = (sample.prdata & 0xFFFF_FFFF) == self.response_data
            self.hit = bool(
                self.request_accepted
                and self.stalled_cycles >= 1
                and self.waited_for_response
                and not self.duplicate_request
                and self.protocol_error is None
                and self.returned_data_matches
            )
