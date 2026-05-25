# Fleshwound Recursion Kinds Catalog

> This catalog has two jobs. First, it is the reference list of catalog entries that the host ships (or could ship). Second, it is the **contract-stress fixture** for `recursion-contract.md`: each entry calls out the contract clauses it exercises, and the act of enumerating them is how we discover gaps. Issues surfaced while writing this list are collected in §"Contract issues found" at the bottom.
>
> Kinds are grouped by what they stress, not by likely deployment usefulness. Some are degenerate on purpose.

## Conventions

For each kind:

- **input** — JSON shape the executor expects.
- **value** — JSON shape it returns inside the `{outcome, value, host_error}` envelope.
- **charges** — what the executor draws from its envelope, beyond the host's auto `charge_step`.
- **uses** — which `ctx.*` primitives the executor invokes.
- **stresses** — which `recursion-contract.md` clauses this entry is the test case for.

---

## Group A — Degenerate (zero or near-zero work)

### `constant`

- **input** — `{"value": Any}` (must be JSON-serializable).
- **value** — `input["value"]`, returned verbatim.
- **charges** — nothing (only the host's auto step charge).
- **uses** — none.
- **stresses** — §4 verbatim pass-through; §5.1 zero-token/zero-tool_call requests (Q1); §6.2 "charge step on entry, executor may not need anything else."

### `echo`

- **input** — `Any`.
- **value** — `input`, returned verbatim.
- **charges** — nothing.
- **uses** — none.
- **stresses** — §6.0 — an executor that does no work at all; confirms the host wrapper still emits `charge_step` and a well-formed envelope. Identical to `constant` except for input convention; included to test that the **convention** is a documentation concern, not enforced.

### `noop_fail`

- **input** — any (ignored).
- **value** — never reached.
- **charges** — n/a.
- **uses** — none; deliberately raises.
- **stresses** — §4 host safety net: uncaught Python exception in a non-Monty executor → `host_error{code: "executor_error"}`. Companion `noop_fail_monty` raises inside Monty → `monty_error`. Both must round-trip without crashing the host.

---

## Group B — Non-recursive leaves (single tool, no children)

### `prose_writer`

- **input** — `{"task": str, "context": dict|None}`.
- **value** — `{"text": str, "notes": str}`.
- **charges** — tokens (one `ctx.llm` call).
- **uses** — `ctx.llm`.
- **stresses** — §4.1 `llm()` always-dict return (success and error paths); §3 charging usage to the active budget including on failure.

### `classifier`

- **input** — `{"text": str, "labels": [str]}`.
- **value** — `{"label": str, "confidence": float|None, "rationale": str}`.
- **charges** — tokens.
- **uses** — `ctx.llm`.
- **stresses** — the kind that **post-processes** the LLM response to coerce it to a fixed shape — i.e. the kind decides how strict to be about its own value convention, the host does not (§6).

### `monty_exec`

- **input** — `{"code": str}`.
- **value** — whatever the final expression of `code` evaluates to (must be JSON-serializable).
- **charges** — nothing automatic; if the code calls `ctx.llm` or `ctx.step` it charges accordingly.
- **uses** — Monty interpreter with full `ctx.*` bound as externals.
- **stresses** — §6.0 — Monty is an executor's implementation choice, not a host requirement. Also stresses §4 `malformed_result` when the final expression is non-serializable.

### `ask_user_only`

- **input** — `{"question": str}`.
- **value** — `{"answer": str}` on success; `{"answer": null, "notes": "ask_user unavailable"}` when the parent did not bind one.
- **charges** — nothing.
- **uses** — `ctx.ask_user`.
- **stresses** — §3 explicit "`ask_user` is not charged"; the gating behavior when `ctx.ask_user is None`.

---

## Group C — Recursive coordinators (use `ctx.step`)

### `program_writer`

- Canonical entry; full spec in `Recursive_step_prompt.md`.
- **stresses** — almost everything: §5 budget partition; §5.2 refund-on-every-close; §4 host safety nets; the value convention vs. host outcome distinction (`status` vs. `outcome`).

### `map_reduce`

- **input** — `{"items": [Any], "map_kind": str, "reduce_kind": str|null}`.
- **value** — `{"mapped": [Any], "reduced": Any|null, "errors": [int]}`.
- **charges** — N child step allocations (sequential); optionally one more for reduce.
- **uses** — `ctx.step` once per item, then once for reduce.
- **stresses** — sequential-only execution (§7 no concurrency); per-child `kind=` override on `step()`; how a parent recovers when individual children come back as `host_error` without aborting the whole map.

### `retry_wrapper`

- **input** — `{"inner_input": Any, "inner_kind": str, "max_attempts": int}`.
- **value** — `{"attempts": int, "result": StepResult}` (the inner envelope is exposed verbatim).
- **charges** — up to `max_attempts` child step allocations; the parent must size each request to leave reserve.
- **uses** — `ctx.step` in a loop, branching on returned `outcome` / `host_error.code`.
- **stresses** — §5.2 refund correctness — a `budget_denied` or `monty_error` child must return its envelope to the parent so a retry has budget to spend; without correct refunds this kind is unusable.

### `ensemble`

- **input** — `{"inner_input": Any, "inner_kind": str, "n": int, "aggregator_prompt": str}`.
- **value** — `{"chosen": Any, "candidates": [Any]}`.
- **charges** — `n` step calls (sequential) plus one `ctx.llm` to aggregate.
- **uses** — `ctx.step` × n, then `ctx.llm`.
- **stresses** — deterministic ordering of sibling child IDs (§3 of `budget-ledger.md` — 1-based by allocation order); each sibling's seed differs by `budget_id`.

### `judge`

- **input** — `{"candidate": Any, "criteria": str}`.
- **value** — `{"verdict": "pass"|"fail", "rationale": str}`.
- **charges** — tokens.
- **uses** — `ctx.llm`.
- **stresses** — composes with `ensemble`/`retry_wrapper`; this entry exists to confirm value pass-through chains cleanly. (Not recursive itself.)

### `clarify_then_delegate`

- **input** — `{"task": str, "child_kind": str}`.
- **value** — `{"clarification_q": str|null, "clarification_a": str|null, "result": StepResult}`.
- **charges** — optionally one ask_user; one child step.
- **uses** — `ctx.ask_user` (conditionally), `ctx.step`.
- **stresses** — `ask_user`'s availability gating threaded through to an explicit field on the value; demonstrates that step authors, not the host, decide how to surface "I had to assume X."

---

## Group D — Default-policy stressors

### `random_pick`

- **input** — `{"inner_input": Any}`.
- **value** — `{"result": StepResult}`.
- **charges** — one child step.
- **uses** — `ctx.step` with `kind=None` and `default_policy="random"`.
- **stresses** — §6.3 seed derivation. Two runs with the same `run_seed` and parent `budget_id` must pick the same child kind. (Which kind was picked is recorded on the `allocate_child` ledger event; the envelope does not surface it.)

### `subset_pick`

- **input** — `{"inner_input": Any, "subset": [str]}`.
- **value** — `{"result": StepResult}`.
- **uses** — `ctx.step` with `default_policy={"random_from_subset": subset}`.
- **stresses** — §6.3 edge cases: empty subset → `unresolvable_default`; unknown name → `unknown_kind`; dedup of repeated names.

### `inherit_chain`

- **input** — `{"task": str, "depth": int}`.
- **value** — `{"trace": [str]}` (kinds visited in order).
- **uses** — `ctx.step` with no `kind=`, relying on `same_as_parent`.
- **stresses** — §6.3 corrected `same_as_parent` semantics (always resolvable inside an executor); §5 depth decrement-on-allocate; depth bottoming out as `budget_denied`.

---

## Group E — Failure-mode injectors (for testing the host)

### `always_host_error`

- **input** — `{"code": str}` (one of the §4 host-error codes).
- **value** — never reached.
- **uses** — none; the executor immediately raises an exception that the host would convert to that code, **or** returns a malformed value, **or** issues a budget_request that will be denied.
- **stresses** — every `host_error.code`. One instance per code, exercised as a fixture.

### `always_partial`

- **input** — `{}`.
- **value** — `{"status": "partial", "program": "", "notes": "deliberate partial for tests"}`.
- **stresses** — the `program_writer` convention's `status: "partial"` path — parents that wrap this kind must accept partial and not interpret it as `host_error`.

### `budget_hog`

- **input** — `{"target": "tokens"|"steps"|"tool_calls"}`.
- **uses** — burns the targeted dimension to zero, then attempts one more call → must observe `host_error{code: "budget_exhausted"}` on the next `ctx.llm` / `ctx.step` call.
- **stresses** — §4 `budget_exhausted` surfaces as a value, not an exception; mid-execution stopping at host-primitive boundaries (the only place the host can interrupt without sandboxing the executor body).

### `infinite_descent`

- **input** — `{}`.
- **uses** — recursively `ctx.step({}, request={steps: parent.steps - 1, depth: parent.depth - 1, tokens: 0, tool_calls: 0})` until depth hits 1.
- **stresses** — depth termination produces `budget_denied` (not `budget_exhausted`); confirms that `depth >= 1` floor (§5.1) is what halts the chain, not steps.

---

## Group F — Provider / override

### `provider_swap`

- **input** — `{"inner_input": Any, "inner_kind": str, "inner_provider": ProviderConfig}`.
- **uses** — `ctx.step(..., provider=new_provider)`.
- **stresses** — §3 `provider=` override is per-subtree, not per-call; the child's subsequent grandchildren inherit the new provider unless they override again.

---

---

## Group G — Dynamic dispatch (kind chosen at runtime)

### `dynamic_dispatch`

- **input** — `{"chooser": "literal"|"llm", "literal_kind": str|null, "task_for_chooser": str|null, "inner_input": Any}`.
- **value** — `{"chosen_kind": str, "result": StepResult}` — `chosen_kind` is the string this kind itself computed and passed to `ctx.step`; it knows it because it produced it, not because the host reported it.
- **uses** — optionally `ctx.llm` to pick a kind name (Monty assembles a prompt listing `ctx.catalog`), then `ctx.step(inner_input, request, kind=chosen_kind)`.
- **stresses** — that `kind=` accepts a runtime-computed string (no compile-time restriction); host's `unknown_kind` path when the chooser hallucinates a name; need for `ctx.catalog` (see C-10).

### `meta_planner`

- **input** — `{"task": str}`.
- **value** — `{"plan": [{"kind": str, "input": Any}], "results": [StepResult]}`.
- **uses** — one `ctx.llm` to produce a JSON plan, then a sequential loop of `ctx.step` per plan item.
- **stresses** — kinds-as-data: the catalog is materially exposed to the LLM and the model decides decomposition shape, not just content.

### `cascade`

- **input** — `{"inner_input": Any, "kinds": [str], "stop_predicate": str}`.
- **value** — `{"chosen_kind": str|null, "result": StepResult, "tried": [str]}`.
- **uses** — `ctx.step` for each kind in `kinds` in order, stopping when the predicate (a small Monty expression over the returned value) is satisfied.
- **stresses** — refund correctness: each failed attempt must refund into the parent envelope so the next attempt has budget.

### `cond_dispatch`

- **input** — `{"branches": [{"when": str, "kind": str}], "default_kind": str|null, "inner_input": Any}`.
- **value** — `{"chosen_kind": str, "result": StepResult}`.
- **uses** — evaluates each `when` (Monty predicate over `inner_input`) and dispatches; falls through to `default_kind`.
- **stresses** — pure-Monty dispatch without an LLM round; useful as a deterministic baseline for `meta_planner`.

---

## Group H — Structured-data shapes (the user's "function map" family)

### `function_map_writer`

- **input** — `{"signatures": {name: {"signature": str, "docstring": str}}, "context": dict|None}`.
- **value** — `{"functions": {name: {"source": str, "notes": str}}, "missing": [str]}`.
- **uses** — typically one `ctx.step(kind="program_writer")` per function for medium-large maps; for small maps a single `ctx.llm`.
- **stresses** — fan-out where the count of children is data-dependent; aggregation back into a map keyed by the same names; convention that the result's keys must be a subset of the input's keys (kind-enforced, not host-enforced).

### `function_map_editor`

- **input** — `{"current": {name: {"source": str}}, "edits": [{"name": str, "instruction": str}]}`.
- **value** — `{"updated": {name: {"source": str}}, "removed": [str], "added": [str]}`.
- **stresses** — in-place transform shape: same data type in and out; `removed` and `added` keys make the diff explicit so callers don't have to diff themselves.

### `schema_designer`

- **input** — `{"domain": str, "examples": [Any]|null}`.
- **value** — `{"schema": dict, "rationale": str}` — `schema` is a JSON Schema document.
- **uses** — `ctx.llm`.

### `ast_transform`

- **input** — `{"ast": dict, "transform": str}` — `ast` is a JSON-encoded AST in any convention; `transform` is prose.
- **value** — `{"ast": dict, "changes": [str]}`.
- **stresses** — value being a recursive nested structure that round-trips JSON; confirms there is no hidden depth limit on `value` (other than JSON's own).

### `diff_writer`

- **input** — `{"file": str, "content": str, "change": str}`.
- **value** — `{"diff": str, "format": "unified"}`.

### `patch_set_writer`

- **input** — `{"files": {path: str}, "task": str}`.
- **value** — `{"patches": [{"path": str, "diff": str}]}`.
- **stresses** — companion to `directory_input`; produces a structure that a caller can mechanically apply without re-prompting the model.

---

## Group I — Filesystem-backed I/O (without granting executors FS access)

> v1 stance: kinds **never** touch the filesystem. The caller materializes input from disk into a JSON blob and writes outputs back. This keeps determinism and sandboxing tight; the alternative (a `ctx.fs` primitive) is C-8 below.

### `directory_input`

- **input** — `{"tree": {path: {"content": str, "mode": str}}, "task": str}` — a virtual tree, keyed by path relative to a notional root.
- **value** — defined by the task; this kind is a thin wrapper that delegates to e.g. `program_writer` after assembling a prose `context` from the tree.
- **stresses** — large inputs (a repo subtree may be megabytes of JSON); tests that the contract has no implicit size limit but also surfaces that `value` size will hit the provider's token limit long before the host's JSON limit.

### `directory_writer`

- **input** — `{"task": str, "shape": "tree"|"flat"}`.
- **value** — `{"tree": {path: {"content": str, "mode": str}}, "notes": str}`.
- **stresses** — symmetric to `directory_input`; combined, the pair lets the caller (not the kind) own all FS state.

### `repo_walker`

- **input** — `{"tree": {path: ...}, "per_file_kind": str, "predicate": str}`.
- **value** — `{"per_file": {path: StepResult}}`.
- **uses** — one `ctx.step` per matching path.
- **stresses** — large fan-out plus per-child budget sizing decisions; this is where parents will most often hit `budget_denied` because they evenly divided budget over too many files.

### `patch_applier_proxy`

- **input** — `{"patches": [...]}`.
- **value** — `{"applied": [str], "rejected": [{"path": str, "reason": str}]}`.
- **stresses** — this is a **pure-data** kind: it simulates application but doesn't touch disk. Pairs with a caller-side real applier. The point: even FS-mutating intent is modelable inside the contract by emitting structured outputs.

---

## Group J — Iterative / multi-turn

### `refine_until`

- **input** — `{"inner_input": Any, "inner_kind": str, "judge_kind": str, "max_rounds": int, "judge_pass_predicate": str}`.
- **value** — `{"rounds": int, "history": [{"candidate": Any, "verdict": Any}], "final": Any}`.
- **uses** — alternating `ctx.step(inner_kind, ...)` and `ctx.step(judge_kind, ...)`.
- **stresses** — composition of two kinds in a loop; budget shrinkage round-over-round (parents must size the loop's total envelope).

### `conversation`

- **input** — `{"system": str, "turns": [{"role": str, "content": str}]}`.
- **value** — `{"reply": str, "turns": [...]}` — the turns appended with the new exchange.
- **uses** — `ctx.llm` once.
- **stresses** — that there is **no hidden state** between calls: the entire conversation history must be carried in `input`. The contract's determinism property depends on this; this kind exists partly to make the invariant explicit.

### `tournament`

- **input** — `{"candidates": [Any], "judge_kind": str}`.
- **value** — `{"winner": Any, "bracket": [...]}`.
- **uses** — log₂(N) rounds of pairwise `ctx.step(judge_kind, ...)`.
- **stresses** — N children sequential; deterministic bracket ordering tied to `budget_id` numbering.

---

## Group K — Composition

### `pipeline`

- **input** — `{"stages": [{"kind": str, "transform_input": str|null}], "initial": Any}`.
- **value** — `{"stages": [StepResult], "final": Any}`.
- **uses** — sequential `ctx.step` with each stage's value feeding the next (optionally massaged by a Monty `transform_input` snippet).

### `transformer`

- **input** — `{"preprocess": str, "inner_kind": str, "postprocess": str, "inner_input_template": Any}`.
- **value** — postprocessed value of the inner step.
- **stresses** — wrappers around existing kinds without needing to register a new entry per variant.

### `precondition_gate`

- **input** — `{"predicate": str, "inner_kind": str, "inner_input": Any}`.
- **value** — either the inner result or `{"gated": true, "reason": str}`.
- **uses** — Monty evaluates `predicate` against `inner_input`; if false, no `ctx.step` is made.

---

## Group L — Catalog-aware / introspective

### `kind_lister`

- **input** — `{}`.
- **value** — `{"kinds": [{"name": str, "convention": str}]}`.
- **uses** — reads `ctx.catalog`.
- **stresses** — C-10 below: `ctx.catalog` must be exposed for this to work. The kind is the smoking gun for the missing primitive.

### `kind_chooser`

- **input** — `{"task": str}`.
- **value** — `{"chosen_kind": str, "rationale": str}`.
- **uses** — `ctx.llm` with `ctx.catalog` rendered into the prompt.

### `catalog_self_test`

- **input** — `{"kinds_to_exercise": [str]|null}`.
- **value** — `{"results": [{"kind": str, "outcome": str, "host_error": ...}]}`.
- **uses** — one `ctx.step` per kind, with each kind's smallest viable input.
- **stresses** — every host-error code (paired with `always_host_error` fixtures from Group E).

---

---

## Group N — Scoring and grading

### `rubric_grader`

- **input** — `{"candidate": Any, "rubric": [{"criterion": str, "weight": float, "scale": "0-1"|"0-5"|"pass-fail"}]}`.
- **value** — `{"scores": [{"criterion": str, "score": float, "rationale": str}], "weighted_total": float, "notes": str}`.
- **uses** — `ctx.llm` per criterion (or batched into one call for small rubrics).
- **stresses** — composes upstream of `tournament`, `refine_until`, and `ensemble`; demonstrates that `judge` was a binary special case of this.

### `pairwise_preference`

- **input** — `{"a": Any, "b": Any, "criterion": str}`.
- **value** — `{"winner": "a"|"b"|"tie", "rationale": str, "confidence": float}`.
- **uses** — `ctx.llm`.
- **stresses** — the unit operation under `tournament`; isolating it from the loop lets the bracket reason about ties.

### `calibration`

- **input** — `{"grader_kind": str, "examples": [{"item": Any, "gold_score": float}]}`.
- **value** — `{"agreement": float, "per_example": [{"predicted": float, "gold": float}], "bias": float}`.
- **uses** — one `ctx.step(grader_kind, ...)` per example, then a small Monty reduction.
- **stresses** — meta-evaluation: grading the grader. Fan-out is exactly `len(examples)`, so this is the smallest kind that gives a parent a real budget-sizing problem.

### `score_aggregator`

- **input** — `{"scores": [{"score": float, "weight": float}], "policy": "weighted_mean"|"median"|"min"}`.
- **value** — `{"aggregate": float, "n": int}`.
- **uses** — none (pure Monty).
- **stresses** — that some kinds genuinely need no `ctx.*` primitives at all. Pairs with `rubric_grader` so a parent doesn't have to write reduction code inline.

---

## Group O — Adversarial / red-team

### `attack_generator`

- **input** — `{"target_kind": str, "target_input_template": dict, "attack_goal": str}` — e.g. `"make target return status:error"`.
- **value** — `{"crafted_input": Any, "rationale": str}`.
- **uses** — `ctx.llm`; reads `ctx.catalog[target_kind]` to ground the attack in the target's documented convention.
- **stresses** — `ctx.catalog` is load-bearing here; without it the attacker has no documentation to read.

### `adversarial_loop`

- **input** — `{"target_kind": str, "seed_input": Any, "max_rounds": int, "success_predicate": str}`.
- **value** — `{"rounds": int, "history": [{"input": Any, "target_result": StepResult, "successful": bool}], "winning_input": Any|null}`.
- **uses** — alternating `ctx.step(kind="attack_generator", ...)` and `ctx.step(target_kind, ...)`.
- **stresses** — confirms a kind can be both a parent and a target of attack on other kinds in the same run; no host-level distinction between "victim" and "attacker."

### `failure_classifier`

- **input** — `{"step_result": StepResult}`.
- **value** — `{"category": "host_error"|"convention_violation"|"semantic_error"|"ok", "subcategory": str, "evidence": str}`.
- **uses** — `ctx.llm` (and possibly `ctx.catalog` to look up the expected value convention).
- **stresses** — a kind whose **input** is itself a `StepResult` envelope; tests that envelopes round-trip through JSON cleanly and that callers can pass them down without unwrapping.

### `regression_canary`

- **input** — `{"frozen_input": Any, "frozen_kind": str, "expected_value_hash": str}`.
- **value** — `{"passed": bool, "actual_hash": str, "result": StepResult}`.
- **uses** — `ctx.step(frozen_kind, frozen_input, ...)` then hashes its value.
- **stresses** — the determinism property (§7) directly: re-running the same fixture must hash-match, so this kind doubles as the contract test for "same `(input, budget, seed, provider)` → same value."

---

## Group P — Convention translation and content-hash caching

### `convention_adapter`

- **input** — `{"source_kind": str, "target_kind": str, "source_value": Any}`.
- **value** — `{"target_input": Any, "lossy": bool, "notes": str}`.
- **uses** — `ctx.llm`, reading both `ctx.catalog[source_kind]` and `ctx.catalog[target_kind]`.
- **stresses** — kind A's value becomes kind B's input via an explicit translation step. Example: take `program_writer`'s `{status, program, notes}` and produce `function_map_writer`'s `{signatures: ...}`. This is what makes the catalog **composable** rather than a flat list of disconnected entries.

### `chain_with_adapter`

- **input** — `{"first_kind": str, "first_input": Any, "second_kind": str}`.
- **value** — `{"first_result": StepResult, "adapted_input": Any, "second_result": StepResult}`.
- **uses** — `ctx.step(first_kind, ...)`, then `ctx.step(kind="convention_adapter", ...)`, then `ctx.step(second_kind, ...)`.
- **stresses** — three-step linear composition where the middle step is itself a kind. Demonstrates that adapters live in the catalog, not in host glue code.

### `content_hash_memo`

- **input** — `{"inner_kind": str, "inner_input": Any, "memo": {hash_str: Any}|null}`.
- **value** — `{"hash": str, "value": Any, "hit": bool, "memo": {hash_str: Any}}`.
- **uses** — Monty hashes `(inner_kind, inner_input)`; if the hash is in `memo`, returns the cached value; otherwise calls `ctx.step(inner_kind, inner_input, ...)` and adds to memo.
- **stresses** — the **legal** form of memoization under §7 constraint 5: the cache is part of `input` and `value`, so the parent carries it explicitly. No host-side state, no cross-run cache. A parent that wants memoization across iterations of a loop threads the `memo` through each call; a parent that doesn't, doesn't.

### `dedup_then_map`

- **input** — `{"items": [Any], "inner_kind": str}`.
- **value** — `{"results_by_hash": {hash_str: StepResult}, "items_to_hash": [str]}`.
- **uses** — hashes each item, calls `ctx.step(inner_kind, ...)` exactly once per unique hash, returns a map keyed by hash plus a parallel list mapping each input position to its hash.
- **stresses** — `map_reduce`'s sibling for the case where many inputs collapse to few unique computations; content-hash dedup is the only safe memoization in the deterministic model.

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

## Contract issues found

Writing this list surfaced these residual ambiguities. They are not blocking — most can be resolved by a one-line clarification in `recursion-contract.md` — but should be settled before implementation.

- **C-1. ~~`ctx.step()` return on default-policy resolution.~~** *(Resolved — rejected.)* Originally proposed adding `resolved_kind` to `StepResult` so kinds like `random_pick` could honestly fill in `chosen_kind`. On review: a caller that cares about the kind specifies it; a caller that did not specify has no use for the answer in its control flow. The only real consumer is post-hoc log analysis, which belongs on the ledger, not the envelope. Resolution: record `resolved_kind` on the `allocate_child` ledger event; do **not** add it to `StepResult`. As a consequence, `random_pick`, `subset_pick`, and `dynamic_dispatch`'s `chosen_kind` field is dropped from their value conventions — those kinds return only `result: StepResult`. Log readers can join against the ledger via `budget_id`.

- **C-2. Where do executors find their own kind?** §6.0 says `ctx.kind` exposes it; that is new in this edit. Confirm. (`inherit_chain` needs it to build its trace.)

- **C-3. Sibling iteration order.** `map_reduce` and `ensemble` assume children allocated in for-loop order get child IDs `parent.1`, `parent.2`, … in that order. `budget-ledger.md` §3 says "child index order is based on allocation order" — confirm "allocation order" means "the order in which `allocate_child` is called on the ledger," not e.g. some completion order. Recommendation: one-line tighten in budget-ledger.md.

- **C-4. `host_error.code: "executor_error"`.** Added in this edit to distinguish Monty failures from non-Monty failures. Is the distinction useful, or should both be `monty_error`? Argument for keeping them separate: debugging — `monty_error` carries a Monty traceback, `executor_error` carries a host-Python traceback, and confusing them slows diagnosis. Argument against: callers don't care; one code means simpler retry logic.

- **C-5. Wall-clock / env nondeterminism.** §7 now says executors "must not rely on" these, but the host does not currently prevent it. Tighten to either (a) constrain Monty's external bindings so `datetime.now()` and `os.environ` are unbound, or (b) accept that determinism is a kind-author responsibility. Recommend (a) for v1; (b) is an audit hole.

- **C-6. `ctx.budget()` snapshot freshness.** When a child is mid-flight, what does the parent's `ctx.budget()` show — the parent's remaining **including** the child's reservation, or excluding it? Embedded mode currently shows excluding (the reservation has already debited the parent). Spawned would show the same after `allocate_child` writes through. Confirm and document.

- **C-7. Charging order on `ctx.llm()` failure.** `budget-ledger.md` §6 says tokens are charged "for whatever the provider reports, including on failure." But §4.1's `llm()` return shape has `usage` field always populated. If the provider returns `{status: "error", usage: {prompt_tokens: 0, ...}, ...}` is the charge zero? Recommend: yes, charge whatever `usage.total_tokens` reports, including zero. Document explicitly.

- **C-8. Side effects and the executor surface.** The catalog's filesystem family (Group I) and the exclusion list (Group M) together expose that the contract has no explicit stance on side effects. v1 default is "executors are pure functions of `(input, ctx-primitive returns)`"; the four `ctx.*` primitives are the only ways out. Recommendation: add one sentence to `recursion-contract.md` §3 saying exactly that, and reference Group M's reasoning. Without it, the next kind author may assume `import requests` is fair game.

- **C-9. `ctx.catalog` introspection.** Several kinds (`dynamic_dispatch`, `meta_planner`, `cascade`, `cond_dispatch`, `kind_lister`, `kind_chooser`, `catalog_self_test`) need to read the available kind names and conventions at runtime. The contract currently does not expose them. Recommendation: add `ctx.catalog: Mapping[str, str]` (name → convention string) as a fifth primitive. Read-only, no charging, no nondeterminism (it's static for the run).

- **C-10. Runtime-computed `kind=`.** `dynamic_dispatch` and `meta_planner` pass a string computed at runtime as `kind=`. Per Q4 this is allowed (kind names are flat strings, behavior comes from input). Worth one line in §6 confirming there is no compile-time / literal restriction.

- **C-11. No hidden state across `ctx.llm` / `ctx.step` calls.** `conversation` is the kind that makes this load-bearing — the entire turn history lives in `input`, not in the host. Recommendation: §7 already implies this but should state it as a numbered constraint, since it directly contradicts how most "chat" libraries work and will be a surprise.

- **C-12. Streaming / incremental output.** Several patterns (`refine_until`, `tournament`, long `conversation`) would benefit from emitting intermediate progress before the final `value`. v1 has no surface for it (one `value` per step). Explicitly out of scope — note in §4 as "v1 returns exactly one value per step; intermediate progress, if any, is logged via the ledger, not returned to the caller."

These twelve issues collectively are the second pass over the contract. C-1 was rejected and recorded as a ledger-event field; C-2 through C-12 are reflected in `recursion-contract.md` and `budget-ledger.md`. No open contract items remain. Resolving them and writing the matching test fixtures from the catalog above is the work that lets implementation begin without rework.
