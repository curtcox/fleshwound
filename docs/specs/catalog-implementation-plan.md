# Catalog Implementation Plan (TDD)

This plan implements every kind in `recursion-kinds-catalog.md` using TDD, in dependency order. It tightens the layered approach proposed earlier with the choices recorded under "Decisions" below.

## Decisions

| # | Decision |
|---|---|
| A | **Test framework**: `pytest`. No additional tooling required to start. `hypothesis` may be added later for property tests on the ledger; not part of v1. |
| B | **FakeProvider**: pattern-matched. Tests register `{prompt_regex: ModelTextResult}` mappings. Unmatched prompts raise `FakeProviderUnmatched` at test time — no fallback, no warning. Helper presets ship for common patterns (program_writer scaffolds, judge yes/no, etc.). |
| C | **Monty in CI**: in the default suite. Failures expose bugs in Monty or the binding — that is the point of running it. No `slow`/`monty` skip markers in v1. |
| D | **Catalog layout**: one file per kind at `fleshwound/kinds/<name>.py`, registered via `@catalog.register(name, convention=...)`. Prompt assets at `fleshwound/kinds/<name>_prompt.md` when applicable. Tests at `tests/kinds/test_<name>.py`. |
| E | **Per-kind test minimum**: four classes (convention, budget, failure, determinism). Most kinds will have multiple cases per class. |
| F | **Test realism**: every kind gets both layers — stubbed unit tests (fast, isolated) and integration tests with real Monty + FakeProvider. Combined in one file, integration tests marked `@pytest.mark.integration` and run by default in CI. |
| G | **Determinism fixtures**: both. Hand-curated goldens for kinds where the choice of input is meaningful (e.g. `program_writer` against a realistic task); auto-recorded goldens (record → SHA-256 of value) for every kind via the `regression_canary` fixture. Record mode is opt-in (`pytest --record`); verify is the default and drift fails CI. |

## Conventions

### Per-kind test obligations

Every `tests/kinds/test_<name>.py` file must contain at minimum:

```python
class TestConvention:
    # input shape acceptance; value shape conformance; happy path
    ...

class TestBudget:
    # charges what convention documents; refunds correct on every close
    ...

class TestFailure:
    # at least one realistic failure path per kind:
    #   - provider error, budget_denied from child, ask_user unavailable,
    #     malformed input, etc. — kind-specific
    ...

class TestDeterminism:
    # same (input, budget, seed, provider) → byte-identical value
    # (auto-recorded via regression_canary helper)
    ...
```

A kind is "implemented" when these four classes are green AND it appears in `catalog_self_test`'s minimal-input sweep (Phase 14) without producing an unexpected `host_error`.

### Test layering inside one file

```python
# fast, deterministic, no Monty execution required
class TestConvention: ...     # unit
class TestBudget: ...         # unit

# real Monty + FakeProvider, marked integration
@pytest.mark.integration
class TestEndToEnd: ...

# determinism canary; auto-recorded
class TestDeterminism: ...
```

Unit tests stub the Monty layer where present (executor is invoked directly with a constructed `RunContext`). Integration tests exercise the full `runner.run_step` path.

### FakeProvider patterns

```python
fake = FakeProvider({
    r"^Write a Python function slugify": ModelTextResult(
        text="```python\ndef slugify(s): ...\n```",
        usage=Usage(prompt_tokens=42, completion_tokens=18),
    ),
})
```

Unmatched prompts raise `FakeProviderUnmatched(prompt)` — surfaced via the test's normal failure path; never via `llm()`'s `status: "error"` (which would silently mask the missing fixture).

### Catalog registration

```python
# fleshwound/kinds/constant.py
from fleshwound.catalog import register

@register("constant", convention="input.value → value verbatim; no charges beyond step")
def executor(input, ctx):
    return input["value"]
```

The decorator wires the function into a module-level `Catalog` populated by an `import fleshwound.kinds` side-effect import. Test fixtures can register additional kinds (e.g. `always_host_error/*` variants) into a fresh `Catalog` instance to keep the production catalog clean.

### `regression_canary` helper

```python
def assert_deterministic(kind, input, *, budget=DEFAULT_BUDGET, seed=0, provider=FROZEN_PROVIDER):
    """Record-or-verify the SHA-256 of value for (kind, input, seed)."""
    ...
```

Goldens live at `tests/_goldens/<kind>/<test_name>.json` as `{"hash": "...", "input": ..., "value_sample": ...}`. Record mode rewrites them; verify mode diffs.

---

## Phases

Each phase is **red → green → refactor**. A phase is complete when its exit criterion holds with no skipped tests.

### Phase 0 — Test harness

Build the harness used by every later phase. No production code.

- `tests/conftest.py`: `make_ledger`, `make_ctx`, `assert_ok`, `assert_host_error(code=)`, `DEFAULT_BUDGET`.
- `tests/_fake_provider.py`: pattern-matched `FakeProvider`, `FakeProviderUnmatched`, `Usage`.
- `tests/_fake_user.py`: `FakeAskUser` (queue or per-question map).
- `tests/_golden.py`: `assert_deterministic`, record/verify modes.
- `tests/test_harness.py`: tests for the harness itself.

**Exit**: harness self-tests green; `--record` and verify modes both work on a stub.

### Phase 1 — Budget ledger

TDD against `budget-ledger.md`. Implement `fleshwound/budget.py`.

Test surfaces (each is a test method, not a whole class):

- root creation; snapshot matches limit.
- per-dimension charges; snapshot decrements; events ordered.
- child allocation: zero tokens / zero tool_calls accepted; steps>=1 / depth>=1 enforced.
- over-parent → `deny` event, no child created.
- close-child: refund-then-close ordering; refund on every outcome including error.
- deterministic child IDs (`root.1`, `root.2.1`).
- sequence numbers stable across runs.
- `allocate_child` event records `resolved_kind` (the C-1 ledger home).

**Exit**: every clause in budget-ledger.md §3–§6 has a test; all green.

### Phase 2 — RunContext, Catalog, executor protocol

- `fleshwound/context.py`: `RunContext` dataclass + factory.
- `fleshwound/catalog.py`: `Catalog` registry, `register` decorator, lookup with `unknown_kind` surfacing.
- Tests cover: registration, lookup, duplicate-name rejection, `ctx.catalog` shape (read-only mapping).

**Exit**: a kind can be registered and looked up; ctx.catalog reflects the registry; unknown-kind lookups raise the right typed error (later wrapped into `host_error` by the runner).

### Phase 3 — Runner core + Group A kinds

- `fleshwound/runner.py` rewrite implementing the contract's §3–§6 wrapper.
- Group A kinds (each `tests/kinds/test_<name>.py` with the four standard classes plus end-to-end):
  - `constant`
  - `echo`
  - `noop_fail` (one variant raises a host-Python exception → `executor_error`; companion `noop_fail_monty` after Phase 5 → `monty_error`)

**Exit**: Group A green. The runner's host safety nets (charge_step, exception wrap, JSON-serializability, envelope shape) are exercised. Determinism canary is in active use for the first time.

### Phase 4 — Provider abstraction

- `fleshwound/provider.py`: `ModelProvider` protocol, `CallableProvider`, `ModelTextResult`, `Usage`, `ToolSpec`/`ToolCall`/`ToolResult`.
- `ctx.llm` lands in `runner.py`: always-dict return, charge on success AND failure, never raises.
- Tests: success path; provider raises → `status: "error"`; usage charged for prompt_tokens even on failure; multiple calls accumulate charges; failure mid-step lets the executor return a normal value.

**Exit**: `llm()` contract from §4.1 fully covered.

### Phase 5 — Monty integration + `monty_exec`

- `runner.py` binds `ctx.{llm, step, ask_user, budget, catalog}` as Monty externals for Monty-using executors.
- `fleshwound/kinds/monty_exec.py` is the first kind to use this binding.
- Tests for `monty_exec`:
  - trivial expression
  - code calling `ctx.llm`
  - non-serializable final expression → `malformed_result`
  - code raising → `monty_error`
  - code calling `ctx.step` recursively (cross-checks Phase 6's recursion machinery — initially a stub)

**Exit**: Monty round-trip works through the runner; safety nets behave the same as for non-Monty executors.

### Phase 6 — Group B (LLM leaves)

- `prose_writer`, `classifier`, `ask_user_only`.
- Patterns established here will be reused across the LLM-heavy kinds: FakeProvider scripts for happy/edge cases, integration tests pinning a realistic prompt fragment.

**Exit**: Group B green; FakeProvider pattern library has presets useful to later phases.

### Phase 7 — Group C minus `program_writer`

- `map_reduce`, `retry_wrapper`, `ensemble`, `judge`, `clarify_then_delegate`.
- Recursion stresses: sequential child allocation order, refund correctness on failed children, child-budget sizing, `kind=` override per child.

**Exit**: a kind can call `ctx.step` to invoke another kind; refund accounting is correct across at least one error path.

### Phase 8 — `program_writer`

- Move `Recursive_step_prompt.md` to `fleshwound/kinds/program_writer_prompt.md`. Executor loads it from there.
- Tests: end-to-end with FakeProvider scripting plausible Monty code; child step delegation; status/outcome distinction; partial/error paths.
- This is the first kind with a substantial prompt asset — establish the convention.

**Exit**: the canonical kind works end-to-end against FakeProvider; goldens recorded.

### Phase 9 — Group D (default-policy)

- `inherit_chain`, `random_pick`, `subset_pick`.
- Tests: `same_as_parent` chain hits depth floor → `budget_denied`; seed derivation reproducible across runs; `allocate_child` event records the resolved kind (C-1 ledger field validated here); empty subset → `unresolvable_default`; unknown name in subset → `unknown_kind`.

**Exit**: default-policy resolution is observable on the ledger; no kind has to surface `resolved_kind` in its value.

### Phase 10 — Group E + Group F

- Group E: `always_host_error/*` (one per host_error code), `always_partial`, `budget_hog/{tokens,steps,tool_calls}`, `infinite_descent`.
- Group F: `provider_swap`.
- Cross-check: every `host_error.code` listed in `recursion-contract.md` §4 is now produced by *some* fixture in Group E. A test asserts this completeness mechanically.

**Exit**: all host_error codes reachable from inside the catalog.

### Phase 11 — Group G (dynamic dispatch)

Requires Phase 9 catalog state + `ctx.catalog`.

- `dynamic_dispatch`, `cond_dispatch`, `cascade`, `meta_planner`.
- First integration smoke: a kind reads the catalog and picks another kind by name.

**Exit**: runtime-computed `kind=` strings work; `ctx.catalog` is exercised.

### Phase 12 — Group H (structured-data shapes)

- `function_map_writer`, `function_map_editor`, `schema_designer`, `ast_transform`, `diff_writer`, `patch_set_writer`.
- Mostly convention round-trip tests; `function_map_writer` is the first kind that fans out a *data-dependent* number of children.

### Phase 13 — Group I (filesystem-shaped, pure-data)

- `directory_input`, `directory_writer`, `repo_walker`, `patch_applier_proxy`.
- `repo_walker` is the first realistic large-fan-out kind. Add explicit tests for the `budget_denied` failure mode when a parent oversizes its split.

### Phase 14 — Groups J, K, L (iterative, composition, introspective)

- J: `refine_until`, `conversation`, `tournament`. `conversation` test validates §7 constraint 4 (no hidden state).
- K: `pipeline`, `transformer`, `precondition_gate`.
- L: `kind_lister`, `kind_chooser`, `catalog_self_test`. `catalog_self_test` runs every registered kind with a minimal input; from this phase forward it is a CI canary.

### Phase 15 — Groups N, O, P

- N (scoring): `rubric_grader`, `pairwise_preference`, `calibration`, `score_aggregator`.
- O (adversarial): `attack_generator`, `adversarial_loop`, `failure_classifier`, `regression_canary`. The first regression_canary lands here as a kind; the *helper* it codifies has been in use since Phase 3.
- P (translation + memo): `convention_adapter`, `chain_with_adapter`, `content_hash_memo`, `dedup_then_map`. `content_hash_memo` validates §7 constraint 5.

### Phase 16 — Cross-cutting contract test sweep

`tests/test_contract_invariants.py`. Sweeps the whole catalog:

- every kind's value is JSON-serializable;
- every kind charges at least one `step` (the host enforces this; test asserts);
- every host_error code is produced by some catalog entry;
- every §7 constraint has positive and negative tests;
- `catalog_self_test` runs every kind with a minimal input, no unexpected `host_error`.

Much of this content accumulates during prior phases; Phase 16 finalizes and gates.

---

## CI strategy

- Default `pytest` invocation runs unit + integration + determinism. Monty is in the loop. No skips.
- `pytest -m "not integration"` for fast local iteration.
- `pytest --record` (custom flag wired in `_golden.py`) regenerates goldens; CI runs without it.
- Golden drift = CI failure; the diff is in `tests/_goldens/`, reviewable like code.
- Coverage target: line coverage on `fleshwound/budget.py`, `runner.py`, `context.py`, `catalog.py`, `provider.py` ≥ 95% by end of Phase 5. Per-kind coverage ≥ 90% at the file the kind lives in.

## Critical path

Phases 0 → 1 → 2 → 3 → 4 → 5 → 8 (`program_writer`). Everything else fans out from those seven phases. The earliest meaningful demo is the end of Phase 8 (a real recursive program-writing run against FakeProvider).

## Out of scope for this plan

- Larql provider implementation (`integration-plan.md` Phase 7) — slots in as an alternative `ModelProvider` once the catalog is complete; every kind's integration tests can then be re-run against a real Larql backend as a `slow` suite.
- Spawned mode — deferred per `spawned-mode-future.md`.
- Streaming output — out of v1 scope per `recursion-contract.md` §4.

## Suggested start

Phase 0 + Phase 1 together. Zero dependencies, unblock everything, and either ships in a single session. After that, Phases 2–5 are a single critical-path sequence and a natural second session.
