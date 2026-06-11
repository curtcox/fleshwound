# Fleshwound Recursion Contract

Protocol version: `fleshwound-larql/1`

This document is the source of truth for the recursion contract between Fleshwound and any caller (in-process Monty step code, the Larql provider, spawned workers, or a user-facing entry point). Other documents in `docs/specs/` and prompt assets defer to this document.

## 1. Scope

The host guarantees three things and nothing more:

1. It runs Monty code in a sandbox with a fixed set of injected functions (§3).
2. It enforces the budget invariant (§5) across the entire recursion tree.
3. It returns whatever the step's Monty code produced as its final expression, wrapped in a uniform envelope (§4).

Everything else — the meaning of the input value, the shape of the step's value, how the step describes its work — is defined by the catalog entry (§6) the step runs under and by the caller's convention. The host does not interpret it.

## 2. Public entry point

```python
def run_step(
    input: Any,
    budget: BudgetLimit,
    provider: ModelProvider,
    *,
    kind: str | None = None,
    default_policy: DefaultPolicy = "same_as_parent",
    seed: int,
    ask_user: Callable[[str], str] | None = None,
) -> StepResult:
    ...
```

- `input` — any JSON-serializable value. The host does not inspect it.
- `budget` — root `BudgetLimit` (a 4-field dict; see §5).
- `provider` — model provider used by every step in the run that does not override it.
- `kind` — selects the root step's catalog entry. If omitted, the default-resolution policy is used; in that case the policy must be able to resolve without a parent (i.e. not `"same_as_parent"`).
- `default_policy` — policy applied whenever a step calls `step()` without `kind=`. See §6.3.
- `seed` — required. Used to deterministically derive per-step randomness (for random default policies).
- `ask_user` — human callback. If `None`, `ask_user` is not bound in the Monty namespace.

Returns a `StepResult` envelope (§4).

## 3. Host primitives

Every executor (§6) receives a `RunContext` exposing the same four primitives. For Monty-based executors, the host binds them as Monty external functions; non-Monty executors call them on `ctx` directly. They are:

- `llm(prompt: str) -> dict` — see §4.1.
- `step(input: Any, request: BudgetRequest, *, kind=None, default_policy=None, provider=None, ask_user=None) -> StepResult` — recursive call.
- `ask_user(question: str) -> str` — bound iff the parent provided one. Not charged against any budget dimension; may block on the human indefinitely.
- `budget() -> dict` — read-only snapshot: `{budget_id, tokens_remaining, steps_remaining, depth_remaining, tool_calls_remaining}`.
- `catalog -> Mapping[str, str]` — read-only mapping from kind name to its `convention` string (§6). Static for the run, no charging. Allows kinds like `dynamic_dispatch`, `kind_chooser`, and `catalog_self_test` to introspect available kinds without baking the list into a prompt.

These five primitives are the **only** side-effect surface available to an executor. Executors are pure functions of `(input, the values returned by these primitives)`. Kinds may not perform filesystem, network, subprocess, or wall-clock I/O directly; if such an effect is needed, it must enter through a future host primitive added to this list. The exclusion list in `recursion-kinds-catalog.md` (Group M) enumerates the natural-but-disallowed kinds.

`kind=` arguments to `ctx.step()` are runtime strings. There is no compile-time or literal restriction; a kind name computed by Monty code or returned by `ctx.llm()` is just as valid as a literal. The host resolves the string against `ctx.catalog` at the moment of allocation; misses produce `unknown_kind`.

None of these raise across the executor boundary. Every failure surface is a returned value (the always-dict shape of `llm()` in §4.1; the `{outcome, value, host_error}` envelope of `step()` in §4).

`step(...)` kwargs:

- `kind` selects the child's catalog entry. If omitted, the host applies the active `default_policy`.
- `default_policy`, `provider`, `ask_user` are inheritance overrides for the child's subtree. If omitted, the child inherits the parent's.

## 4. Return envelope

`step()` and `run_step()` always return:

```python
{
    "outcome": "ok" | "host_error",
    "value": Any,
    "host_error": {"code": str, "message": str} | None,
}
```

- `outcome == "ok"` — `value` is the step's final expression, returned verbatim. `host_error` is None. `value` must be JSON-serializable; the host validates this and substitutes `malformed_result` on failure.
- `outcome == "host_error"` — the host substituted the result because the step could not produce one. `value` is `None`. `host_error` carries the reason.

The host never raises across the step boundary. `step()` and `run_step()` always return an envelope; uncaught exceptions in executor code are caught and wrapped as `monty_error` (Monty-based) or `executor_error` (non-Monty).

v1 returns exactly one `value` per step. There is no streaming/incremental surface: a step is observable to its caller only as a single envelope on completion. Intermediate progress, if any, must be expressed through ledger events, not through partial values. Streaming output is out of v1 scope.

Host-error codes:

| Code | Triggered by |
|---|---|
| `budget_exhausted` | Host stopped the step mid-execution. |
| `budget_denied` | A child `step(...)` request was invalid against the parent envelope. |
| `monty_error` | Unhandled exception in the step's Monty code. The host catches and wraps. |
| `malformed_result` | Step's final expression was missing or coerced (e.g. not JSON-serializable for spawned mode). |
| `spawn_failed` | Spawned worker could not start. (Spawned mode is deferred — see `spawned-mode-future.md`.) |
| `spawn_protocol_error` | Spawned worker returned malformed JSON. (Spawned mode is deferred.) |
| `unknown_kind` | `kind=` named an entry not in the catalog. |
| `unresolvable_default` | Default policy could not produce a kind (e.g. `same_as_parent` at the root, or an empty `random_from_subset`). |
| `executor_error` | Unhandled exception in a non-Monty executor. Wrapped identically to `monty_error`. |

`budget_exhausted` applies to any of `tokens`, `steps`, or `tool_calls` running out mid-execution. Depth violations cannot occur mid-execution — depth is checked only at child-allocation time, where it surfaces as `budget_denied`.

**The host does not inspect or interpret `value`.** Any structure inside `value` (a `status` field, a `program` field, etc.) is a convention of the catalog entry and its caller — not part of this contract.

### 4.1 `llm()` return

```python
{
    "status": "ok" | "error",
    "text": str,
    "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
    "error": {"code": str, "message": str} | None,
}
```

The host charges `usage` to the active budget on every call, success or failure. `llm()` does not raise across the host boundary.

## 5. Budget invariant

```
For every step s allocated budget B(s),
  sum_consumed(s + transitive descendants of s) ≤ B(s)
in every dimension (tokens, steps, tool_calls).
```

`depth` is structural, not cumulative: `depth(child) ≤ depth(parent) − 1`.

### 5.1 Allocation

When a step calls `step(input, request, ...)`, the host validates against the parent's remaining envelope:

```
request.tokens     <= parent.remaining.tokens     ;  request.tokens     >= 0
request.steps      <= parent.remaining.steps      ;  request.steps      >= 1
request.tool_calls <= parent.remaining.tool_calls ;  request.tool_calls >= 0
request.depth      <= parent.remaining.depth − 1  ;  request.depth      >= 1
```

`tokens` and `tool_calls` may be requested as zero — that is how a parent honestly allocates a non-LLM child (e.g. `constant`, `echo`, `monty_exec`) without padding waste. `steps` and `depth` must be `>= 1`: a step needs to charge its own entry, and depth `0` would forbid the child from running at all.

If validation fails, `step()` returns `outcome: "host_error"` with `host_error.code == "budget_denied"`. Otherwise the host reserves the requested envelope from the parent, opens a child budget, and runs the child.

### 5.2 Refund

On every child close — `outcome: "ok"` or `outcome: "host_error"` — the host refunds whatever remains in the child envelope to the parent. The host emits `refund_child` first, then `close_child`; the ledger is replayable in this order. The invariant in §5 holds because the parent's reserved-but-unused budget returns to its remaining balance.

A denied request (`budget_denied`, `unknown_kind`, `unresolvable_default`) never allocates a child, so no `charge_step`, `refund_child`, or `close_child` events fire — only a `deny` event on the parent.

## 6. Catalog

Each catalog entry is a named **execution strategy**. The catalog is fixed (defined by the host). Kind names are flat strings (no path-like parameterization in v1); a kind that needs variation reads its own `input` and behaves accordingly. Each entry is:

```
{
  "name":       str,        # the value passed as `kind=`
  "executor":   Executor,   # host-side callable; signature in §6.0
  "convention": str,        # human-readable: what input it expects,
                            # what value it produces, what budget it charges
}
```

Selecting `kind="X"` means "run this step with entry X's executor and convention." The convention is part of the entry's published documentation; the host does not enforce it.

### 6.0 Executor contract

An executor is any host-side callable with signature:

```python
executor(input: Any, ctx: RunContext) -> Any   # returns the step's value
```

`RunContext` exposes the host primitives from §3 — `ctx.llm`, `ctx.step`, `ctx.ask_user` (or `None` when the parent did not provide one), `ctx.budget` — plus run configuration (`ctx.provider`, `ctx.seed`, `ctx.budget_id`, `ctx.kind`). These are available to **every** executor; the catalog does not gate access to them. Security relies entirely on the Monty interpreter (for code that an executor chooses to run via Monty) and on the budget invariant in §5.

Monty is one implementation choice for an executor body; it is not host-mandated:

- `program_writer` calls `ctx.llm(...)` for source, then runs it inside Monty with `ctx.{llm,step,ask_user,budget}` bound as Monty external functions, and returns the final expression.
- `monty_exec` runs `input["code"]` inside Monty with the same external bindings, and returns the final expression.
- `constant` simply returns `input["value"]` — no Monty involved.

The host wraps every executor invocation with:

1. `charge_step` on entry, after successful allocation, before the executor body runs.
2. Uncaught exceptions → `host_error{code: "monty_error"}` for executors that ran Monty, or `host_error{code: "executor_error"}` otherwise.
3. Returned value is checked for JSON-serializability; failure → `host_error{code: "malformed_result"}`.
4. Wrap into the `{outcome, value, host_error}` envelope (§4).

### 6.1 Example entries

- **`program_writer`** — LLM-driven. Convention: input is `{"task": str, "context": dict|None, "output_schema": dict|None}`; value is `{"status": "complete"|"partial"|"error", "program": str, "notes": str, "error": ... }`. Charges tokens and one `step`. Prompt asset: `fleshwound/kinds/program_writer_prompt.md`.
- **`monty_exec`** — non-LLM. Convention: input is `{"code": str}`; value is whatever the executed code's final expression evaluated to. Charges one `step` and no tokens.
- (the full catalog under consideration lives in [`recursion-kinds-catalog.md`](recursion-kinds-catalog.md), which doubles as the contract-stress fixture.)

### 6.2 Charging

Every entry charges one `step` on entry (host-enforced, executor cannot skip). Entries are free to charge `tokens` (via `ctx.llm()`), `tool_calls` (via provider tool loops inside `ctx.llm()`), or neither. The entry's `convention` field documents what it charges.

### 6.3 Default-resolution policy

When `step()` is called without `kind=`, the host resolves a kind from the active default policy:

| Policy | Meaning |
|---|---|
| `"same_as_parent"` | Use the calling step's kind. Always resolvable inside an executor (the caller always has a kind). |
| `"random"` | Pick uniformly at random from the entire catalog. |
| `{"random_from_subset": [names...]}` | Pick uniformly at random from the named subset, after deduplication. |

Edge cases for `random_from_subset`:

- Empty subset (after dedup) → `unresolvable_default`.
- Any name in the subset not in the catalog → `unknown_kind` (raised at resolution time, before allocation).

The constraint "must be able to resolve without a parent" applies only when resolving the **root step's own kind** (the `run_step(kind=None)` case in §2). `same_as_parent` fails there because the root step has no caller; it is fine as the default policy for the root step's children.

The active policy is inherited from the parent. A step may override it for its subtree via `default_policy=` on `step()`.

All random picks use a per-call seed derived as:

```python
import hashlib
def derive_seed(run_seed: int, budget_id: str) -> int:
    h = hashlib.sha256(f"{run_seed}|{budget_id}".encode()).digest()
    return int.from_bytes(h[:8], "big")
```

`budget_id` is the deterministic path-like ID of the **child** budget being allocated (e.g. `root.2.1`). The same `run_seed` and `input` therefore produce the same execution.

## 7. Determinism

Operation is fully determined by:

- `input`,
- root `budget`,
- root `kind` and `default_policy`,
- `seed`,
- `provider` (and any state it carries),
- `ask_user` (assumed deterministic or absent).

The host introduces no other variation. This is the "operation entirely determined by input + budget" property — with `provider` and `seed` understood as run configuration. The following are forbidden:

1. Hidden retries.
2. Concurrent execution (sibling children run sequentially; no parallel `ctx.step`).
3. Undeclared randomness.
4. **Hidden state across host-primitive calls.** An executor's behavior on call N must depend only on `input` and on the values it has received back from earlier `ctx.*` calls in the same step. The host carries no cross-call memory on behalf of the executor; concretely, a multi-turn conversation must round-trip its full history through `input`, not through any host-side cache.
5. **Hidden state across runs.** The same `(input, budget, seed, provider, kind, default_policy)` tuple produces the same execution every time. Memoization-across-runs is therefore disallowed in the host; safe in-step memoization (a pure function of `input`) is the only legal form. See `recursion-kinds-catalog.md` Group P for content-hash caching that respects this constraint.

Executors must not rely on wall-clock time, OS environment, or other ambient nondeterminism. The Monty language limits restrict imports but still expose `datetime`, `os`, and `asyncio`; executors that bind Monty externals should treat reads of those as "do not, for determinism's sake" — the host does not currently sandbox them further. See [`open-contract-issues.md`](open-contract-issues.md) (C-5).

## 8. Transport modes

v1 supports **embedded mode only** (single process, in-memory ledger). Spawned mode — running a Fleshwound step in a child process under a serialized budget — is described in `spawned-worker-protocol.md` but is not part of v1's guarantees. See [`spawned-mode-future.md`](spawned-mode-future.md) for the open issues that block enabling it.
