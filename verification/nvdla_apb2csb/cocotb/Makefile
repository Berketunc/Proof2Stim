ROOT := $(abspath ../../..)

SIM ?= verilator
RUN_KIND ?= baseline
TEST_MODULE ?= test_baseline
TARGET_HIT ?= 0
TOPLEVEL_LANG := verilog
VERILOG_SOURCES := $(ROOT)/third_party/nvdla/vmod/nvdla/apb2csb/NV_NVDLA_apb2csb.v
COCOTB_TOPLEVEL := NV_NVDLA_apb2csb
COCOTB_TEST_MODULES := $(TEST_MODULE)
COCOTB_RESULTS_FILE := $(RUN_KIND)_results.xml
COCOTB_HDL_TIMEUNIT := 1ns
COCOTB_HDL_TIMEPRECISION := 1ps
SIM_BUILD := $(ROOT)/build/nvdla_apb2csb/baseline
export PYTHONPATH := $(ROOT):$(PYTHONPATH)
export PYTEST_DISABLE_PLUGIN_AUTOLOAD := 1
export COCOTB_RANDOM_SEED := 1
export STIMULUS_JSON := $(ROOT)/results/nvdla_apb2csb/stimulus.json
export REPLAY_CHECKS_JSON := $(ROOT)/results/nvdla_apb2csb/replay_checks.json

COMPILE_ARGS += --coverage-line --coverage-toggle
SIM_ARGS += +verilator+coverage+file+$(RUN_KIND)_coverage.dat

ifeq ($(TARGET_HIT),1)
TARGET_HIT_ARG := --target-hit
endif

.PHONY: coverage $(COCOTB_RESULTS_FILE)
coverage: $(COCOTB_RESULTS_FILE)
	verilator_coverage --write-info $(RUN_KIND)_coverage.info $(RUN_KIND)_coverage.dat
	python3 $(ROOT)/scripts/summarize_coverage.py \
		$(RUN_KIND)_coverage.dat \
		--output $(ROOT)/results/nvdla_apb2csb/$(RUN_KIND).json \
		--kind $(RUN_KIND) \
		--benchmark-id nvdla_apb2csb \
		--target-id delayed_read_roundtrip_v1 \
		$(TARGET_HIT_ARG)

include $(shell cocotb-config --makefiles)/Makefile.sim
