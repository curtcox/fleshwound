# AGENTS.md

This directory contains built-in catalog kinds.

## Current Layout

- `__init__.py` imports `core.py` for registration side effects.
- `core.py` currently contains all built-in kind executors and their
  `@register(...)` calls.
- `program_writer_prompt.md` is the prompt asset read by the `program_writer`
  kind and the legacy doctor path.

The preferred long-term layout is one module per kind, with registration in the
kind module and import wiring from `__init__.py`. Until that split happens, use
`rg '@register' fleshwound/kinds/core.py` to find a kind quickly.

## When Adding Or Editing A Kind

- Read `docs/specs/recursion-contract.md` first. The host envelope, budget
  rules, and deterministic side-effect boundary live there.
- Keep executor behavior deterministic. Do not add filesystem, network,
  subprocess, wall-clock, or persistent-cache behavior inside a kind.
- Use `ctx.step(...)` for recursion and request explicit child budget.
- Use `ctx.llm(...)` for model calls so usage is charged through the ledger.
- Add or update minimal inputs in `_minimal_input` so
  `catalog_self_test` and contract invariant tests keep covering the kind.
- Add tests under `tests/kinds/` and update goldens intentionally with
  `pytest --record` only when the value change is expected.
