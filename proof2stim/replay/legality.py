"""Protocol legality checks that do not inspect DUT internal state."""

from __future__ import annotations

from dataclasses import dataclass, field

from proof2stim.targets import CycleSample


@dataclass
class ApbCsbLegalityChecker:
    """Check the pilot's explicit APB and CSB environment contract."""

    previous: CycleSample | None = None
    outstanding_read: bool = False
    accepted_reads: int = 0
    responses: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def legal(self) -> bool:
        return not self.errors

    def observe(self, sample: CycleSample) -> None:
        access = bool(sample.psel and sample.penable)
        read_access = bool(access and not sample.pwrite)
        accepted_read = bool(read_access and sample.csb2nvdla_valid and sample.csb2nvdla_ready)
        response = bool(sample.nvdla2csb_valid)

        if sample.penable and not sample.psel:
            self.errors.append("penable asserted without psel")

        if access:
            legal_predecessor = bool(
                self.previous
                and self.previous.psel
                and (
                    not self.previous.penable
                    or (self.previous.penable and not self.previous.pready)
                )
            )
            if not legal_predecessor:
                self.errors.append("APB access lacked setup or waiting predecessor")

        if (
            self.previous
            and self.previous.psel
            and self.previous.penable
            and not self.previous.pready
        ):
            if not (sample.psel and sample.penable):
                self.errors.append("APB transfer was dropped while waiting")
            if sample.paddr != self.previous.paddr:
                self.errors.append("APB address changed while waiting")
            if sample.pwrite != self.previous.pwrite:
                self.errors.append("APB direction changed while waiting")
            if sample.pwdata != self.previous.pwdata:
                self.errors.append("APB write data changed while waiting")

        if accepted_read:
            self.accepted_reads += 1
            if self.outstanding_read:
                self.errors.append("duplicate read request accepted")
            self.outstanding_read = True

        if response:
            self.responses += 1
            if accepted_read:
                self.errors.append("response coincided with request acceptance")
            if not self.outstanding_read:
                self.errors.append("response arrived without an outstanding read")
            self.outstanding_read = False

        self.previous = sample
