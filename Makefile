# Targets used by humans and CI. Every target works offline after `uv sync`.
UV ?= uv
RUN = $(UV) run --frozen

.PHONY: check lint fmt typecheck test guards verify rebuild quality dashboard network-test

check: lint typecheck test guards

lint:
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fmt:
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

typecheck:
	$(RUN) mypy

test:
	$(RUN) pytest -q

guards:
	$(RUN) measles guard boundary
	$(RUN) measles guard hygiene
	$(RUN) measles guard outputs
	$(RUN) measles guard size
	$(RUN) measles verify

verify:
	$(RUN) measles verify

rebuild:
	$(RUN) measles rebuild

quality:
	$(RUN) measles quality

dashboard:
	$(RUN) measles dashboard build

network-test:
	$(RUN) pytest -q -m network
