# Vertex Gemini proposal runbook

The Gemini integration produces target and formal-harness proposals. It does not
write executable verification collateral and cannot issue an acceptance verdict.

## 1. Prepare and review without provider access

```bash
uv sync --extra dev --extra gemini
make prepare-gemini PYTHON=.venv/bin/python
```

Review the ignored request at
`runs/nvdla_apb2csb/gemini/target-harness-v1/request.json`. Its prompt, response
schema, manifest, target, baseline coverage, and RTL inputs are content-hashed.
Changing any pinned input makes request validation fail until the request is
regenerated.

## 2. Configure credentials

Use Application Default Credentials or an attached workload identity. Do not copy
an API key or service-account JSON file into this repository.

For an interactive development machine:

```bash
gcloud auth application-default login
gcloud services enable aiplatform.googleapis.com --project PROJECT_ID
```

Confirm that billing and any organization policy required for Vertex AI are
configured in the selected project. Enabling an API changes external project state
and should be done deliberately by the project owner.

## 3. Freeze the paid-call inputs

Before execution, record:

- GCP project ID;
- supported Vertex location;
- exact Gemini model identifier;
- current published input and output prices per million tokens;
- a maximum estimated cost for this single request.

Pricing is supplied explicitly at invocation time so a stale price is never hidden
in source code. The preflight guard prices the conservative input-token bound plus
the configured maximum output tokens and refuses a request above the supplied cap.
Actual prompt, candidate, thinking, cached-input, and total token counts are recorded
from provider metadata.

The manifest also pins a 120-second provider timeout and one maximum HTTP attempt;
the SDK's default retry behavior is disabled so one confirmation cannot fan out
into multiple generation attempts.

## 4. Make one explicitly confirmed call

```bash
.venv/bin/python -m proof2stim run-gemini \
  --request runs/nvdla_apb2csb/gemini/target-harness-v1/request.json \
  --project PROJECT_ID \
  --location VERTEX_LOCATION \
  --model GEMINI_MODEL_ID \
  --input-usd-per-million INPUT_RATE \
  --output-usd-per-million OUTPUT_RATE \
  --cost-cap-usd SINGLE_CALL_CAP \
  --confirm-paid-call
```

On success, `proposal.json` and `run.json` are written beneath
`results/nvdla_apb2csb/gemini/target-harness-v1/`. The run record includes model,
prompt version, parameters, token usage, latency, caller-supplied pricing, estimated
cost, artifact hashes, and all validation checks.

## 5. Review and verify

A proposal is rejected if it invents a signal, cites an undeclared RTL file or bad
line range, constrains an output as an environment assumption, duplicates an ID,
changes benchmark identity, violates the JSON schema, or claims acceptance.

A validated proposal still has status `requires_formal_and_replay`. A human must
review it before translating any part into a semantic target or formal harness, and
the normal Proof2Stim formal, safety, replay, legality, data, and coverage gates
remain authoritative.
