# AGENTS.md

Tests are fast and should usually be run in full before handing off changes.

## Commands

```sh
python -m pytest -q
python -m pytest -q -m "not integration"
python -m pytest -q tests/kinds/test_group_a.py::TestBudget
python -m pytest --record
```

## Fixtures And Helpers

- `tests/conftest.py` defines the custom `--record` option and assertion
  helpers.
- `tests/_fake_provider.py` provides pattern-matched model responses. An
  unmatched prompt raises `FakeProviderUnmatched`; that is intentional.
- `tests/_fake_user.py` provides deterministic `ask_user` behavior.
- `tests/_golden.py` hashes deterministic outputs and reads or rewrites files
  under `tests/_goldens/`.

## Golden Files

Default test runs verify goldens. `pytest --record` rewrites them, so only use
record mode when reviewing an intentional behavior change. Golden diffs should
be reviewed like code.

## Coverage Shape

Per-kind group tests normally cover convention, budget behavior, failure
behavior, integration paths, and determinism. Cross-catalog invariants live in
`tests/test_contract_invariants.py`.
