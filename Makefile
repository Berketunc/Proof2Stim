.PHONY: bootstrap-tools doctor doctor-strict check test validate-manifest baseline formal-cover formal-safety formal normalize-witness replay acceptance vertical-slice

PYTHON ?= python3
TOOL_ENV := $(CURDIR)/.tools/oss-cad-suite/environment

bootstrap-tools:
	bash scripts/bootstrap_oss_cad_suite.sh

doctor:
	$(PYTHON) scripts/doctor.py

doctor-strict:
	$(PYTHON) scripts/doctor.py --strict

validate-manifest:
	$(PYTHON) scripts/validate_manifest.py manifests/nvdla_apb2csb.yaml

test:
	$(PYTHON) -m unittest discover -s tests -v

check: validate-manifest test

baseline:
	bash -lc 'source "$(TOOL_ENV)" && $(MAKE) -C verification/nvdla_apb2csb/cocotb coverage RUN_KIND=baseline TEST_MODULE=test_baseline'

formal-cover:
	bash -lc 'source "$(TOOL_ENV)" && cd verification/nvdla_apb2csb/formal && sby -f nvdla_apb2csb.sby cover'

formal-safety:
	bash -lc 'source "$(TOOL_ENV)" && cd verification/nvdla_apb2csb/formal && sby -f nvdla_apb2csb.sby safety'

formal: formal-cover formal-safety

normalize-witness: formal-cover
	$(PYTHON) scripts/normalize_witness.py \
		verification/nvdla_apb2csb/formal/nvdla_apb2csb_cover/engine_0/trace0.yw \
		--manifest manifests/nvdla_apb2csb.yaml \
		--target-spec targets/nvdla_apb2csb/delayed_read_roundtrip_v1.yaml \
		--schema schemas/stimulus-v1.schema.json \
		--solver boolector-3.2.4 \
		--output results/nvdla_apb2csb/stimulus.json \
		--witness-copy results/nvdla_apb2csb/formal_witness.yw

replay: normalize-witness
	bash -lc 'source "$(TOOL_ENV)" && $(MAKE) -C verification/nvdla_apb2csb/cocotb coverage RUN_KIND=replay TEST_MODULE=test_replay TARGET_HIT=1'

acceptance: baseline formal-safety replay
	$(PYTHON) scripts/summarize_acceptance.py \
		--baseline results/nvdla_apb2csb/baseline.json \
		--replay results/nvdla_apb2csb/replay.json \
		--replay-checks results/nvdla_apb2csb/replay_checks.json \
		--stimulus results/nvdla_apb2csb/stimulus.json \
		--witness results/nvdla_apb2csb/formal_witness.yw \
		--cover-status verification/nvdla_apb2csb/formal/nvdla_apb2csb_cover/status \
		--safety-status verification/nvdla_apb2csb/formal/nvdla_apb2csb_safety/status \
		--output results/nvdla_apb2csb/acceptance.json

vertical-slice:
	$(MAKE) doctor-strict
	$(MAKE) check
	$(MAKE) acceptance
