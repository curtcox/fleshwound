# AGENTS.md

This directory contains built-in catalog kinds.

## Current Layout

- `__init__.py` imports one module per kind for registration side effects.
- Each kind lives in its own module (for example `echo.py`, `map_reduce.py`).
- Shared helpers live in `_shared.py` (`request`, `monty_run`, `content_hash`).
- `_minimal_input.py` holds minimal inputs for `catalog_self_test` and contract
  invariants.
- `_llm_json.py` is the factory for LLM-backed structured JSON kinds.
- `rlm_loop.py` contains the `rlm_loop` kind and RLM action protocol helpers.
- `program_writer_prompt.md` is the prompt asset read by the `program_writer`
  kind and the legacy doctor path.

Use `rg '@register' fleshwound/kinds/` to find a kind quickly.

## When Adding Or Editing A Kind

- Read `docs/specs/recursion-contract.md` first. The host envelope, budget
  rules, and deterministic side-effect boundary live there.
- Keep executor behavior deterministic. Do not add filesystem, network,
  subprocess, wall-clock, or persistent-cache behavior inside a kind.
- Use `ctx.step(...)` for recursion and request explicit child budget.
- Use `ctx.llm(...)` for model calls so usage is charged through the ledger.
- Add or update minimal inputs in `_minimal_input.py` so `catalog_self_test` and
  contract invariant tests keep covering the kind.
- Add tests under `tests/kinds/` and update goldens intentionally with
  `pytest --record` only when the value change is expected.
