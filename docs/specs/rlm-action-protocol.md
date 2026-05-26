# RLM Action Protocol

The structured action protocol used by `rlm_loop` is:

```text
fleshwound-rlm-action/1
```

Models should return exactly one JSON object and no prose:

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "answer",
  "value": {"ok": true}
}
```

When `strict_protocol` is false, legacy action objects without `protocol` are
accepted. When it is true, missing protocol markers and prose outside raw JSON
are controlled validation or parse errors. Fenced JSON blocks are accepted.

## Actions

### `answer`

Finishes the loop successfully.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "answer",
  "value": {},
  "notes": ""
}
```

### `step`

Delegates a child call through `ctx.step(...)`.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "step",
  "kind": "constant",
  "input": {"value": 7},
  "request": {"tokens": 100, "steps": 2, "depth": 1, "tool_calls": 0},
  "assign": "x"
}
```

If `request` is omitted, `rlm_loop` derives a safe request from the root
`child_request` and current budget. Explicit over-budget requests are rejected
with a `validation_error`; they are not clamped.

### `llm`

Calls the model directly through `ctx.llm(...)`.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "llm",
  "prompt": "Summarize the current evidence.",
  "assign": "summary"
}
```

### `think`

Records a planning note without external work.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "think",
  "notes": "Classify before answering."
}
```

### `fail`

Stops the loop with controlled `status: "error"`.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "fail",
  "message": "Cannot solve within current context."
}
```

## Validation

The parser accepts pure JSON, fenced JSON, and the first valid action-shaped JSON
object in non-strict mode. Validation requires:

- `action` is one of `answer`, `step`, `llm`, `think`, or `fail`.
- `step.kind`, when present, is a string.
- `step.input` is JSON-serializable.
- `step.request`, when present, contains valid integer budget dimensions and
  does not exceed remaining budget.
- `llm.prompt` is a string.
- `assign`, when present, is a safe variable key.

Assignments write the observation result into `state["vars"][assign]`, allowing
later iterations to inspect prior child or LLM results through loop state.

