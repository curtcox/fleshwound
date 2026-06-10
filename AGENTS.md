# AGENTS.md

Fleshwound is a Python experiment in recursive, budget-bounded program-writing
on Monty. The public package entry point is `fleshwound.run_step`.

## Start Here

- Contract source of truth: `docs/specs/recursion-contract.md`.
- Runtime entry point: `fleshwound/runner.py`.
- Budget accounting: `fleshwound/budget.py`.
- Catalog registry/context/provider: `fleshwound/catalog.py`,
  `fleshwound/context.py`, and `fleshwound/provider.py`.
- Built-in kinds: currently consolidated in `fleshwound/kinds/core.py`; the
  preferred long-term shape is one module per kind.
- Tests: `tests/`, with per-kind groups in `tests/kinds/`.
- Historical design notes: `docs/history/`.

## Commands

Canonical local setup uses an editable pip install because it matches CI and
keeps prompt Markdown files available from the checkout:

```sh
python -m pip install -e ".[site]"
```

Common loops:

```sh
make check          # compile, ruff, mypy, pytest
make test           # full suite
make test-fast      # skips integration-marked tests
make lint
make typecheck
make site           # writes ./site from existing reports/api inputs
```

For one test, pass normal pytest selectors through `PYTEST_ARGS`:

```sh
make test-one PYTEST_ARGS='tests/kinds/test_group_a.py::TestBudget'
```

## Gotchas

- `import fleshwound.kinds` registers built-in catalog entries by import side
  effect. See `fleshwound/kinds/__init__.py`.
- `run_step(task=..., llm=...)` is the legacy doctor path. New work should use
  the contract-shaped `run_step(input, budget, provider, kind=...)` path.
- `Recursive_step_prompt.md` is used by the legacy path. The modern
  `program_writer` kind reads `fleshwound/kinds/program_writer_prompt.md`.
- `pytest --record` rewrites files under `tests/_goldens/`; use it only when
  intentionally updating determinism fixtures.
- `tools/build_site.py --out PATH` deletes and recreates `PATH`.
- Executors are intended to be deterministic and side-effect-free except
  through `ctx.llm`, `ctx.step`, `ctx.ask_user`, `ctx.budget`, and
  `ctx.catalog`.
- Wheels/sdists are not a supported surface today. If that changes, make sure
  prompt Markdown files are explicitly packaged; editable installs work because
  the files are read directly from the checkout.

## Generated Or Local-Only Paths

Do not edit `.venv/`, `.pytest_cache/`, `.mypy_cache`, `.ruff_cache/`,
`__pycache__/`, `.coverage`, `*.egg-info/`, `site/`, `reports/`, or `api/`.

## Project Conventions

- There is no repo-specific branch, commit message, or PR format yet.
- CI and local checks should agree on Python 3.12 where practical.
- GitHub Pages must continue to publish the developer dashboard with compile,
  lint, type-check, test, coverage, and API-report information whenever `main`
  changes.
