# Proof2Stim

Proof2Stim turns formally discovered RTL cover witnesses into deterministic
simulation tests. Formal tools search for a bounded trace; independent cocotb
monitors, protocol checks, and Verilator coverage decide whether that trace is
accepted.

The first vertical slice targets NVDLA's `NV_NVDLA_apb2csb` bridge and a legal
delayed APB-read round trip. The detailed goals and acceptance criteria live in
[`PROOF2STIM_PROJECT_BRIEF.md`](PROOF2STIM_PROJECT_BRIEF.md).

## Current status

- The initial NVDLA vertical slice is complete and passes every acceptance gate.
- The intentionally read-free baseline leaves the delayed-read target uncovered.
- SymbiYosys finds a six-cycle, top-level-input-only witness; the normalized
  stimulus replays legally on the original RTL and independently hits the target.
- Bounded safety passes to depth 32, and two complete regenerations produced the
  same normalized stimulus and replay-result hashes.
- NVDLA is pinned to commit `8e06b1b9d85aab65b40d43d08eec5ea4681ff715`.
- CHIA is pinned to commit `a2c4dae46528055efa59444d54832336851f633f`.

Measured coverage for the accepted trace:

| Metric | Baseline | Replay | Delta |
| --- | ---: | ---: | ---: |
| Line | 1/2 (50%) | 2/2 (100%) | +50 percentage points |
| Branch | 3/4 (75%) | 4/4 (100%) | +25 percentage points |
| Toggle | 64/380 (16.84%) | 114/380 (30%) | +13.16 percentage points |

The complete warm local reproduction takes about seven seconds on the development
machine. The machine-readable verdict is in
[`results/nvdla_apb2csb/acceptance.json`](results/nvdla_apb2csb/acceptance.json).

## Quick start

```bash
make bootstrap-tools
make vertical-slice
```

`make bootstrap-tools` installs the checksum-pinned Linux x86_64 OSS CAD Suite
under the ignored `.tools/` directory without administrator privileges.
`make vertical-slice` checks the environment and manifest, runs the unit tests and
baseline, proves the bounded safety properties, solves the cover target, normalizes
the witness, replays it with cocotb, measures coverage, and writes the final verdict.

Use `make doctor` to inspect dependencies without failing, or `make doctor-strict`
to require the complete toolchain. The Python-only checks run with `make check`.

## Produced evidence

- `results/nvdla_apb2csb/stimulus.json`: normalized six-cycle formal stimulus.
- `results/nvdla_apb2csb/formal_witness.yw`: compact original Yosys witness.
- `results/nvdla_apb2csb/replay_checks.json`: independent legality, data, and
  semantic-monitor results.
- `results/nvdla_apb2csb/baseline.json` and `replay.json`: deterministic Verilator
  coverage summaries.
- `results/nvdla_apb2csb/acceptance.json`: combined binary acceptance decision,
  coverage deltas, and artifact hashes.

## Design rules

- Third-party RTL remains byte-for-byte identical to its pinned upstream source.
- Formal assumptions, safety assertions, and cover goals stay separate.
- Witness artifacts contain only top-level DUT inputs; cocotb creates clocks and
  reset waveforms.
- Unknown witness bits retain a known-bit mask and are zero-filled deterministically.
- A trace is accepted only after legality, semantic-target, data, and coverage checks.
- Bounded misses and timeouts are unresolved outcomes, not unreachability proofs.

## Repository map

- `manifests/`: pinned benchmark and interface descriptions.
- `targets/`: shared, versioned semantic target definitions.
- `schemas/`: JSON Schema contracts for manifests and generated artifacts.
- `proof2stim/`: reusable Python implementation.
- `verification/`: DUT-specific cocotb and formal collateral.
- `third_party/`: pinned upstream RTL and license material.
- `runs/`: ignored ephemeral run directories.
- `results/`: compact, reviewable result summaries.
