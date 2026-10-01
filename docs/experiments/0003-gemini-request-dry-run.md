# Experiment 0003: Gemini request dry-run

- Date: 2026-09-13
- Benchmark: `nvdla_apb2csb`
- Target: `delayed_read_roundtrip_v1`
- Command: `make prepare-gemini PYTHON=.venv/bin/python`

## Hypothesis

The complete target/harness proposal request and validation boundary can be frozen
and exercised before configuring credentials or spending money.

## Result

The dry-run generated a request from pinned manifest inputs and explicitly reported
`MODEL CALL: not performed`. The deterministic prompt SHA-256 is
`cadf480c67d36858b41a8da29497955fc2137f510f2ad5ddacb8eb8492a99c0a`.
The local heuristic estimates 3,705 input tokens, while the cost guard uses a more
conservative 18,686-token input bound plus the configured 8,192-token maximum
output.

The Google Gen AI SDK was locked at 1.75.0. Its local types accepted the frozen
`application/json` structured-output configuration and response JSON Schema. The
offline suite covers request determinism, hash tampering, unknown signals,
input-only assumptions, evidence ranges, duplicate identifiers, non-JSON output,
provider metering, the cost cap, and the explicit paid-call confirmation.

No provider request was made, so measured provider token usage and cost are zero.
