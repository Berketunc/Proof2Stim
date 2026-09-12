# Experiment 0001: NVDLA cached pipeline

- Date: 2026-09-09
- Benchmark: `nvdla_apb2csb`
- Target: `delayed_read_roundtrip_v1`
- Command: `python3 -m proof2stim run --manifest manifests/nvdla_apb2csb.yaml`

## Hypothesis

A manifest-declared pipeline can reuse verified artifacts without changing the
acceptance result or relaunching formal and simulation stages.

## Result

The cold run executed baseline, formal, normalization, replay, and acceptance in
5.58 seconds of pipeline time. The immediate repeat reported five of five cache
hits in 0.60 seconds. The repeat did not launch Verilator or SymbiYosys and retained
the accepted result.

The normalized stimulus SHA-256 remained
`607a362d90573c3b18f589c85bd5e601a7c4933e5a05bb9f97bd437352711871` and the
replay-result SHA-256 remained
`153a1f7d53fd6a675274ddf8230566b67e823549cdd509f65c6ec97420e772bb`.

No model or cloud service was used, so token usage and estimated cost were zero.
