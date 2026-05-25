# Larql Provider Integration Plan for Fleshwound

## 1. Goal

Use Larql as a rich model provider for Fleshwound. When Fleshwound uses a Larql model, Larql must be able to call back into Fleshwound as a function/tool. Those embedded or spawned Fleshwound calls must receive a child budget allocated by Larql and enforced by Fleshwound's shared budget ledger.

## 2. Non-goals

- Preserve current Fleshwound APIs.
- Preserve backward compatibility.
- Add full Python support to Fleshwound.
- Add concurrent execution.
- Add background execution.
- Support multiple simultaneous tool calls in one Larql generation round.

## 3. Architectural principles

1. Fleshwound owns orchestration.
2. Larql is a rich provider, not a plain `Callable[[str], str]`.
3. Budget accounting is explicit and ledger-backed.
4. Larql may request child budgets but cannot mint budget.
5. Fleshwound validates and allocates child budgets.
6. Embedded and spawned modes share the same JSON-compatible protocol.
7. Execution is single-threaded and deterministic.

## 4. Target execution loop

```text
Fleshwound run
  -> LarqlModelProvider
      -> sends prompt + tools + budget to Larql
      -> Larql returns text or tool call
      -> tool call may invoke fleshwound(...)
          -> embedded mode: same-process Runner
          -> spawned mode: child worker process
      -> provider returns final text to Monty llm(...)
```

## 5. Fleshwound file plan

Current relevant files:

```text
fleshwound/
  __init__.py
  runner.py
Recursive_step_prompt.md
pyproject.toml
```

Proposed additions:

```text
fleshwound/
  budget.py
  context.py
  provider.py
  tools.py
  serialization.py
  providers/
    __init__.py
    larql.py
  workers/
    __init__.py
    spawned_child.py

docs/specs/
  larql-provider-protocol.md
  larql-provider-integration-plan.md
  budget-ledger.md
  spawned-worker-protocol.md
```

## 6. Larql file plan

Likely additions:

```text
crates/larql-inference/src/
  budget.rs
  tools/
    mod.rs
    schema.rs
    protocol.rs
    runtime.rs
    fleshwound.rs

docs/integrations/
  fleshwound.md
```

Likely modifications:

```text
crates/larql-inference/src/lib.rs
crates/larql-cli/src/commands/primary/run_cmd.rs
crates/larql-server/src/http/*
crates/larql-server/src/routes/*
```

Exact server route files should be identified during implementation because the server module layout is more detailed than the high-level plan.

## 7. Fleshwound implementation phases

### Phase 1: Budget ledger

Add `fleshwound/budget.py`.

Implement:

- `BudgetLimit`
- `BudgetUsage`
- `BudgetSnapshot`
- `BudgetEvent`
- `BudgetLedger`

Required operations:

- `snapshot(budget_id)`
- `charge_tokens(budget_id, amount, reason)`
- `charge_step(budget_id, reason)`
- `charge_tool_call(budget_id, reason)`
- `allocate_child(parent_budget_id, requested, reason)`
- `close_child(child_budget_id)`

Acceptance criteria:

- child budget allocation is deterministic;
- over-budget requests are rejected;
- event ordering is stable;
- `budget()` can be rendered for Monty code.

### Phase 2: Run context

Add `fleshwound/context.py`.

Implement:

```python
@dataclass
class RunContext:
    ledger: BudgetLedger
    budget_id: str
    depth_remaining: int
    provider: ModelProvider
    tool_registry: ToolRegistry
    mode: Literal["embedded", "spawned"] | None = None
    metadata: dict = field(default_factory=dict)
```

Acceptance criteria:

- runner no longer passes budget and provider as loose parameters;
- child contexts are easy to create;
- spawned serialization uses the same data model.

### Phase 3: Provider abstraction

Add `fleshwound/provider.py`.

Implement:

- `ModelRequest`
- `ModelTextResult`
- `ToolSpec`
- `ToolCall`
- `ToolResult`
- `ModelProvider`
- `RichModelProvider`
- `CallableProvider` for tests

Acceptance criteria:

- `runner.py` no longer assumes `llm` is a plain callable;
- provider requests include budget ID, budget snapshot, tools, and max token information.

### Phase 4: Runner refactor

Modify `fleshwound/runner.py`.

Replace local budget dict mutation with ledger operations.

Host functions:

- `llm(prompt)` creates a `ModelRequest`, calls provider, charges reported usage (including on failure), and **always returns a dict**: `{status: "ok"|"error", text: str, usage: {prompt_tokens, completion_tokens, total_tokens}, error: {code, message}|None}`.
- `step(sub_input, request)` validates `sub_input` (`{task, context, output_schema}`) and `request` (a `BudgetRequest` dict with `tokens`/`steps`/`depth`/`tool_calls`), allocates the child budget from the parent's envelope, recursively invokes Runner, then refunds unused child budget to the parent — including on child failure. The embedded-vs-spawned execution choice is made by host policy, not by the step author; no `mode` parameter is exposed in the Monty surface.
- `ask_user(question)` is host-configured and may be absent. When present, the host sets `context["ask_user_available"] = True` for the step. When absent, the name is not bound in the Monty namespace.
- `budget()` returns a read-only snapshot with shape `{budget_id, tokens_remaining, steps_remaining, depth_remaining, tool_calls_remaining}`.

Child steps inherit the parent's `provider`; there is no per-step provider override in the Monty surface.

Public entry point:

```python
def run_step(
    task: str,
    budget: BudgetLimit,           # not BudgetRequest; root has no parent
    provider: ModelProvider,
    *,
    context: dict | None = None,
    output_schema: dict | None = None,
    ask_user: Callable[[str], str] | None = None,
) -> dict:
    ...
```

The returned dict matches the step output shape (3-arm `status`, with the `error` arm populated iff `status == "error"`).

Host safety nets (the Runner is responsible for both):

- Unhandled Python exceptions raised inside step code are caught and coerced into a `status: "error"`, `error.code: "monty_error"` result; a traceback summary is placed in `notes`. The exception does not propagate past the step boundary.
- A malformed final expression (not a dict, missing `status`, status not in the enum) is coerced into the same `monty_error` result, with `repr(value)` in `notes`.

Acceptance criteria:

- Monty-visible API is `llm`, `step`, `budget`, and conditionally `ask_user`;
- `llm(...)` always returns a dict and never raises across the host boundary;
- recursive `step(...)` cannot exceed budget;
- `step(...)` returns a 3-arm status dict (`complete` / `partial` / `error`); budget denial is observable to the step author as `status == "error"` with `error.code == "budget_denied"`;
- unused child budget is auto-refunded on **every** child close (complete, partial, or error) and emits a `refund_child` ledger event;
- unhandled exceptions and malformed final expressions become `monty_error` results, not host crashes;
- runner handles provider tool loops indirectly;
- `output_schema` validation is advisory: mismatches are logged, the step's return value is passed through unchanged.

### Phase 5: Tool registry and embedded Fleshwound tool

Add `fleshwound/tools.py`.

Implement:

- `ToolRegistry`
- `fleshwound` tool spec
- embedded execution handler
- budget validation and child allocation

Acceptance criteria:

- fake Larql tool call can invoke same-process Fleshwound;
- child result includes final budget snapshot;
- budget denial returns structured error.

### Phase 6: Spawned worker

Add `fleshwound/workers/spawned_child.py` and `fleshwound/serialization.py`.

Implement:

- one JSON request from stdin;
- one JSON response to stdout;
- logs only to stderr;
- process exits after the response.

Acceptance criteria:

- spawned mode returns the same result shape as embedded mode;
- malformed child output is detected;
- parent reconciles child budget usage.

### Phase 7: Larql provider

Add `fleshwound/providers/larql.py`.

Implement:

- HTTP transport;
- CLI transport fallback;
- request serialization;
- response parsing;
- tool-call interception;
- embedded/spawned tool execution;
- usage charging.

Acceptance criteria:

- `run_step(..., provider=LarqlProvider(...))` works;
- Larql can call Fleshwound during the generation loop;
- final text returns to Monty `llm(...)`.

## 8. Larql implementation phases

### Phase 1: Budget mirror types

Add `crates/larql-inference/src/budget.rs` or `crates/larql-core/src/budget.rs`.

Implement Rust mirrors of:

- `BudgetLimit`
- `BudgetUsage`
- `BudgetSnapshot`
- `BudgetRequest`

Larql must validate requests against snapshots but should not be authoritative for budget when Fleshwound owns the run.

### Phase 2: Tool protocol parser

Add `crates/larql-inference/src/tools/protocol.rs`.

Implement parser for:

- plain text response;
- JSON tool call response;
- invalid tool call response.

Rules:

- one tool call per generation round;
- unknown tools rejected;
- missing `budget_request` rejected;
- invalid JSON becomes parse error visible to caller.

### Phase 3: Tool runtime

Add `crates/larql-inference/src/tools/runtime.rs`.

Implement:

```rust
pub trait ToolExecutor {
    fn execute(&mut self, call: ToolCall, budget: BudgetSnapshot) -> Result<ToolResult>;
}
```

Add synchronous loop:

```text
for round in 0..max_tool_rounds:
    generate
    if text: return text
    if tool_call: execute synchronously and append result
return tool_loop_exceeded
```

### Phase 4: CLI support

Modify `crates/larql-cli/src/commands/primary/run_cmd.rs`.

Add flags:

```text
--tools
--fleshwound-tool
--fleshwound-mode embedded|spawned
--budget-tokens N
--budget-steps N
--budget-depth N
--budget-tool-calls N
```

For Larql-owned CLI runs, only spawned Fleshwound execution is required initially.

### Phase 5: Server support

Extend non-streaming chat/completion request handling first.

Add optional fields:

```json
{
  "tools": [],
  "tool_choice": "auto",
  "budget": {}
}
```

Defer streaming tool-call interleaving until non-streaming support is stable.

## 9. Recommended first executable slice

```text
Fleshwound run_step
  -> LarqlProvider.complete_with_tools
  -> Larql returns larql.tool_call:fleshwound
  -> embedded child Fleshwound run
  -> tool result appended
  -> Larql returns final text
  -> Monty executes final text
```

This validates the recursive loop before introducing process isolation or server-side complexity.

## 10. Testing plan

### Fleshwound tests

```text
tests/test_budget.py
tests/test_runner_budget.py
tests/test_provider_contract.py
tests/test_fleshwound_tool.py
tests/test_spawned_worker_contract.py
tests/test_larql_provider_contract.py
```

### Larql tests

```text
crates/larql-inference/src/tools/protocol.rs unit tests
crates/larql-inference/src/tools/runtime.rs unit tests
CLI integration smoke test for spawned Fleshwound worker
```

## 11. Main risks

1. Larql models may not reliably emit valid tool-call JSON.
2. Double accounting may occur if both sides try to own budget.
3. Recursive Larql -> Fleshwound -> Larql loops can grow quickly.
4. Spawned mode can hide protocol errors if logs mix with stdout.

Mitigations:

- strict JSON parser;
- one canonical budget ledger;
- depth and tool-call limits;
- logs only to stderr;
- explicit structured errors.
