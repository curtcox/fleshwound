PYTHON ?= python
PYTEST_ARGS ?=

.PHONY: install test test-fast test-one record lint typecheck compile check site

install:
	$(PYTHON) -m pip install -e ".[site]"

test:
	$(PYTHON) -m pytest -q

test-fast:
	$(PYTHON) -m pytest -q -m "not integration"

test-one:
	$(PYTHON) -m pytest -q $(PYTEST_ARGS)

record:
	$(PYTHON) -m pytest --record

lint:
	ruff check fleshwound tests

typecheck:
	mypy fleshwound

compile:
	$(PYTHON) -m compileall -q fleshwound tests

check: compile lint typecheck test

site:
	$(PYTHON) tools/build_site.py --reports reports --out site --api api
