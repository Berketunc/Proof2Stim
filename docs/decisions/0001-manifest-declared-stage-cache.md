# Decision 0001: Manifest-declared, content-addressed stage cache

- Status: accepted
- Date: 2026-09-09

## Context

The verified NVDLA flow consisted of deterministic Make targets, but the targets
were tied together with convenience dependencies. Repeating the workflow always
launched formal and simulation even when every relevant input was unchanged.

## Decision

Each benchmark manifest declares an ordered pipeline. Every stage lists its exact
command, file inputs, and required outputs. Proof2Stim hashes the stage identity,
command, and input contents to form a cache key. A cache entry is usable only when
all cached output hashes match its metadata. Cache hits restore outputs into their
normal project paths so downstream stages use the same interfaces as cold runs.

The latest run record is committed as compact evidence. Immutable per-invocation
records and cache payloads remain under ignored local directories.

## Consequences

- Cache invalidation is explicit and reviewable in the benchmark manifest.
- Changes propagate naturally because downstream artifacts are stage inputs.
- Cached results are never accepted based only on path existence.
- Benchmark authors must keep declared input lists complete.
- Commands remain independently runnable outside the orchestrator.
