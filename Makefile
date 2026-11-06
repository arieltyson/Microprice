# Microprice build and research pipeline. Every published number comes from `make results`.

PY := cd research && uv run
BUILD := build
JOBS ?= 8
SEC_USER_AGENT ?=

.PHONY: all hooks build test check bench bench-feed data headlines features forecast sweep evaluate analysis \
        results gateway dashboard demo up clean clean-data

all: build

hooks:
	git config core.hooksPath .githooks

build:
	cmake -S . -B $(BUILD) -DCMAKE_BUILD_TYPE=Release -DPython_EXECUTABLE=$(CURDIR)/research/.venv/bin/python
	cmake --build $(BUILD) -j $(JOBS)

test: build
	ctest --test-dir $(BUILD) --output-on-failure -j $(JOBS)
	$(PY) pytest -q
	cd analysis && Rscript tests/testthat.R
	cd dashboard && npm test
	@if command -v q >/dev/null; then q tickstore/tests/test_analytics.q -q; else echo "q not installed: skipped q unit tests"; fi

check: test
	$(PY) ruff check microprice tests
	$(PY) ruff format --check microprice tests
	$(PY) mypy
	cd dashboard && npm run lint && npx tsc -b

bench: build
	$(BUILD)/engine/engine_bench --benchmark_min_time=2s --benchmark_format=json --benchmark_out=results/engine_bench.json
	$(MAKE) bench-feed

bench-feed: build
	./scripts/bench_feed.sh $(BUILD) data/synthetic/AAPL/AAPL_2026-10-19_34200000_57600000_message_1.csv

headlines:
	$(PY) python -m microprice.sentiment $(if $(SEC_USER_AGENT),--source edgar --user-agent "$(SEC_USER_AGENT)",)

data: build
	$(PY) python -m microprice.synth --workers $(JOBS)

forecast:
	$(PY) python -m microprice.model

sweep:
	$(PY) python -m microprice.sweep

evaluate:
	$(PY) python -m microprice.evaluate

analysis:
	Rscript analysis/run.R results/holdout_fills.csv results/analysis

results: build headlines data forecast sweep evaluate analysis bench
	$(PY) python -m microprice.report

gateway:
	$(PY) python -m microprice.gateway

dashboard:
	cd dashboard && npm run dev

# Static dashboard with recorded data, for hosting without the gateway (dashboard/dist).
demo:
	$(PY) python -m microprice.demo
	cd dashboard && VITE_DEMO=true npx vite build

up:
	docker compose -f infra/docker-compose.yml up --build

clean:
	rm -rf $(BUILD)

clean-data:
	rm -rf data/synthetic data/features data/sessions data/headlines results
