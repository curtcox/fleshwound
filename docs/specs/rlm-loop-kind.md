# RLM Loop Kind

`rlm_loop` is a cataloged recursive reasoning kind. It runs an iterative loop in
which a model chooses one structured action at a time, the kind executes that
action through normal host primitives, and the loop records an inspectable trace.

The kind is implemented as a normal catalog entry. It does not change the host
contract: child recursion still goes through `ctx.step(...)`, model calls still
go through `ctx.llm(...)`, and budget/depth enforcement remains with the host.

## Input

```json
{
  "task": "Solve the problem.",
  "context": {},
  "max_iterations": 8,
  "answer_schema": null,
  "child_kind": null,
  "child_request": {
    "tokens": 1000,
    "steps": 2,
    "depth": 1,
    "tool_calls": 0
  },
  "system_hint": ""
}
```

- `task` is the user-level task for the loop.
- `context` is JSON-serializable task context copied into loop state.
- `max_iterations` caps model/action cycles. Reaching it returns `partial`.
- `answer_schema` is a prompt hint only; the host does not enforce it.
- `child_kind` is the fallback kind for `step` actions without `kind`.
- `child_request` is the default child budget when an action omits `request`.
- `system_hint` is extra prompt guidance for the model.
- Actions must include `"protocol": "fleshwound-rlm-action/1"`; prose
  wrapped around raw JSON is rejected while fenced JSON is accepted.

## Output

```json
{
  "status": "complete",
  "answer": {},
  "iterations": 1,
  "trace": [],
  "state": {
    "task": "Solve the problem.",
    "context": {},
    "vars": {},
    "trace": []
  },
  "notes": ""
}
```

`status` is one of:

- `complete`: an `answer` action finished the loop.
- `partial`: the loop stopped at `max_iterations`, an LLM error, parse error,
  validation error, or a budget/depth limitation.
- `error`: a validated `fail` action explicitly stopped the loop.

Each trace row contains `iteration`, raw `model_text`, parsed `action`, and an
`observation`. Observations include `step_result`, `llm_result`, `thought`,
`parse_error`, `validation_error`, and `budget_limit`.

## Execution

For each iteration, `rlm_loop` builds a prompt containing:

- the current task and context,
- the current `vars` state,
- the trace so far,
- the available catalog,
- the remaining budget snapshot,
- the required action protocol.

The model response is parsed as an RLM action. Valid actions are executed through
`ctx.llm(...)` or `ctx.step(...)`; nothing bypasses host accounting. If an action
has `assign`, the resulting observation payload is stored under `state["vars"]`.

Child recursion is unavailable when depth remaining is at the floor. In that
case, a `step` action records a `budget_limit` observation instead of attempting
an invalid child allocation.

