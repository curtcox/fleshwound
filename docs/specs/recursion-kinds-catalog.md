# Fleshwound Recursion Kinds Catalog

> This catalog has two jobs. First, it is the reference list of catalog entries that the host ships (or could ship). Second, it is the **contract-stress fixture** for `recursion-contract.md`: each entry calls out the contract clauses it exercises, and the act of enumerating them is how we discover gaps. Unresolved ambiguities are tracked in [`open-contract-issues.md`](open-contract-issues.md).
>
> Kinds are grouped by what they stress, not by likely deployment usefulness. Some are degenerate on purpose.

## Conventions

For each kind:

- **purpose** — what the executor does in plain language.
- **when to use** — typical caller intent; not a deployment recommendation for contract fixtures.
- **similar kinds** — nearby catalog entries that solve overlapping problems.
- **prefer alternatives when** — conditions under which a similar kind is usually the better choice.
- **input** — JSON shape the executor expects.
- **value** — JSON shape it returns inside the `{outcome, value, host_error}` envelope.
- **charges** — what the executor draws from its envelope, beyond the host's auto `charge_step`.
- **uses** — which `ctx.*` primitives the executor invokes.
- **stresses** — which `recursion-contract.md` clauses this entry is the test case for.

Each kind's Python module under `fleshwound/kinds/` repeats the purpose, usage, and comparison notes in its module docstring. The `convention` string registered on the kind is a one-line summary exposed through `ctx.catalog`.

---

## Group A — Degenerate (zero or near-zero work)

### `constant`

- **purpose** — Returns `input["value"]` verbatim; no LLM, no child steps, no Monty.
- **when to use** — Contract baselines, plumbing tests, or when a parent wants a typed leaf that extracts one field from a larger JSON blob.
- **similar kinds** — `echo` (whole-input pass-through); `monty_exec` (compute a return value in Monty).
- **prefer alternatives when** — Use `echo` when the entire input should round-trip unchanged; use `monty_exec` when you need light computation without registering a new kind.
- **input** — `{"value": Any}` (must be JSON-serializable).
- **value** — `input["value"]`, returned verbatim.
- **charges** — nothing (only the host's auto step charge).
- **uses** — none.
- **stresses** — §4 verbatim pass-through; §5.1 zero-token/zero-tool_call requests (Q1); §6.2 "charge step on entry, executor may not need anything else."

### `echo`

- **purpose** — Returns the entire `input` value unchanged; the simplest possible successful step.
- **when to use** — Identity steps in pipelines, budget or envelope smoke tests, and as the inner kind for failure injectors like `budget_hog` (steps target).
- **similar kinds** — `constant` (extracts one field); `monty_exec` (can return arbitrary computed values).
- **prefer alternatives when** — Use `constant` when callers should pass `{"value": ...}` explicitly; use `monty_exec` when the return value depends on logic rather than pass-through.
- **input** — `Any`.
- **value** — `input`, returned verbatim.
- **charges** — nothing.
- **uses** — none.
- **stresses** — §6.0 — an executor that does no work at all; confirms the host wrapper still emits `charge_step` and a well-formed envelope. Identical to `constant` except for input convention; included to test that the **convention** is a documentation concern, not enforced.

### `noop_fail`

- **purpose** — Raises an uncaught exception in host Python before returning a value.
- **when to use** — Host safety-net tests: verify `executor_error` wrapping and that the run survives a failing leaf.
- **similar kinds** — `noop_fail_monty` (raises inside Monty → `monty_error`); `always_host_error` (targets specific host-error codes).
- **prefer alternatives when** — Use `noop_fail_monty` to exercise the Monty executor path; use `always_host_error` when you need a particular `host_error.code`.
- **input** — any (ignored).
- **value** — never reached.
- **charges** — n/a.
- **uses** — none; deliberately raises in host Python.
- **stresses** — §4 host safety net: uncaught Python exception in a non-Monty executor → `host_error{code: "executor_error"}`. Companion `noop_fail_monty` raises inside Monty → `monty_error`. Both must round-trip without crashing the host.

### `noop_fail_monty`

- **purpose** — Runs Monty code that deliberately raises, producing `monty_error` through the Monty executor path.
- **when to use** — Contract tests for Monty-based executors and the distinction between `monty_error` and `executor_error`.
- **similar kinds** — `noop_fail` (host Python exception); `monty_exec` (general Monty execution).
- **prefer alternatives when** — Use `noop_fail` for non-Monty executors; use `monty_exec` when you need controlled Monty behavior rather than a guaranteed failure.
- **input** — any (ignored).
- **value** — never reached.
- **charges** — n/a.
- **uses** — Monty executor; deliberately raises inside Monty.
- **stresses** — §4 host safety net: Monty exception → `monty_error` (companion to `noop_fail`, which raises in host Python → `executor_error`).

### `py_spin`

- **purpose** — Non-Monty infinite loop fixture for pytest-timeout guard tests.
- **when to use** — Verify plain-Python executors are not preempted by Fleshwound compute limits.
- **similar kinds** — `budget_hog` target `spin` (Monty runaway preemption); `noop_fail` (host failure fixtures).
- **prefer alternatives when** — Use `budget_hog` `spin` to test Monty compute preemption.
- **input** — `{"spin"?: bool}`; default idle return when omitted or false.
- **value** — `{"status": "idle"}` or never reached when spinning.
- **charges** — one `step` on entry only.
- **uses** — none when idle; tight `while True` when `spin` is true.
- **stresses** — non-Monty executors rely on external timeout guards, not compute budget.

---

## Group B — Non-recursive leaves (single tool, no children)

### `prose_writer`

- **purpose** — One LLM call that turns a task (and optional context dict) into prose text plus notes.
- **when to use** — Unstructured natural-language generation where you do not need a fixed JSON schema or executable output.
- **similar kinds** — `program_writer` (generates and runs Monty code); `conversation` (multi-turn chat with history in input).
- **prefer alternatives when** — Use `program_writer` when the deliverable is runnable code; use `conversation` when the caller carries full turn history across calls.
- **input** — `{"task": str, "context": dict|None}`.
- **value** — `{"text": str, "notes": str}`.
- **charges** — tokens (one `ctx.llm` call).
- **uses** — `ctx.llm`.
- **stresses** — §4.1 `llm()` always-dict return (success and error paths); §3 charging usage to the active budget including on failure.

### `classifier`

- **purpose** — One LLM call that assigns a label from a fixed list, with optional confidence and rationale extracted from the response.
- **when to use** — Simple categorization, routing labels, or triage where the output shape is fixed but the model text is messy.
- **similar kinds** — `judge` (pass/fail on criteria); `rubric_grader` (multi-criterion scores); `failure_classifier` (classifies StepResult failures).
- **prefer alternatives when** — Use `judge` for binary acceptance; use `rubric_grader` for weighted multi-criterion grading; use `failure_classifier` when the input is already a `StepResult` envelope.
- **input** — `{"text": str, "labels": [str]}`.
- **value** — `{"label": str, "confidence": float|None, "rationale": str}`.
- **charges** — tokens.
- **uses** — `ctx.llm`.
- **stresses** — the kind that **post-processes** the LLM response to coerce it to a fixed shape — i.e. the kind decides how strict to be about its own value convention, the host does not (§6).

### `monty_exec`

- **purpose** — Evaluates Monty `code` with full `ctx.*` bound as externals; returns the final expression value.
- **when to use** — Ad-hoc step logic, predicates, and transforms without registering a dedicated catalog entry; also the escape hatch for custom orchestration in Monty.
- **similar kinds** — `program_writer` (LLM writes then runs Monty); `transformer` (pre/post Monty around a child kind); `precondition_gate` / `cond_dispatch` (Monty predicates only).
- **prefer alternatives when** — Use `program_writer` when an LLM should author the code; use `transformer` when wrapping an existing kind with input/output massage; use dedicated kinds when the logic is stable and reusable.
- **input** — `{"code": str}`.
- **value** — whatever the final expression of `code` evaluates to (must be JSON-serializable).
- **charges** — nothing automatic; if the code calls `ctx.llm` or `ctx.step` it charges accordingly.
- **uses** — Monty interpreter with full `ctx.*` bound as externals.
- **stresses** — §6.0 — Monty is an executor's implementation choice, not a host requirement. Also stresses §4 `malformed_result` when the final expression is non-serializable.

### `ask_user_only`

- **purpose** — Asks one question via `ctx.ask_user` and returns the answer, or a structured unavailable response when no callback was bound.
- **when to use** — Human-in-the-loop leaves, testing `ask_user` gating, or isolating user interaction from delegation logic.
- **similar kinds** — `clarify_then_delegate` (optional ask, then child step); `rlm_loop` (can ask via protocol actions when wired).
- **prefer alternatives when** — Use `clarify_then_delegate` when clarification should feed a downstream kind; use a custom parent when you need multiple questions in one step.
- **input** — `{"question": str}`.
- **value** — `{"answer": str}` on success; `{"answer": null, "notes": "ask_user unavailable"}` when the parent did not bind one.
- **charges** — nothing.
- **uses** — `ctx.ask_user`.
- **stresses** — §3 explicit "`ask_user` is not charged"; the gating behavior when `ctx.ask_user is None`.

---

## Group C — Recursive coordinators (use `ctx.step`)

### `program_writer`

- Canonical entry; prompt asset in `fleshwound/kinds/program_writer_prompt.md`.
- **purpose** — LLM generates Monty-subset Python from a task, then executes it via `monty_run`, returning `{status, program, notes}` (and optional error detail).
- **when to use** — Primary path for budget-bounded program writing: turn a natural-language task into runnable in-process code with explicit partial/error status.
- **similar kinds** — `prose_writer` (text only); `monty_exec` (caller supplies code); `function_map_writer` (fans out to one `program_writer` per signature); `directory_input` (wraps repo context).
- **prefer alternatives when** — Use `prose_writer` for non-code output; use `monty_exec` when code is already known; use `function_map_writer` for many related functions; use `rlm_loop` for multi-iteration reasoning with structured actions.
- **stresses** — almost everything: §5 budget partition; §5.2 refund-on-every-close; §4 host safety nets; the value convention vs. host outcome distinction (`status` vs. `outcome`).

### `map_reduce`

- **purpose** — Maps each item through `map_kind` sequentially, collects values (and error indices), optionally reduces via `reduce_kind`.
- **when to use** — Homogeneous fan-out over a list where each element gets the same kind and per-item failures should not abort the whole map.
- **similar kinds** — `dedup_then_map` (collapses duplicate items by hash); `repo_walker` (fan-out over virtual file paths); `pipeline` (sequential stages, not parallel items).
- **prefer alternatives when** — Use `dedup_then_map` when many items repeat; use `repo_walker` when inputs are keyed by path with a filter predicate; use `pipeline` when stages depend on prior stage output, not independent items.
- **input** — `{"items": [Any], "map_kind": str, "reduce_kind": str|null}`.
- **value** — `{"mapped": [Any], "reduced": Any|null, "errors": [int]}`.
- **charges** — N child step allocations (sequential); optionally one more for reduce.
- **uses** — `ctx.step` once per item, then once for reduce.
- **stresses** — sequential-only execution (§7 no concurrency); per-child `kind=` override on `step()`; how a parent recovers when individual children come back as `host_error` without aborting the whole map.

### `retry_wrapper`

- **purpose** — Calls `inner_kind` up to `max_attempts` times until `outcome == "ok"`, returning attempt count and the last envelope.
- **when to use** — Transient failures (model flake, occasional `monty_error`) where re-allocation and refund semantics must be exercised.
- **similar kinds** — `cascade` (try different kinds, not repeats); `refine_until` (iterate with a judge, not identical retries); `ensemble` (multiple successes aggregated).
- **prefer alternatives when** — Use `cascade` when fallbacks differ by kind; use `refine_until` when each round should change the candidate; use `ensemble` when you want diverse successes, not the first ok.
- **input** — `{"inner_input": Any, "inner_kind": str, "max_attempts": int}`.
- **value** — `{"attempts": int, "result": StepResult}` (the inner envelope is exposed verbatim).
- **charges** — up to `max_attempts` child step allocations; the parent must size each request to leave reserve.
- **uses** — `ctx.step` in a loop, branching on returned `outcome` / `host_error.code`.
- **stresses** — §5.2 refund correctness — a `budget_denied` or `monty_error` child must return its envelope to the parent so a retry has budget to spend; without correct refunds this kind is unusable.

### `ensemble`

- **purpose** — Runs `inner_kind` `n` times on the same input, then optionally uses one LLM call to pick or synthesize from ok candidate values.
- **when to use** — Diversity sampling (multiple drafts) with LLM aggregation when quality varies run-to-run under the same seed-derived child budgets.
- **similar kinds** — `tournament` (pairwise elimination); `map_reduce` (different inputs per child); `retry_wrapper` (stop at first success).
- **prefer alternatives when** — Use `tournament` when candidates should compete head-to-head; use `map_reduce` when each child gets different input; use `retry_wrapper` when attempts are redundant, not diverse.
- **input** — `{"inner_input": Any, "inner_kind": str, "n": int, "aggregator_prompt": str}`.
- **value** — `{"chosen": Any, "candidates": [Any]}`.
- **charges** — `n` step calls (sequential) plus one `ctx.llm` to aggregate.
- **uses** — `ctx.step` × n, then `ctx.llm`.
- **stresses** — deterministic ordering of sibling child IDs (§3 of `budget-ledger.md` — 1-based by allocation order); each sibling's seed differs by `budget_id`.

### `judge`

- **purpose** — One LLM call that evaluates a candidate against prose criteria and returns pass/fail plus rationale.
- **when to use** — Binary acceptance checks in composition (`refine_until`, manual pipelines) without a full rubric.
- **similar kinds** — `rubric_grader` (multi-criterion weighted scores); `pairwise_preference` (compare two candidates); `classifier` (pick from labels).
- **prefer alternatives when** — Use `rubric_grader` for graded feedback or weighted totals; use `pairwise_preference` inside brackets; use `classifier` for label sets, not pass/fail criteria.
- **input** — `{"candidate": Any, "criteria": str}`.
- **value** — `{"verdict": "pass"|"fail", "rationale": str}`.
- **charges** — tokens.
- **uses** — `ctx.llm`.
- **stresses** — composes with `ensemble`/`retry_wrapper`; this entry exists to confirm value pass-through chains cleanly. (Not recursive itself.)

### `clarify_then_delegate`

- **purpose** — Optionally asks the user one clarifying question, then delegates the (possibly enriched) task to `child_kind`.
- **when to use** — Human clarification before expensive recursion, or demonstrating explicit surfacing of missing information in the value.
- **similar kinds** — `ask_user_only` (question only); `dynamic_dispatch` (pick kind, no user); `program_writer` (may assume context without asking).
- **prefer alternatives when** — Use `ask_user_only` to test ask_user in isolation; use `dynamic_dispatch` when kind selection is the main decision; use `rlm_loop` for multi-turn agentic clarification.
- **input** — `{"task": str, "child_kind": str}`.
- **value** — `{"clarification_q": str|null, "clarification_a": str|null, "result": StepResult}`.
- **charges** — optionally one ask_user; one child step.
- **uses** — `ctx.ask_user` (conditionally), `ctx.step`.
- **stresses** — `ask_user`'s availability gating threaded through to an explicit field on the value; demonstrates that step authors, not the host, decide how to surface "I had to assume X."

---

## Group D — Default-policy stressors

### `random_pick`

- **purpose** — Delegates `inner_input` to one child kind chosen by the host's `"random"` default policy (seed-derived).
- **when to use** — Testing §6.3 seed-stable random default resolution and recording which kind was allocated on the ledger.
- **similar kinds** — `subset_pick` (random within a named subset); `dynamic_dispatch` (explicit or LLM-chosen kind); `kind_chooser` (LLM picks without delegating in the same step).
- **prefer alternatives when** — Use `subset_pick` to constrain candidates; use `dynamic_dispatch` when the chooser logic is explicit or LLM-driven; use `kind_chooser` when you only need a name, not execution.
- **input** — `{"inner_input": Any}`.
- **value** — `{"result": StepResult}`.
- **charges** — one child step.
- **uses** — `ctx.step` with `kind=None` and `default_policy="random"`.
- **stresses** — §6.3 seed derivation. Two runs with the same `run_seed` and parent `budget_id` must pick the same child kind. (Which kind was picked is recorded on the `allocate_child` ledger event; the envelope does not surface it.)

### `subset_pick`

- **purpose** — Delegates with `default_policy={"random_from_subset": subset}`, picking uniformly among listed kind names (deduped).
- **when to use** — Constrained random dispatch tests: empty subset, unknown names, and seed-stable picks within a fixed menu.
- **similar kinds** — `random_pick` (full catalog random); `cond_dispatch` (deterministic Monty branches); `dynamic_dispatch` (runtime-chosen kind string).
- **prefer alternatives when** — Use `random_pick` when any catalog kind is allowed; use `cond_dispatch` when rules are deterministic; use `dynamic_dispatch` when the kind name is computed outside default policy.
- **input** — `{"inner_input": Any, "subset": [str]}`.
- **value** — `{"result": StepResult}`.
- **uses** — `ctx.step` with `default_policy={"random_from_subset": subset}`.
- **stresses** — §6.3 edge cases: empty subset → `unresolvable_default`; unknown name → `unknown_kind`; dedup of repeated names.

### `inherit_chain`

- **purpose** — Recursively calls itself with `kind=None` and `same_as_parent` until `depth` reaches the allocation floor, building a trace of visited kind names.
- **when to use** — Testing depth decrement-on-allocate, `same_as_parent` resolution, and `budget_denied` when depth bottoms out.
- **similar kinds** — `infinite_descent` (self-recursion until budget denial); `pipeline` (different kinds per stage).
- **prefer alternatives when** — Use `infinite_descent` to stress step budget exhaustion vs depth; use explicit `pipeline` when each hop should change kind or input shape.
- **input** — `{"task": str, "depth": int}`.
- **value** — `{"trace": [str]}` (kinds visited in order).
- **uses** — `ctx.step` with no `kind=`, relying on `same_as_parent`.
- **stresses** — §6.3 corrected `same_as_parent` semantics (always resolvable inside an executor); §5 depth decrement-on-allocate; depth bottoming out as `budget_denied`.

---

## Group E — Failure-mode injectors (for testing the host)

### `always_host_error`

- **purpose** — Test fixture that triggers a specific `host_error.code` via raise, malformed return, or budget denial depending on `input.code`.
- **when to use** — Exhaustive host-error-path regression paired with `catalog_self_test` and parent recovery logic.
- **similar kinds** — `noop_fail` / `noop_fail_monty` (generic executor/Monty failures); `budget_hog` (`budget_exhausted`); `infinite_descent` (`budget_denied`).
- **prefer alternatives when** — Use `noop_fail*` for generic safety nets; use `budget_hog` or `infinite_descent` for budget-dimension-specific behavior; use this kind when you need a particular code string.
- **input** — `{"code": str}` (one of the §4 host-error codes).
- **value** — never reached.
- **uses** — none; the executor immediately raises an exception that the host would convert to that code, **or** returns a malformed value, **or** issues a budget_request that will be denied.
- **stresses** — every `host_error.code`. One instance per code, exercised as a fixture.

### `always_partial`

- **purpose** — Always returns a `program_writer`-shaped value with `status: "partial"` and empty program.
- **when to use** — Tests that parents treat convention-level partial as ok `outcome`, not `host_error`.
- **similar kinds** — `program_writer` (real partial on empty model output); `noop_fail` (host_error, not partial).
- **prefer alternatives when** — Use `program_writer` with a task that yields partial naturally; use `noop_fail` when testing hard failures, not soft partial completion.
- **input** — `{}`.
- **value** — `{"status": "partial", "program": "", "notes": "deliberate partial for tests"}`.
- **stresses** — the `program_writer` convention's `status: "partial"` path — parents that wrap this kind must accept partial and not interpret it as `host_error`.

### `budget_hog`

- **purpose** — Burns one budget dimension (`tokens`, `steps`, or `tool_calls`) to zero, then attempts one more primitive call to observe `budget_exhausted`.
- **when to use** — Contract tests for mid-execution budget exhaustion at host-primitive boundaries.
- **similar kinds** — `infinite_descent` (`budget_denied` via depth); `always_host_error` (arbitrary codes); `noop_fail` (exception, not budget).
- **prefer alternatives when** — Use `infinite_descent` for depth-floor denial; use `always_host_error` for non-exhaustion codes; use real workloads to test token limits in integration tests.
- **input** — `{"target": "tokens"|"steps"|"tool_calls"|"spin"|"recurse", "stop_on_exhaustion"?: bool}`.
- **uses** — burns the targeted dimension to zero, then attempts one more call → must observe `host_error{code: "budget_exhausted"}` on the next `ctx.llm` / `ctx.step` call. Targets `spin` and `recurse` run Monty runaway loops to observe compute-budget preemption.
- **stresses** — §4 `budget_exhausted` surfaces as a value, not an exception; mid-execution stopping at host-primitive boundaries and Monty compute limits.

### `infinite_descent`

- **purpose** — Recursively self-calls with shrinking step/depth budget until child allocation fails with `budget_denied`.
- **when to use** — Confirm depth floor (§5.1) halts chains and that denial is distinct from `budget_exhausted`.
- **similar kinds** — `inherit_chain` (same kind, depth counter in input); `budget_hog` (exhaust a dimension inside one step).
- **prefer alternatives when** — Use `inherit_chain` when you need an explicit trace of kind names; use `budget_hog` when testing exhaustion inside a leaf, not recursive allocation failure.
- **input** — `{}`.
- **uses** — recursively `ctx.step({}, request={steps: parent.steps - 1, depth: parent.depth - 1, tokens: 0, tool_calls: 0})` until depth hits 1.
- **stresses** — depth termination produces `budget_denied` (not `budget_exhausted`); confirms that `depth >= 1` floor (§5.1) is what halts the chain, not steps.

---

## Group F — Provider / override

### `provider_swap`

- **purpose** — Runs `inner_kind` under an overridden `provider`, demonstrating per-subtree provider inheritance.
- **when to use** — Multi-model pipelines (cheap planner, expensive writer) and provider override contract tests.
- **similar kinds** — `transformer` (wrap one kind with pre/post logic); `pipeline` (sequential kinds, default same provider unless each step overrides).
- **prefer alternatives when** — Use per-stage `provider=` in a custom parent when only some hops swap models; use `pipeline` when provider is uniform across stages.
- **input** — `{"inner_input": Any, "inner_kind": str, "inner_provider": ProviderConfig}`.
- **uses** — `ctx.step(..., provider=new_provider)`.
- **stresses** — §3 `provider=` override is per-subtree, not per-call; the child's subsequent grandchildren inherit the new provider unless they override again.

---

---

## Group G — Dynamic dispatch (kind chosen at runtime)

### `dynamic_dispatch`

- **purpose** — Chooses a kind name (literal or via LLM over `ctx.catalog`), then delegates `inner_input` with `kind=chosen_kind`.
- **when to use** — Runtime routing when the target kind is not known at plan time; tests `unknown_kind` when the chooser hallucinates.
- **similar kinds** — `meta_planner` (LLM emits a multi-step plan); `cond_dispatch` (Monty predicates, no LLM); `kind_chooser` (pick only, no step); `subset_pick` / `random_pick` (host default policy).
- **prefer alternatives when** — Use `meta_planner` for multi-step decomposition; use `cond_dispatch` for deterministic rules; use `kind_chooser` + separate parent when selection and execution should split; use default-policy picks for seeded randomness without explicit names.
- **input** — `{"chooser": "literal"|"llm", "literal_kind": str|null, "task_for_chooser": str|null, "inner_input": Any}`.
- **value** — `{"chosen_kind": str, "result": StepResult}` — `chosen_kind` is the string this kind itself computed and passed to `ctx.step`; it knows it because it produced it, not because the host reported it.
- **uses** — optionally `ctx.llm` to pick a kind name (Monty assembles a prompt listing `ctx.catalog`), then `ctx.step(inner_input, request, kind=chosen_kind)`.
- **stresses** — that `kind=` accepts a runtime-computed string (`recursion-contract.md` §3); host's `unknown_kind` path when the chooser hallucinates a name; `ctx.catalog` introspection (`recursion-contract.md` §3).

### `meta_planner`

- **purpose** — One LLM call produces a JSON plan of `{kind, input}` steps, then executes them sequentially via `ctx.step`.
- **when to use** — LLM-driven multi-step workflows where decomposition shape and kind choice are both model decisions.
- **similar kinds** — `pipeline` (caller-defined stages); `dynamic_dispatch` (single delegated step); `rlm_loop` (iterative actions with trace).
- **prefer alternatives when** — Use `pipeline` when stages are fixed and trusted; use `dynamic_dispatch` for one hop; use `rlm_loop` when the model must observe intermediate results before the next action.
- **input** — `{"task": str}`.
- **value** — `{"plan": [{"kind": str, "input": Any}], "results": [StepResult]}`.
- **uses** — one `ctx.llm` to produce a JSON plan, then a sequential loop of `ctx.step` per plan item.
- **stresses** — kinds-as-data: the catalog is materially exposed to the LLM and the model decides decomposition shape, not just content.

### `cascade`

- **purpose** — Tries `kinds[]` in order via `ctx.step`, stopping at the first ok result that satisfies an optional Monty `stop_predicate`.
- **when to use** — Fallback chains (cheap kind first, expensive later) where failed attempts must refund budget for the next try.
- **similar kinds** — `retry_wrapper` (same kind, repeated); `cond_dispatch` (predicate picks kind before one call); `ensemble` (all attempts kept).
- **prefer alternatives when** — Use `retry_wrapper` for identical retries; use `cond_dispatch` when input determines the kind upfront; use `ensemble` when every attempt's output matters.
- **input** — `{"inner_input": Any, "kinds": [str], "stop_predicate": str}`.
- **value** — `{"chosen_kind": str|null, "result": StepResult, "tried": [str]}`.
- **uses** — `ctx.step` for each kind in `kinds` in order, stopping when the predicate (a small Monty expression over the returned value) is satisfied.
- **stresses** — refund correctness: each failed attempt must refund into the parent envelope so the next attempt has budget.

### `cond_dispatch`

- **purpose** — Evaluates Monty `when` predicates on `inner_input` in branch order, dispatching to the first matching `kind` or `default_kind`.
- **when to use** — Deterministic routing without an LLM round; baseline for comparing against `meta_planner` and `dynamic_dispatch`.
- **similar kinds** — `dynamic_dispatch` (LLM or literal kind choice); `precondition_gate` (predicate gates a single inner kind); `subset_pick` (random among names).
- **prefer alternatives when** — Use `dynamic_dispatch` when rules are too fuzzy for Monty; use `precondition_gate` when there is only one candidate kind; use `subset_pick` for intentional nondeterminism within a set.
- **input** — `{"branches": [{"when": str, "kind": str}], "default_kind": str|null, "inner_input": Any}`.
- **value** — `{"chosen_kind": str, "result": StepResult}`.
- **uses** — evaluates each `when` (Monty predicate over `inner_input`) and dispatches; falls through to `default_kind`.
- **stresses** — pure-Monty dispatch without an LLM round; useful as a deterministic baseline for `meta_planner`.

---

## Group H — Structured-data shapes (the user's "function map" family)

### `function_map_writer`

- **purpose** — For each entry in `signatures`, calls `program_writer` (or could batch via LLM) and returns a map of generated function sources keyed by name.
- **when to use** — Generating many related Monty functions from signature/docstring specs with explicit `missing` tracking.
- **similar kinds** — `program_writer` (single function/task); `function_map_editor` (edit existing map); `directory_input` (repo-shaped context).
- **prefer alternatives when** — Use `program_writer` for one function; use `function_map_editor` for incremental edits; use a single `prose_writer` or `monty_exec` when outputs are not a named function map.
- **input** — `{"signatures": {name: {"signature": str, "docstring": str}}, "context": dict|None}`.
- **value** — `{"functions": {name: {"source": str, "notes": str}}, "missing": [str]}`.
- **uses** — typically one `ctx.step(kind="program_writer")` per function for medium-large maps; for small maps a single `ctx.llm`.
- **stresses** — fan-out where the count of children is data-dependent; aggregation back into a map keyed by the same names; convention that the result's keys must be a subset of the input's keys (kind-enforced, not host-enforced).

### `function_map_editor`

- **purpose** — Pure-data transform: applies remove/add/update edits to an existing function map and reports `removed` / `added` keys explicitly.
- **when to use** — Incremental map maintenance without re-generating unchanged functions; diff-friendly updates in tests.
- **similar kinds** — `function_map_writer` (create from signatures); `patch_set_writer` (file diffs); `convention_adapter` (translate between kind value shapes).
- **prefer alternatives when** — Use `function_map_writer` for greenfield generation; use `patch_set_writer` for whole-file edits; use LLM kinds when edits need semantic reasoning beyond structural ops.
- **input** — `{"current": {name: {"source": str}}, "edits": [{"name": str, "instruction": str}]}`.
- **value** — `{"updated": {name: {"source": str}}, "removed": [str], "added": [str]}`.
- **stresses** — in-place transform shape: same data type in and out; `removed` and `added` keys make the diff explicit so callers don't have to diff themselves.

### `schema_designer`

- **purpose** — One LLM call that proposes a JSON Schema document plus rationale for a domain (optionally with examples).
- **when to use** — Upfront schema design before `program_writer` or structured outputs; contract tests for LLM JSON parsing fallbacks.
- **similar kinds** — `prose_writer` (unstructured); `classifier` (fixed label set, not schema); `ast_transform` (transform existing structured data).
- **prefer alternatives when** — Use `prose_writer` when a formal schema is unnecessary; use hand-authored schema in input when the shape is already known.
- **input** — `{"domain": str, "examples": [Any]|null}`.
- **value** — `{"schema": dict, "rationale": str}` — `schema` is a JSON Schema document.
- **uses** — `ctx.llm`.

### `ast_transform`

- **purpose** — Stub that round-trips a JSON-encoded AST and records the transform string as `changes` (placeholder for LLM/Monty transform pipelines).
- **when to use** — Tests that deeply nested JSON values serialize cleanly; starting point before wiring real transform logic.
- **similar kinds** — `transformer` (pre/post around a child kind); `monty_exec` (general AST manipulation in Monty); `function_map_editor` (map-shaped edits).
- **prefer alternatives when** — Use `transformer` or `monty_exec` for real transforms; use `function_map_editor` when editing named function sources, not generic AST nodes.
- **input** — `{"ast": dict, "transform": str}` — `ast` is a JSON-encoded AST in any convention; `transform` is prose.
- **value** — `{"ast": dict, "changes": [str]}`.
- **stresses** — value being a recursive nested structure that round-trips JSON; confirms there is no hidden depth limit on `value` (other than JSON's own).

### `diff_writer`

- **purpose** — One LLM call that produces a unified diff for a single file given current content and a change description.
- **when to use** — Single-file edit proposals the caller will apply outside the sandbox.
- **similar kinds** — `patch_set_writer` (multi-file patches); `directory_writer` (whole virtual tree); `patch_applier_proxy` (validate/apply patch data).
- **prefer alternatives when** — Use `patch_set_writer` for coordinated multi-file changes; use `directory_writer` when structure matters more than line-level diffs; use `program_writer` when the deliverable is executable code, not a diff.
- **input** — `{"file": str, "content": str, "change": str}`.
- **value** — `{"diff": str, "format": "unified"}`.

### `patch_set_writer`

- **purpose** — One LLM call that returns a list of `{path, diff}` patches for multiple files from a task description.
- **when to use** — Batch edit planning across a virtual file set before caller-side application.
- **similar kinds** — `diff_writer` (one file); `directory_writer` (full tree generation); `patch_applier_proxy` (simulate apply).
- **prefer alternatives when** — Use `diff_writer` for a single file; use `directory_writer` for greenfield tree creation; use `repo_walker` + per-file kinds when each file needs different processing.
- **input** — `{"files": {path: str}, "task": str}`.
- **value** — `{"patches": [{"path": str, "diff": str}]}`.
- **stresses** — companion to `directory_input`; produces a structure that a caller can mechanically apply without re-prompting the model.

---

## Group I — Filesystem-backed I/O (without granting executors FS access)

> v1 stance: kinds **never** touch the filesystem. The caller materializes input from disk into a JSON blob and writes outputs back. This keeps determinism and sandboxing tight; direct FS access would require a new host primitive (`recursion-contract.md` §3; Group M below).

### `directory_input`

- **purpose** — Assembles prose context from a virtual `tree` and delegates to `program_writer` with the caller's `task`.
- **when to use** — Repo-shaped tasks where the caller materialized files into JSON (no executor filesystem access).
- **similar kinds** — `program_writer` (direct task/context); `repo_walker` (per-file child steps); `directory_writer` (symmetric output side).
- **prefer alternatives when** — Use `program_writer` when context is already a dict; use `repo_walker` when each file needs its own kind; use `patch_set_writer` when the goal is diffs, not new programs.
- **input** — `{"tree": {path: {"content": str, "mode": str}}, "task": str}` — a virtual tree, keyed by path relative to a notional root.
- **value** — defined by the task; this kind is a thin wrapper that delegates to e.g. `program_writer` after assembling a prose `context` from the tree.
- **stresses** — large inputs (a repo subtree may be megabytes of JSON); tests that the contract has no implicit size limit but also surfaces that `value` size will hit the provider's token limit long before the host's JSON limit.

### `directory_writer`

- **purpose** — One LLM call that generates a virtual directory tree (`tree` + `notes`) matching a task and shape hint.
- **when to use** — Greenfield scaffold generation the caller persists to disk outside the host.
- **similar kinds** — `directory_input` (consume tree → program); `patch_set_writer` (modify existing paths via diffs); `function_map_writer` (code map, not file tree).
- **prefer alternatives when** — Use `patch_set_writer` when starting from existing content; use `directory_input` + `program_writer` when code must be executed/validated in-process.
- **input** — `{"task": str, "shape": "tree"|"flat"}`.
- **value** — `{"tree": {path: {"content": str, "mode": str}}, "notes": str}`.
- **stresses** — symmetric to `directory_input`; combined, the pair lets the caller (not the kind) own all FS state.

### `repo_walker`

- **purpose** — Filters paths in a virtual `tree` with a Monty `predicate`, then runs `per_file_kind` once per match.
- **when to use** — Large fan-out over files where each match gets the same kind but separate budget allocation.
- **similar kinds** — `map_reduce` (list fan-out); `dedup_then_map` (unique items only); `pipeline` (sequential dependency).
- **prefer alternatives when** — Use `map_reduce` for homogeneous lists without path keys; use `dedup_then_map` when many paths share identical content; size child budgets carefully—this kind is a common source of parent `budget_denied`.
- **input** — `{"tree": {path: ...}, "per_file_kind": str, "predicate": str}`.
- **value** — `{"per_file": {path: StepResult}}`.
- **uses** — one `ctx.step` per matching path.
- **stresses** — large fan-out plus per-child budget sizing decisions; this is where parents will most often hit `budget_denied` because they evenly divided budget over too many files.

### `patch_applier_proxy`

- **purpose** — Pure-data simulation of patch application: validates paths/diffs and returns applied vs rejected lists without touching disk.
- **when to use** — Test patch shapes paired with caller-side real appliers; model FS intent inside the contract boundary.
- **similar kinds** — `patch_set_writer` / `diff_writer` (produce patches); `function_map_editor` (structural map edits).
- **prefer alternatives when** — Use writer kinds to generate patches; use caller code for actual filesystem mutation (v1 has no FS primitive).
- **input** — `{"patches": [...]}`.
- **value** — `{"applied": [str], "rejected": [{"path": str, "reason": str}]}`.
- **stresses** — this is a **pure-data** kind: it simulates application but doesn't touch disk. Pairs with a caller-side real applier. The point: even FS-mutating intent is modelable inside the contract by emitting structured outputs.

---

## Group J — Iterative / multi-turn

### `refine_until`

- **purpose** — Alternates `inner_kind` (candidate) and `judge_kind` (verdict) up to `max_rounds`, stopping when verdict JSON contains `"pass"`.
- **when to use** — Iterative improvement loops with an explicit judge kind (often `judge` or `rubric_grader`).
- **similar kinds** — `retry_wrapper` (identical retries); `rlm_loop` (richer action protocol); `tournament` (pick best among fixed candidates).
- **prefer alternatives when** — Use `retry_wrapper` when failures are transient, not quality-based; use `rlm_loop` when the model must plan multi-action iterations; use `ensemble` when parallel drafts beat sequential refinement.
- **input** — `{"inner_input": Any, "inner_kind": str, "judge_kind": str, "max_rounds": int, "judge_pass_predicate": str}`.
- **value** — `{"rounds": int, "history": [{"candidate": Any, "verdict": Any}], "final": Any}`.
- **uses** — alternating `ctx.step(inner_kind, ...)` and `ctx.step(judge_kind, ...)`.
- **stresses** — composition of two kinds in a loop; budget shrinkage round-over-round (parents must size the loop's total envelope).

### `conversation`

- **purpose** — One LLM turn: appends an assistant reply to the caller-supplied `turns` history and returns updated turns (no hidden host state).
- **when to use** — Chat-style steps where determinism requires the full history in every `input`.
- **similar kinds** — `prose_writer` (single-shot text); `rlm_loop` (multi-iteration agent with actions); `clarify_then_delegate` (one user question then delegate).
- **prefer alternatives when** — Use `prose_writer` for one-off generation; use `rlm_loop` for tool/step actions between turns; use an outer loop in the caller to chain multiple `conversation` steps explicitly.
- **input** — `{"system": str, "turns": [{"role": str, "content": str}]}`.
- **value** — `{"reply": str, "turns": [...]}` — the turns appended with the new exchange.
- **uses** — `ctx.llm` once.
- **stresses** — that there is **no hidden state** between calls: the entire conversation history must be carried in `input`. The contract's determinism property depends on this; this kind exists partly to make the invariant explicit.

### `tournament`

- **purpose** — Single-elimination bracket: pairwise `judge_kind` comparisons over `candidates` until one winner remains.
- **when to use** — Selecting the best among N fixed candidates when pairwise comparison is cheaper than N-way rubric grading.
- **similar kinds** — `ensemble` (N independent runs + aggregate LLM); `pairwise_preference` (one comparison); `rubric_grader` (score each candidate fully).
- **prefer alternatives when** — Use `ensemble` when candidates are stochastic samples of the same process; use `pairwise_preference` alone for a single A/B; use `rubric_grader` when you need numeric scores, not bracket elimination.
- **input** — `{"candidates": [Any], "judge_kind": str}`.
- **value** — `{"winner": Any, "bracket": [...]}`.
- **uses** — log₂(N) rounds of pairwise `ctx.step(judge_kind, ...)`.
- **stresses** — N children sequential; deterministic bracket ordering tied to `budget_id` numbering.

---

## Group K — Composition

### `pipeline`

- **purpose** — Runs `stages[]` sequentially, threading each ok stage's `value` as the next stage's input (optional Monty `transform_input` not wired in v1 impl).
- **when to use** — Fixed multi-step workflows where stage order and kind names are caller-defined.
- **similar kinds** — `meta_planner` (LLM-defined plan); `chain_with_adapter` (three-step with convention translation); `transformer` (single inner kind with pre/post).
- **prefer alternatives when** — Use `meta_planner` when decomposition should be model-driven; use `chain_with_adapter` when middle step adapts conventions; use `transformer` for one wrapped kind with Monty massage.
- **input** — `{"stages": [{"kind": str, "transform_input": str|null}], "initial": Any}`.
- **value** — `{"stages": [StepResult], "final": Any}`.
- **uses** — sequential `ctx.step` with each stage's value feeding the next (optionally massaged by a Monty `transform_input` snippet).

### `transformer`

- **purpose** — Optional Monty preprocess on `inner_input_template`, one `ctx.step` to `inner_kind`, optional Monty postprocess on the result.
- **when to use** — Reuse an existing kind with input/output adaptation without registering a variant catalog entry.
- **similar kinds** — `monty_exec` (all logic in one Monty snippet); `convention_adapter` (LLM translation between kind conventions); `precondition_gate` (predicate only, no postprocess).
- **prefer alternatives when** — Use `convention_adapter` when shapes differ by catalog convention, not simple field mapping; use `monty_exec` when no child kind is needed; use dedicated kinds when the wrapper is stable and shared.
- **input** — `{"preprocess": str, "inner_kind": str, "postprocess": str, "inner_input_template": Any}`.
- **value** — postprocessed value of the inner step.
- **stresses** — wrappers around existing kinds without needing to register a new entry per variant.

### `precondition_gate`

- **purpose** — Evaluates a Monty `predicate` on `inner_input`; skips `ctx.step` and returns `gated: true` when false.
- **when to use** — Cheap guards before expensive child steps; deterministic eligibility checks.
- **similar kinds** — `cond_dispatch` (pick among kinds by predicate); `retry_wrapper` (run inner either way after failures); `cascade` (try kinds until predicate on result).
- **prefer alternatives when** — Use `cond_dispatch` to route among multiple kinds; use `cascade` when fallback kinds exist; use `monty_exec` when guard and work belong in one snippet.
- **input** — `{"predicate": str, "inner_kind": str, "inner_input": Any}`.
- **value** — either the inner result or `{"gated": true, "reason": str}`.
- **uses** — Monty evaluates `predicate` against `inner_input`; if false, no `ctx.step` is made.

---

## Group L — Catalog-aware / introspective

### `kind_lister`

- **purpose** — Returns sorted catalog names and one-line `convention` strings from `ctx.catalog`.
- **when to use** — Introspection, debugging, and regression that `ctx.catalog` stays wired for a run.
- **similar kinds** — `kind_chooser` (LLM picks one kind for a task); `catalog_self_test` (executes kinds); `dynamic_dispatch` (uses catalog for LLM chooser prompts).
- **prefer alternatives when** — Use `kind_chooser` when you need a recommendation, not the full list; use `catalog_self_test` to validate behavior, not metadata alone.
- **input** — `{}`.
- **value** — `{"kinds": [{"name": str, "convention": str}]}`.
- **uses** — reads `ctx.catalog`.
- **stresses** — `ctx.catalog` introspection (`recursion-contract.md` §3); this kind is the regression canary that the primitive stays wired.

### `kind_chooser`

- **purpose** — One LLM call that selects a catalog kind name for a task using rendered `ctx.catalog` entries.
- **when to use** — Planning/routing step where execution happens in a separate parent call.
- **similar kinds** — `dynamic_dispatch` (choose and run); `meta_planner` (multi-step plan); `random_pick` (seeded random, no LLM).
- **prefer alternatives when** — Use `dynamic_dispatch` to choose and delegate in one step; use `meta_planner` for ordered multi-kind plans; use `random_pick` for contract tests of default policy, not task fit.
- **input** — `{"task": str}`.
- **value** — `{"chosen_kind": str, "rationale": str}`.
- **uses** — `ctx.llm` with `ctx.catalog` rendered into the prompt.

### `catalog_self_test`

- **purpose** — Runs minimal viable input through each catalog kind (or a subset) via `ctx.step` and collects outcomes.
- **when to use** — Broad regression sweeps paired with `always_host_error` fixtures and `_minimal_input.py`.
- **similar kinds** — `regression_canary` (one frozen hash); `kind_lister` (metadata only); `noop_fail` (single failure mode).
- **prefer alternatives when** — Use `regression_canary` for golden-hash determinism on one kind; use targeted pytest for single-kind behavior; use `kind_lister` when you only need names, not execution.
- **input** — `{"kinds_to_exercise": [str]|null}`.
- **value** — `{"results": [{"kind": str, "outcome": str, "host_error": ...}]}`.
- **uses** — one `ctx.step` per kind, with each kind's smallest viable input.
- **stresses** — every host-error code (paired with `always_host_error` fixtures from Group E).

---

---

## Group N — Scoring and grading

### `rubric_grader`

- **purpose** — LLM grades a candidate against a weighted rubric, returning per-criterion scores and `weighted_total`.
- **when to use** — Multi-criterion evaluation upstream of `tournament`, `refine_until`, or `calibration`.
- **similar kinds** — `judge` (binary pass/fail); `pairwise_preference` (A vs B); `score_aggregator` (combine scores without LLM).
- **prefer alternatives when** — Use `judge` for simple accept/reject; use `pairwise_preference` in brackets; use `score_aggregator` when scores already exist.
- **input** — `{"candidate": Any, "rubric": [{"criterion": str, "weight": float, "scale": "0-1"|"0-5"|"pass-fail"}]}`.
- **value** — `{"scores": [{"criterion": str, "score": float, "rationale": str}], "weighted_total": float, "notes": str}`.
- **uses** — `ctx.llm` per criterion (or batched into one call for small rubrics).
- **stresses** — composes upstream of `tournament`, `refine_until`, and `ensemble`; demonstrates that `judge` was a binary special case of this.

### `pairwise_preference`

- **purpose** — One LLM call comparing `a` and `b` under a criterion, returning winner (`a`|`b`|`tie`) plus rationale.
- **when to use** — Atomic comparison for `tournament` brackets or standalone A/B evaluation.
- **similar kinds** — `judge` (single candidate vs criteria); `tournament` (full bracket); `ensemble` (aggregate many runs).
- **prefer alternatives when** — Use `judge` when only one candidate exists; use `tournament` for full elimination; use `rubric_grader` for numeric multi-criterion scores on one candidate.
- **input** — `{"a": Any, "b": Any, "criterion": str}`.
- **value** — `{"winner": "a"|"b"|"tie", "rationale": str, "confidence": float}`.
- **uses** — `ctx.llm`.
- **stresses** — the unit operation under `tournament`; isolating it from the loop lets the bracket reason about ties.

### `calibration`

- **purpose** — Runs `grader_kind` on each labeled example, compares predicted scores to `gold_score`, returns agreement and bias stats.
- **when to use** — Meta-evaluation of graders/judges; budget-sizing exercises with fan-out `len(examples)`.
- **similar kinds** — `regression_canary` (hash match one fixture); `catalog_self_test` (breadth over kinds); `rubric_grader` (the grader being measured).
- **prefer alternatives when** — Use `regression_canary` for single golden outputs; use offline analysis when you already have stored StepResults; use `rubric_grader` directly when not comparing to gold labels.
- **input** — `{"grader_kind": str, "examples": [{"item": Any, "gold_score": float}]}`.
- **value** — `{"agreement": float, "per_example": [{"predicted": float, "gold": float}], "bias": float}`.
- **uses** — one `ctx.step(grader_kind, ...)` per example, then a small Monty reduction.
- **stresses** — meta-evaluation: grading the grader. Fan-out is exactly `len(examples)`, so this is the smallest kind that gives a parent a real budget-sizing problem.

### `score_aggregator`

- **purpose** — Pure Monty reduction: aggregates `{score, weight}` rows by `policy` (`weighted_mean`, `median`, or `min`).
- **when to use** — Deterministic combine step after `rubric_grader` or other scorers without inline parent math.
- **similar kinds** — `rubric_grader` (produces scores via LLM); `calibration` (compare to gold); `monty_exec` (arbitrary reduction code).
- **prefer alternatives when** — Use `rubric_grader` when scores do not exist yet; use `monty_exec` for custom aggregation policies not listed here.
- **input** — `{"scores": [{"score": float, "weight": float}], "policy": "weighted_mean"|"median"|"min"}`.
- **value** — `{"aggregate": float, "n": int}`.
- **uses** — none (pure Monty).
- **stresses** — that some kinds genuinely need no `ctx.*` primitives at all. Pairs with `rubric_grader` so a parent doesn't have to write reduction code inline.

---

## Group O — Adversarial / red-team

### `attack_generator`

- **purpose** — LLM crafts adversarial input for a target kind using its catalog convention and a goal string.
- **when to use** — Red-team setup inside `adversarial_loop` or standalone fuzzing of kind conventions.
- **similar kinds** — `adversarial_loop` (orchestrates attacks); `failure_classifier` (diagnose results); `noop_fail` (deterministic failure).
- **prefer alternatives when** — Use `noop_fail` for deterministic host errors; use `adversarial_loop` when multiple attack rounds matter; use hand-crafted inputs for reproducible security cases.
- **input** — `{"target_kind": str, "target_input_template": dict, "attack_goal": str}` — e.g. `"make target return status:error"`.
- **value** — `{"crafted_input": Any, "rationale": str}`.
- **uses** — `ctx.llm`; reads `ctx.catalog[target_kind]` to ground the attack in the target's documented convention.
- **stresses** — `ctx.catalog` is load-bearing here; without it the attacker has no documentation to read.

### `adversarial_loop`

- **purpose** — Alternates `attack_generator` and `target_kind` up to `max_rounds`, stopping on first target `host_error` or success predicate.
- **when to use** — End-to-end red-team loops showing any kind can be both attacker parent and victim child.
- **similar kinds** — `attack_generator` (one crafted input); `refine_until` (benign iterate/judge); `cascade` (try kinds, not adaptive attacks).
- **prefer alternatives when** — Use `attack_generator` alone for one-shot inputs; use `refine_until` for quality iteration, not adversarial search; use manual pytest with fixed inputs for stable CI.
- **input** — `{"target_kind": str, "seed_input": Any, "max_rounds": int, "success_predicate": str}`.
- **value** — `{"rounds": int, "history": [{"input": Any, "target_result": StepResult, "successful": bool}], "winning_input": Any|null}`.
- **uses** — alternating `ctx.step(kind="attack_generator", ...)` and `ctx.step(target_kind, ...)`.
- **stresses** — confirms a kind can be both a parent and a target of attack on other kinds in the same run; no host-level distinction between "victim" and "attacker."

### `failure_classifier`

- **purpose** — LLM classifies a `StepResult` into failure categories (host_error vs convention vs semantic ok).
- **when to use** — Downstream triage when parents pass full envelopes without unwrapping; tests JSON round-trip of StepResult-shaped input.
- **similar kinds** — `classifier` (label arbitrary text); `judge` (pass/fail on candidate content); `regression_canary` (hash-based pass/fail).
- **prefer alternatives when** — Use `classifier` when input is not a StepResult; use deterministic checks in parents when rules are fixed; use `regression_canary` for golden determinism, not taxonomy.
- **input** — `{"step_result": StepResult}`.
- **value** — `{"category": "host_error"|"convention_violation"|"semantic_error"|"ok", "subcategory": str, "evidence": str}`.
- **uses** — `ctx.llm` (and possibly `ctx.catalog` to look up the expected value convention).
- **stresses** — a kind whose **input** is itself a `StepResult` envelope; tests that envelopes round-trip through JSON cleanly and that callers can pass them down without unwrapping.

### `regression_canary`

- **purpose** — Runs frozen `(frozen_kind, frozen_input)`, content-hashes the value, compares to `expected_value_hash`.
- **when to use** — Determinism regression (§7): same `(input, budget, seed, provider)` must yield the same hash.
- **similar kinds** — `catalog_self_test` (many kinds, outcome not hash); `constant` / `echo` (trivial determinism); `content_hash_memo` (memo keyed by input hash).
- **prefer alternatives when** — Use `catalog_self_test` for broad smoke tests; use pytest goldens for full value comparison, not just hash; use `content_hash_memo` for within-run dedup, not cross-run CI gates.
- **input** — `{"frozen_input": Any, "frozen_kind": str, "expected_value_hash": str}`.
- **value** — `{"passed": bool, "actual_hash": str, "result": StepResult}`.
- **uses** — `ctx.step(frozen_kind, frozen_input, ...)` then hashes its value.
- **stresses** — the determinism property (§7) directly: re-running the same fixture must hash-match, so this kind doubles as the contract test for "same `(input, budget, seed, provider)` → same value."

---

## Group P — Convention translation and content-hash caching

### `convention_adapter`

- **purpose** — LLM translates a `source_value` from one kind's convention into `target_input` for another kind, flagging lossiness.
- **when to use** — Composing pipelines where adjacent kinds disagree on JSON shapes (e.g. `program_writer` → `function_map_writer`).
- **similar kinds** — `chain_with_adapter` (first → adapt → second); `transformer` (Monty pre/post, same run); `monty_exec` (hand-written mapping).
- **prefer alternatives when** — Use `transformer` for deterministic field mapping; use `monty_exec` for simple transforms; use dedicated kinds when translation is stable and should not consume tokens each time.
- **input** — `{"source_kind": str, "target_kind": str, "source_value": Any}`.
- **value** — `{"target_input": Any, "lossy": bool, "notes": str}`.
- **uses** — `ctx.llm`, reading both `ctx.catalog[source_kind]` and `ctx.catalog[target_kind]`.
- **stresses** — kind A's value becomes kind B's input via an explicit translation step. Example: take `program_writer`'s `{status, program, notes}` and produce `function_map_writer`'s `{signatures: ...}`. This is what makes the catalog **composable** rather than a flat list of disconnected entries.

### `chain_with_adapter`

- **purpose** — Three-step linear composition: `first_kind`, then `convention_adapter`, then `second_kind` on the adapted input.
- **when to use** — Reference pattern for catalog-native composition without host glue code.
- **similar kinds** — `pipeline` (N stages, no adapter kind); `convention_adapter` (middle step only); `dynamic_dispatch` (single hop).
- **prefer alternatives when** — Use `pipeline` when conventions already align; use two manual `ctx.step` calls in a custom parent when adapter logic is trivial; use `meta_planner` when even the stage list should be LLM-generated.
- **input** — `{"first_kind": str, "first_input": Any, "second_kind": str}`.
- **value** — `{"first_result": StepResult, "adapted_input": Any, "second_result": StepResult}`.
- **uses** — `ctx.step(first_kind, ...)`, then `ctx.step(kind="convention_adapter", ...)`, then `ctx.step(second_kind, ...)`.
- **stresses** — three-step linear composition where the middle step is itself a kind. Demonstrates that adapters live in the catalog, not in host glue code.

### `content_hash_memo`

- **purpose** — Hashes `(inner_kind, inner_input)`; returns cached value from caller-supplied `memo` or runs one child step and updates memo in the value.
- **when to use** — Legal within-run memoization (§7): cache is explicit in input/output, not host-global state.
- **similar kinds** — `dedup_then_map` (dedupe a list fan-out); `retry_wrapper` (repeat calls intentionally); excluded `cached` (cross-run persistent cache).
- **prefer alternatives when** — Use `dedup_then_map` when many list items share hashes; omit memo when every call must be fresh; never use cross-run persistent caches in v1.
- **input** — `{"inner_kind": str, "inner_input": Any, "memo": {hash_str: Any}|null}`.
- **value** — `{"hash": str, "value": Any, "hit": bool, "memo": {hash_str: Any}}`.
- **uses** — Monty hashes `(inner_kind, inner_input)`; if the hash is in `memo`, returns the cached value; otherwise calls `ctx.step(inner_kind, inner_input, ...)` and adds to memo.
- **stresses** — the **legal** form of memoization under §7 constraint 5: the cache is part of `input` and `value`, so the parent carries it explicitly. No host-side state, no cross-run cache. A parent that wants memoization across iterations of a loop threads the `memo` through each call; a parent that doesn't, doesn't.

### `dedup_then_map`

- **purpose** — Content-hashes each item, runs `inner_kind` once per unique hash, returns map plus per-position hash index.
- **when to use** — Fan-out where many inputs collapse to few unique computations (safe dedup under determinism).
- **similar kinds** — `map_reduce` (one step per item, no dedup); `content_hash_memo` (single key memo threaded by parent); `repo_walker` (path-keyed fan-out).
- **prefer alternatives when** — Use `map_reduce` when every item is distinct; use `content_hash_memo` in loops where the parent threads memo dict; use `map_reduce` + `reduce_kind` when a combine step is needed.
- **input** — `{"items": [Any], "inner_kind": str}`.
- **value** — `{"results_by_hash": {hash_str: StepResult}, "items_to_hash": [str]}`.
- **uses** — hashes each item, calls `ctx.step(inner_kind, ...)` exactly once per unique hash, returns a map keyed by hash plus a parallel list mapping each input position to its hash.
- **stresses** — `map_reduce`'s sibling for the case where many inputs collapse to few unique computations; content-hash dedup is the only safe memoization in the deterministic model.

---

## Group Q — RLM iterative reasoning

### `rlm_loop`

- **purpose** — Iterative RLM agent: repeated LLM cycles emit structured actions (`answer`, `step`, `llm`, `think`, `fail`), executing via `ctx.step`/`ctx.llm` with trace and state in the value.
- **when to use** — Multi-iteration reasoning tasks that need inspectable traces, child delegation, and explicit partial/error/complete status (see `rlm-loop-kind.md`).
- **similar kinds** — `meta_planner` (one-shot plan then run); `refine_until` (fixed inner/judge alternation); `program_writer` (single generate-and-run); `conversation` (chat turns only).
- **prefer alternatives when** — Use `meta_planner` when one plan upfront suffices; use `refine_until` for simple candidate/judge loops; use `program_writer` for one-shot code generation; use `conversation` when no `step` actions are needed.
- **input** — `{"task": str, "context": dict, "max_iterations": int, "answer_schema": Any|null, "child_kind": str|null, "child_request": BudgetRequest, "system_hint": str}` — see `rlm-loop-kind.md` for the full schema and field semantics.
- **value** — `{"status": "complete"|"partial"|"error", "answer": Any|null, "iterations": int, "trace": [...], "state": {"task", "context", "vars", "trace"}, "notes": str}`.
- **charges** — tokens per iteration (one `ctx.llm` per cycle); steps/tokens per `step` action inside the loop.
- **uses** — `ctx.llm`, `ctx.step`, `ctx.catalog`, `ctx.budget`.
- **stresses** — structured iterative recursion with an inspectable trace; the RLM action protocol (`rlm-action-protocol.md`); multi-turn state carried in `value`, not host memory; composes with any child kind via `step` actions. Full specification: `rlm-loop-kind.md`.

---

## Group M — Explicitly excluded from v1 (documented to mark the boundary)

These kinds would be natural to write but are **disallowed** in v1 because they break determinism or sandboxing. They are listed here so future readers do not re-propose them under another name.

- **`shell_exec`** — runs a subprocess. Side-effecting, nondeterministic, can escape the budget. v2 candidate as a host-side gated primitive only.
- **`http_fetch`** — out-of-process I/O. Same reasoning; results vary by network state and time.
- **`filesystem_read_direct`** — bypasses `directory_input`. Allowing it makes determinism a caller responsibility, which the contract currently keeps as a host invariant.
- **`sleep`** / **`wall_clock`** — explicit nondeterminism.
- **`spawn_concurrent`** — concurrent siblings. §7 forbids; included here so it's not silently reintroduced under a different name.
- **`cached`** — memoization across runs. Memo is fine inside one step's input (pure function of input), but a persistent cache that mutates between runs would break the "operation entirely determined by `(input, budget, seed, provider)`" property.

If any of these become necessary, they require a contract change, not just a new catalog entry.
