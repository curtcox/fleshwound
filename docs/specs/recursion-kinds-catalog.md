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
- **value** — `{"chosen_kind": str, "result": StepResult}`.
- **charges** — one child step.
- **uses** — `ctx.step` with `kind=None` and `default_policy="random"`.
- **stresses** — §6.3 seed derivation. Two runs with the same `run_seed` and parent `budget_id` must pick the same child kind. Also stresses that `ctx.step()` reports back which kind was actually chosen (or that the parent can read it from somewhere — open: see issue C-2).

### `subset_pick`

- **input** — `{"inner_input": Any, "subset": [str]}`.
- **value** — `{"chosen_kind": str, "result": StepResult}`.
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

## Contract issues found

Writing this list surfaced these residual ambiguities. They are not blocking — most can be resolved by a one-line clarification in `recursion-contract.md` — but should be settled before implementation.

- **C-1. `ctx.step()` return on default-policy resolution.** Does the returned envelope include the kind that was actually chosen, so kinds like `random_pick` can report it without having to re-derive the seed? Recommendation: extend `StepResult` with an optional `resolved_kind: str` field, populated by the host when default-policy resolution ran. Pure cost: one extra field. Without it, `random_pick` and `subset_pick` cannot honestly fill in `chosen_kind`.

- **C-2. Where do executors find their own kind?** §6.0 says `ctx.kind` exposes it; that is new in this edit. Confirm. (`inherit_chain` needs it to build its trace.)

- **C-3. Sibling iteration order.** `map_reduce` and `ensemble` assume children allocated in for-loop order get child IDs `parent.1`, `parent.2`, … in that order. `budget-ledger.md` §3 says "child index order is based on allocation order" — confirm "allocation order" means "the order in which `allocate_child` is called on the ledger," not e.g. some completion order. Recommendation: one-line tighten in budget-ledger.md.

- **C-4. `host_error.code: "executor_error"`.** Added in this edit to distinguish Monty failures from non-Monty failures. Is the distinction useful, or should both be `monty_error`? Argument for keeping them separate: debugging — `monty_error` carries a Monty traceback, `executor_error` carries a host-Python traceback, and confusing them slows diagnosis. Argument against: callers don't care; one code means simpler retry logic.

- **C-5. Wall-clock / env nondeterminism.** §7 now says executors "must not rely on" these, but the host does not currently prevent it. Tighten to either (a) constrain Monty's external bindings so `datetime.now()` and `os.environ` are unbound, or (b) accept that determinism is a kind-author responsibility. Recommend (a) for v1; (b) is an audit hole.

- **C-6. `ctx.budget()` snapshot freshness.** When a child is mid-flight, what does the parent's `ctx.budget()` show — the parent's remaining **including** the child's reservation, or excluding it? Embedded mode currently shows excluding (the reservation has already debited the parent). Spawned would show the same after `allocate_child` writes through. Confirm and document.

- **C-7. Charging order on `ctx.llm()` failure.** `budget-ledger.md` §6 says tokens are charged "for whatever the provider reports, including on failure." But §4.1's `llm()` return shape has `usage` field always populated. If the provider returns `{status: "error", usage: {prompt_tokens: 0, ...}, ...}` is the charge zero? Recommend: yes, charge whatever `usage.total_tokens` reports, including zero. Document explicitly.

These eight issues collectively are the second pass over the contract. Resolving them and writing the matching test fixtures from the catalog above is the work that lets implementation begin without rework.
