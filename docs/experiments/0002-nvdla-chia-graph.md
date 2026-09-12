# Experiment 0002: NVDLA CHIA graph

- Date: 2026-09-12
- Benchmark: `nvdla_apb2csb`
- Target: `delayed_read_roundtrip_v1`
- Command: `.tools/chia-venv/bin/python scripts/run_chia_pipeline.py`

## Hypothesis

Thin CHIA nodes can schedule the deterministic Proof2Stim stages as a dependency
graph, run independent roots concurrently, preserve the verified acceptance result,
and emit complete provenance without adding model or cloud dependencies.

## Result

The five-node graph completed successfully and reported `CHIA ACCEPTED: True`.
Ray launched baseline coverage and formal solving in separate workers, after which
the formal result flowed through normalization and replay into the terminal
acceptance node. The graph itself took 4.329319 seconds, excluding local Ray startup;
all five stage records reported status `passed` and return code zero.

The run used CHIA 1.0.1 at commit
`a2c4dae46528055efa59444d54832336851f633f` and Ray 2.54.0. The accepted verdict
SHA-256 was
`bac8965e9f8b190315dee54f051055ebd163dc765585e9566fe676ec3fd7d7dd`.
CHIA profiler output was written under `runs/chia-profiles/`, and the compact run
record was written to `results/nvdla_apb2csb/chia_run.json`.

No model or cloud service was used, so token usage and estimated cost were zero.
