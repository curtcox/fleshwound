# Fleshwound Recursion Contract

Protocol version: `fleshwound-larql/1`

This document is the source of truth for the recursion contract between Fleshwound and any caller (in-process Monty step code, the Larql provider, spawned workers, or a user-facing entry point). Other documents in `docs/specs/` and the example prompts in `examples/` defer to this document.

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

## 3. Injected functions

Inside a Monty step, the host binds:

- `llm(prompt: str) -> dict` — see §4.1.
- `step(input: Any, request: BudgetRequest, *, kind=None, default_policy=None, provider=None, ask_user=None) -> StepResult` — recursive call.
- `ask_user(question: str) -> str` — bound iff the parent provided one.
- `budget() -> dict` — read-only snapshot: `{budget_id, tokens_remaining, steps_remaining, depth_remaining, tool_calls_remaining}`.

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

- `outcome == "ok"` — `value` is the step's final expression, returned verbatim. `host_error` is None.
- `outcome == "host_error"` — the host substituted the result because the step could not produce one. `value` is `None`. `host_error` carries the reason.

Host-error codes:

| Code | Triggered by |
|---|---|
| `budget_exhausted` | Host stopped the step mid-execution. |
| `budget_denied` | A child `step(...)` request was invalid against the parent envelope. |
| `monty_error` | Unhandled exception in the step's Monty code. The host catches and wraps. |
| `malformed_result` | Step's final expression was missing or coerced (e.g. not JSON-serializable for spawned mode). |
| `spawn_failed` | Spawned worker could not start. |
| `spawn_protocol_error` | Spawned worker returned malformed JSON. |
| `unknown_kind` | `kind=` named an entry not in the catalog. |
| `unresolvable_default` | Default policy could not produce a kind (e.g. `same_as_parent` at the root). |

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
request.tokens     <= parent.remaining.tokens
request.steps      <= parent.remaining.steps
request.tool_calls <= parent.remaining.tool_calls
request.depth      <= parent.remaining.depth − 1
all values         > 0
```

If validation fails, `step()` returns `outcome: "host_error"` with `host_error.code == "budget_denied"`. Otherwise the host reserves the requested envelope from the parent, opens a child budget, and runs the child.

### 5.2 Refund

On every child close — `outcome: "ok"` or `outcome: "host_error"` — the host refunds whatever remains in the child envelope to the parent. Refunds emit a `refund_child` ledger event. The invariant in §5 holds because the parent's reserved-but-unused budget returns to its remaining balance.

## 6. Catalog

Each catalog entry is a named **execution strategy**. The catalog is fixed (defined by the host) but effectively infinite (entries may parameterize over input). Each entry is:

```
{
  "name":       str,        # the value passed as `kind=`
  "executor":   callable,   # host-side function that runs the step
  "convention": str,        # human-readable: what input it expects,
                            # what value it produces, what budget it charges
}
```

Selecting `kind="X"` means "run this step with entry X's executor and convention." The convention is part of the entry's published documentation; the host does not enforce it.

### 6.1 Example entries

- **`program_writer`** — LLM-driven. Convention: input is `{"task": str, "context": dict|None, "output_schema": dict|None}`; value is `{"status": "complete"|"partial"|"error", "program": str, "notes": str, "error": ... }`. Charges tokens and one `step`. Documented by `examples/recursive_step_prompt.md`.
- **`monty_exec`** — non-LLM. Convention: input is `{"code": str}`; value is whatever the executed code's final expression evaluated to. Charges one `step` and no tokens.
- (others — defined by the catalog author.)

### 6.2 Charging

Every entry charges one `step` on entry, drawn from the entry's own envelope. Entries are free to charge `tokens` (via `llm()`), `tool_calls` (via provider tool loops), or neither. The entry's `convention` field documents what it charges.

### 6.3 Default-resolution policy

When `step()` is called without `kind=`, the host resolves a kind from the active default policy:

| Policy | Meaning |
|---|---|
| `"same_as_parent"` | Use the parent's kind. Cannot be the active policy at the root step. |
| `"random"` | Pick uniformly at random from the entire catalog. |
| `{"random_from_subset": [names...]}` | Pick uniformly at random from the named subset. |

The active policy is inherited from the parent. A step may override it for its subtree via `default_policy=` on `step()`.

All random picks use seeds deterministically derived from `(run_seed, budget_id)`. The same `run_seed` and `input` therefore produce the same execution.

## 7. Determinism

Operation is fully determined by:

- `input`,
- root `budget`,
- root `kind` and `default_policy`,
- `seed`,
- `provider` (and any state it carries),
- `ask_user` (assumed deterministic or absent).

The host introduces no other variation. This is the "operation entirely determined by input + budget" property — with `provider` and `seed` understood as run configuration. Hidden retries, concurrent execution, and undeclared randomness are forbidden.
