# Decision 0003: Gemini output remains an untrusted proposal

- Status: accepted
- Date: 2026-09-13

## Context

Gemini can help interpret RTL and suggest target or harness intent, but plausible
model output is not evidence of reachability, correctness, or useful coverage. A
provider request also introduces authentication, changing model availability, and
cost risk into an otherwise local deterministic flow.

## Decision

The model receives a content-hashed, versioned prompt containing the manifest,
semantic target, baseline coverage, line-numbered RTL, and strict response schema.
It may return only plain-language candidate targets, assumptions, assertions, cover
intent, risks, validation steps, and RTL citations. Raw code, patches, commands, and
tool verdicts are outside the contract.

Local validation checks JSON structure, benchmark identity, source and line
evidence, top-level signal scope, assumption input-only scope, identifier
uniqueness, and the explicit non-acceptance marker. Provider execution requires
Application Default Credentials, caller-selected project/location/model, current
caller-supplied token prices, a single-call cost cap, and an explicit confirmation
flag. The provider timeout is 120 seconds and SDK retries are disabled.

## Consequences

- Prompt preparation and all validation are testable without credentials or spend.
- Model output cannot directly mutate project or acceptance artifacts.
- Published pricing and model selection are reviewed at call time instead of being
  silently embedded as stale defaults.
- Even a schema-valid proposal requires human review, formal solving, safety
  checks, independent replay, and measured coverage before acceptance.
- Provider failures and invalid responses do not weaken the deterministic flow.
