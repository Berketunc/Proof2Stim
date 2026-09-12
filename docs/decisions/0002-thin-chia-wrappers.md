# Decision 0002: Thin CHIA wrappers around deterministic stages

- Status: accepted
- Date: 2026-09-12

## Context

The manifest pipeline already defines commands, inputs, outputs, cache keys, and
acceptance behavior. Reimplementing those rules inside CHIA nodes would create two
verification flows that could silently diverge.

## Decision

CHIA nodes call the same public stage executor used by the local orchestrator.
Baseline coverage and formal solving are independent graph roots. Witness
conversion depends on formal, replay depends on conversion, and acceptance depends
on baseline, formal, and replay. Each node records its cache key and artifact hashes
in CHIA profiler metadata, while the terminal driver writes a schema-validated run
record with pinned CHIA and Ray versions.

The current nodes exchange small dependency results through Ray and exchange RTL,
witness, coverage, and verdict artifacts through the shared project workspace.
Remote workers therefore require the repository at the same absolute path.

## Consequences

- Local and CHIA execution share one deterministic implementation and acceptance
  boundary.
- Two resource slots expose safe baseline/formal parallelism without allowing
  stages that write overlapping artifacts to race.
- CHIA profiling does not change the values consumed by downstream nodes; profiled
  result envelopes are explicitly unwrapped and regression-tested.
- The content-addressed local pipeline remains the artifact cache. CHIA provides
  graph scheduling, resource declaration, profiling, and provenance.
- A future distributed artifact store can replace the shared-filesystem constraint
  without changing the stage contracts.
