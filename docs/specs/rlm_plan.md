# Fleshwound RLM Implementation Plan: Phases 1 and 2

## Current Status

Status as of the current implementation:

- [x] Phase 1 is implemented.
- [x] Phase 2 is implemented.
- [x] `rlm_loop` is registered as a catalog kind in `fleshwound/kinds/rlm_loop.py`.
- [x] The loop uses structured JSON actions as its primary protocol.
- [x] Direct answer, child step, direct LLM, think, fail, malformed-output, max-iteration, unknown-child-kind, and depth-floor paths are covered by tests.
- [x] Strict protocol mode exists and is tested.
- [x] RLM kind and action protocol docs exist in `docs/specs/rlm-loop-kind.md` and `docs/specs/rlm-action-protocol.md`.
- [x] The full test suite passes with the current implementation.

Remaining follow-up work:

- [x] RLM helpers and executor live in `fleshwound/kinds/rlm_loop.py`.
- [ ] Add an `include_model_text` input flag if traces become too token-heavy for production use.
- [ ] Consider warnings for unknown top-level fields in strict mode; the current implementation accepts them.
- [ ] Add more golden coverage for representative `rlm_loop` traces if future changes make trace stability important.

## Goal

Implement the RLM pattern inside `fleshwound` as a cataloged recursion kind, without changing the core host contract. Phase 1 adds a minimal iterative RLM loop. Phase 2 replaces fragile free-form code generation with a structured action protocol.

This plan assumes the existing `fleshwound` architecture:

- `run_step(...)` is the public recursive execution entry point.
- `ctx.step(...)` is the child-recursion primitive.
- `ctx.llm(...)` is the model-call primitive.
- `ctx.budget()` exposes remaining budget.
- `ctx.catalog` exposes available recursion kinds.
- catalog entries live under `fleshwound/kinds/` (one module per kind).
- tests live under `tests/kinds/`.

---

## Design Principles

1. **Do not alter the host contract unless absolutely necessary.**  
   The RLM behavior should be implemented as a normal catalog kind.

2. **Keep the host semantics simple.**  
   The host should continue to enforce budget, depth, provider use, and result envelopes. The RLM kind should own its own internal planning loop and value convention.

3. **Preserve deterministic budget behavior.**  
   Every recursive subcall must use explicit budget requests and must rely on `ctx.step(...)`.

4. **Return inspectable traces.**  
   RLM behavior is hard to debug without iteration traces. Even the minimal implementation should return enough trace data to explain what happened.

5. **Prefer structured protocols over free-form model output.**  
   Phase 1 may use generated Monty/code as a fast path. Phase 2 should move to explicit JSON actions.

---

# Phase 1: Minimal RLM Loop Kind

Status: **complete**.

## Objective

Add a catalog kind that behaves like a small RLM: it repeatedly asks the model what to do next, can call child steps, records observations, and returns a final answer or partial trace.

Recommended kind name:

```text
rlm_loop
```

Alternative names:

```text
recursive_reasoner
recursive_program_solver
rlm_reasoner
```

## Proposed Input Convention

```json
{
  "task": "string",
  "context": {},
  "max_iterations": 8,
  "answer_schema": null,
  "child_kind": null,
  "child_request": {
    "tokens": 10000,
    "steps": 8,
    "depth": 2,
    "tool_calls": 4
  },
  "system_hint": ""
}
```

### Field Semantics

| Field | Required | Meaning |
|---|---:|---|
| `task` | yes | User-level task for the RLM kind. |
| `context` | no | JSON-serializable context available to the loop. |
| `max_iterations` | no | Maximum model/action iterations before returning partial. |
| `answer_schema` | no | Optional schema-like hint for the final answer. |
| `child_kind` | no | Default kind to use when the loop delegates a subtask. |
| `child_request` | no | Default budget request for child calls. |
| `system_hint` | no | Additional caller-provided behavior hint. |

## Proposed Output Convention

```json
{
  "status": "complete",
  "answer": {},
  "iterations": 3,
  "trace": [
    {
      "iteration": 1,
      "model_text": "...",
      "action": {},
      "observation": {}
    }
  ],
  "notes": ""
}
```

### Status Values

| Status | Meaning |
|---|---|
| `complete` | The loop reached a final answer. |
| `partial` | The loop hit iteration or budget limits but has useful trace. |
| `error` | The loop failed in a controlled, JSON-serializable way. |

## Initial Implementation Shape

Add an executor:

```python
@register("rlm_loop", convention="task/context -> answer via iterative llm+step recursion")
def rlm_loop(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    ...
```

Recommended location:

```text
fleshwound/kinds/rlm_loop.py
```

or, if you want to keep shared helpers separate:

```text
fleshwound/kinds/rlm.py
```

If using a new module, ensure it is imported from:

```text
fleshwound/kinds/__init__.py
```

## Phase 1 Prompt Contract

The model should be instructed to return either:

1. A final answer.
2. A child-step request.
3. A direct LLM request.
4. A reflection/continue note.

For Phase 1, the model may emit a simple JSON object or a code block. Prefer JSON if practical.

Minimal Phase 1 action format:

```json
{
  "action": "answer",
  "value": {}
}
```

```json
{
  "action": "step",
  "kind": "prose_writer",
  "input": {},
  "request": {
    "tokens": 1000,
    "steps": 2,
    "depth": 1,
    "tool_calls": 0
  }
}
```

```json
{
  "action": "llm",
  "prompt": "..."
}
```

```json
{
  "action": "think",
  "notes": "..."
}
```

Even though this overlaps with Phase 2, using this simple JSON shape in Phase 1 will make Phase 2 much easier.

## Execution Loop

Pseudo-code:

```python
def rlm_loop(input, ctx):
    task = input.get("task", "")
    context = input.get("context")
    max_iterations = int(input.get("max_iterations", 8))
    trace = []

    for i in range(max_iterations):
        prompt = build_rlm_loop_prompt(task, context, trace, ctx)
        model_result = ctx.llm(prompt)

        if model_result["status"] == "error":
            return {
                "status": "partial",
                "answer": None,
                "iterations": i,
                "trace": trace,
                "notes": "llm error: " + model_result["error"]["message"],
            }

        action = parse_action(model_result["text"])

        observation = execute_action(action, input, ctx)

        trace.append({
            "iteration": i + 1,
            "model_text": model_result["text"],
            "action": action,
            "observation": observation,
        })

        if action.get("action") == "answer":
            return {
                "status": "complete",
                "answer": action.get("value"),
                "iterations": i + 1,
                "trace": trace,
                "notes": "",
            }

    return {
        "status": "partial",
        "answer": None,
        "iterations": max_iterations,
        "trace": trace,
        "notes": "max_iterations reached",
    }
```

## Helper Functions

Add private helpers near the executor:

```python
def _build_rlm_loop_prompt(task: str, context: Any, trace: list[dict[str, Any]], ctx: Any, input: dict[str, Any]) -> str:
    ...
```

```python
def _parse_json_action(text: str) -> dict[str, Any]:
    ...
```

```python
def _default_child_request(ctx: Any, input: dict[str, Any]) -> dict[str, int]:
    ...
```

```python
def _execute_rlm_action(action: dict[str, Any], root_input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    ...
```

## Budget Policy

Use explicit child budgets. Do not let the model request arbitrary unbounded budgets.

Recommended helper behavior:

```python
def _default_child_request(ctx, input):
    snap = ctx.budget()
    requested = dict(input.get("child_request") or {})
    return {
        "tokens": min(int(requested.get("tokens", snap["tokens_remaining"] // 2)), snap["tokens_remaining"]),
        "steps": max(1, min(int(requested.get("steps", snap["steps_remaining"] // 2)), snap["steps_remaining"])),
        "depth": max(1, min(int(requested.get("depth", snap["depth_remaining"] - 1)), snap["depth_remaining"] - 1)),
        "tool_calls": min(int(requested.get("tool_calls", snap["tool_calls_remaining"] // 2)), snap["tool_calls_remaining"]),
    }
```

Guard against `depth_remaining <= 1`; in that case the RLM kind should avoid `ctx.step(...)` and use `ctx.llm(...)` or return partial.

## Phase 1 Tests

Status: **complete**. Implemented in `tests/kinds/test_rlm_loop.py`.

Create:

```text
tests/kinds/test_rlm_loop.py
```

### Test 1: Completes with Direct Answer

Fake provider returns:

```json
{"action": "answer", "value": {"result": 42}}
```

Expected:

```python
result["outcome"] == "ok"
result["value"]["status"] == "complete"
result["value"]["answer"] == {"result": 42}
```

### Test 2: Delegates to Child Step

Fake provider first returns:

```json
{
  "action": "step",
  "kind": "constant",
  "input": {"value": "child result"}
}
```

Then returns:

```json
{"action": "answer", "value": "done"}
```

Expected:

- trace has at least two iterations.
- first observation contains a child `StepResult`.
- final status is `complete`.

### Test 3: Handles Unknown Kind

Fake provider returns a step action with an unknown kind.

Expected:

- RLM kind does not crash.
- trace records `host_error`.
- final result is either `partial` or completes after a later corrective action.

### Test 4: Respects Max Iterations

Fake provider repeatedly returns:

```json
{"action": "think", "notes": "continue"}
```

Expected:

```python
value["status"] == "partial"
value["notes"] == "max_iterations reached"
```

### Test 5: Handles Malformed Model Output

Fake provider returns non-JSON text.

Expected:

- no host exception.
- result is JSON-serializable.
- status is `partial` or `error`.
- trace includes parse error information.

### Test 6: Avoids Child Step at Depth Floor

Run with depth too low for child recursion.

Expected:

- no invalid child allocation crash.
- trace records a depth/budget limitation.
- result is partial or falls back to direct answer.

## Phase 1 Acceptance Criteria

Phase 1 is complete. Acceptance status:

- [x] `rlm_loop` is registered in the catalog.
- [x] `kind_lister` includes `rlm_loop`.
- [x] `run_step(..., kind="rlm_loop")` works with a fake provider.
- [x] Direct-answer, child-step, malformed-output, and max-iteration tests pass.
- [x] All returned values are JSON-serializable.
- [x] No host contract changes are required.

---

# Phase 2: Structured Action Protocol

Status: **complete**.

## Objective

Formalize the model-to-kind protocol so the RLM loop is no longer dependent on ad hoc parsing or free-form code. The model should emit a strict JSON action object each iteration.

This makes the RLM kind safer, easier to test, and easier to extend.

## Protocol Version

Use an explicit protocol marker:

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "answer",
  "value": {}
}
```

## Supported Actions

### 1. `answer`

Return final answer.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "answer",
  "value": {},
  "notes": ""
}
```

### 2. `step`

Call a child `fleshwound` kind.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "step",
  "kind": "classifier",
  "input": {
    "text": "...",
    "labels": ["a", "b"]
  },
  "request": {
    "tokens": 1000,
    "steps": 2,
    "depth": 1,
    "tool_calls": 0
  },
  "assign": "classification"
}
```

### 3. `llm`

Make a direct model call through `ctx.llm(...)`.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "llm",
  "prompt": "Summarize the current evidence.",
  "assign": "summary"
}
```

### 4. `think`

Record a reasoning/planning note without external action.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "think",
  "notes": "I need to classify before answering."
}
```

### 5. `fail`

Explicitly stop with a controlled error.

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "fail",
  "message": "Cannot solve within current context."
}
```

## State Model

Maintain an internal JSON-serializable state object:

```json
{
  "task": "string",
  "context": {},
  "vars": {},
  "trace": []
}
```

When an action has `assign`, store the observation under:

```text
state["vars"][assign]
```

Example after a child step:

```json
{
  "vars": {
    "classification": {
      "outcome": "ok",
      "value": {
        "label": "bug",
        "confidence": null,
        "rationale": "..."
      },
      "host_error": null
    }
  }
}
```

## Parser Requirements

Implement:

```python
def _parse_rlm_action(text: str) -> tuple[dict[str, Any] | None, str | None]:
    ...
```

Expected behavior:

| Input | Result |
|---|---|
| Pure JSON object | parse successfully |
| Markdown fenced JSON | parse successfully |
| Multiple JSON-looking blocks | use first valid action |
| Missing protocol | accept during Phase 2 with warning, or reject depending on strict mode |
| Unknown action | parse succeeds but executor returns controlled action error |
| Invalid JSON | parse fails with parse-error observation |

## Validation Requirements

Implement:

```python
def _validate_rlm_action(action: dict[str, Any], *, strict: bool = False) -> str | None:
    ...
```

Return `None` if valid, otherwise return an error string.

Minimum validation:

- action must be a dict.
- `action` must be one of `answer`, `step`, `llm`, `think`, `fail`.
- `step.kind`, if present, must be a string.
- `step.input` must be JSON-serializable.
- `step.request`, if present, must not exceed current available budget.
- `llm.prompt` must be a string.
- `assign`, if present, must be a safe variable key.

## Prompt Changes

The Phase 2 prompt should be strict:

```text
You are controlling a Fleshwound RLM loop.

Return exactly one JSON object and no prose.

The JSON object must match protocol:
  "protocol": "fleshwound-rlm-action/1"

Allowed actions:
  answer, step, llm, think, fail

Available catalog:
  ...

Current state:
  ...

Budget:
  ...

Task:
  ...
```

Include examples in the prompt, but keep them short.

## Execution Changes

Refactor Phase 1 loop:

```python
text = ctx.llm(prompt)["text"]
action, parse_error = _parse_rlm_action(text)

if parse_error:
    observation = {"type": "parse_error", "message": parse_error}
else:
    validation_error = _validate_rlm_action(action)
    if validation_error:
        observation = {"type": "validation_error", "message": validation_error}
    else:
        observation = _execute_rlm_action(action, root_input, ctx, state)
```

Only `answer` exits successfully.

`fail` exits with:

```json
{
  "status": "error",
  "answer": null,
  "notes": "..."
}
```

## Strict Mode

Add input field:

```json
{
  "strict_protocol": true
}
```

When `strict_protocol` is true:

- missing protocol is invalid.
- extra top-level prose is invalid unless a valid fenced JSON block is found.
- unknown fields may either be rejected or recorded as warnings.

Recommended default:

```text
strict_protocol = false
```

until tests and prompts stabilize.

## Phase 2 Tests

Status: **complete**. Implemented in `tests/kinds/test_rlm_loop_protocol.py`.

Add or extend:

```text
tests/kinds/test_rlm_loop_protocol.py
```

### Test 1: Parses Pure JSON Action

Input text:

```json
{"protocol":"fleshwound-rlm-action/1","action":"answer","value":"ok"}
```

Expected action is parsed.

### Test 2: Parses Fenced JSON

Input text:

````markdown
```json
{"protocol":"fleshwound-rlm-action/1","action":"answer","value":"ok"}
```
````

Expected action is parsed.

### Test 3: Rejects Unknown Action

Input action:

```json
{"protocol":"fleshwound-rlm-action/1","action":"delete_everything"}
```

Expected controlled validation error.

### Test 4: Assigns Step Result to Vars

First action:

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "step",
  "kind": "constant",
  "input": {"value": 7},
  "assign": "x"
}
```

Second action:

```json
{
  "protocol": "fleshwound-rlm-action/1",
  "action": "answer",
  "value": {"done": true}
}
```

Expected:

- state vars include `x`.
- trace records the child `StepResult`.

### Test 5: Strict Mode Rejects Missing Protocol

Input:

```json
{"action":"answer","value":"ok"}
```

Expected:

- accepted when `strict_protocol` is false.
- rejected when `strict_protocol` is true.

### Test 6: Budget Request Is Clamped or Rejected

Model requests too much budget.

Expected:

- deterministic behavior.
- either clamp with warning or reject with validation error.
- no host crash.

Recommended policy: reject explicit over-budget requests; use defaults only when request is absent.

## Phase 2 Acceptance Criteria

Phase 2 is complete. Acceptance status:

- [x] `rlm_loop` uses structured JSON actions as its primary control protocol.
- [x] Protocol parsing and validation helpers are unit-tested.
- [x] Invalid model output produces traceable controlled errors.
- [x] Child-step observations can be assigned into loop state.
- [x] Strict mode is available.
- [x] Existing Phase 1 tests still pass.
- [x] No host contract changes are required.

---

# Suggested File Changes

Status: **complete**, with optional follow-ups noted below.

## Add or Modify

```text
fleshwound/kinds/rlm_loop.py
```

or:

```text
fleshwound/kinds/rlm.py
fleshwound/kinds/__init__.py
```

## Add Tests

Status: **complete**.

```text
tests/kinds/test_rlm_loop.py
tests/kinds/test_rlm_loop_protocol.py
```

## Optional Documentation

Status: **complete**.

```text
docs/specs/rlm-loop-kind.md
docs/specs/rlm-action-protocol.md
```

## Optional Golden Tests

Status: **partially complete**. Existing catalog/golden coverage includes `rlm_loop`; add more trace-specific goldens only if trace stability becomes a product requirement.

```text
tests/_goldens/kind_lister/test_rlm_loop_registered.json
```

---

# Implementation Order

Completed:

- [x] Add `rlm_loop` executor with a minimal loop.
- [x] Add fake-provider tests for direct answer and max iterations.
- [x] Add child-step action support.
- [x] Add trace output.
- [x] Add malformed-output handling.
- [x] Add protocol parser helper.
- [x] Add protocol validator helper.
- [x] Add `assign` / `vars` state model.
- [x] Add strict protocol mode.
- [x] Document the kind and action protocol.

Remaining:

- [x] `rlm_loop` lives in a dedicated module (`fleshwound/kinds/rlm_loop.py`).
- [ ] Optional: add `include_model_text` to suppress raw model text in traces.
- [ ] Optional: add warning or rejection behavior for unknown top-level fields in strict mode.

---

# Open Decisions

## Decision 1: Should Phase 1 use Monty code or JSON actions?

Recommendation: use JSON actions immediately.  
Reason: it avoids fragile arbitrary-code parsing and makes Phase 2 mostly a hardening/refactor step.

## Decision 2: Should over-budget child requests be clamped or rejected?

Recommendation: reject explicit over-budget requests, but provide safe defaults when no request is supplied.  
Reason: clamping can hide model mistakes and make traces harder to reason about.

## Decision 3: Should `rlm_loop` live in its own module?

Recommendation: yes. `rlm_loop` and its protocol helpers now live in
`fleshwound/kinds/rlm_loop.py`; other kinds each have their own module under
`fleshwound/kinds/`.

## Decision 4: Should the trace include full model text?

Recommendation: yes for tests and early development, but add an input flag later:

```json
{
  "include_model_text": false
}
```

to reduce token-heavy outputs in production.

---

# Final Target Shape

After Phases 1 and 2, a caller should be able to run:

```python
from fleshwound.runner import run_step
from fleshwound.provider import CallableProvider

provider = CallableProvider(lambda prompt: '{"protocol":"fleshwound-rlm-action/1","action":"answer","value":{"ok":true}}')

result = run_step(
    {
        "task": "Solve the problem.",
        "context": {"x": 1},
        "max_iterations": 4,
        "strict_protocol": True,
    },
    {"tokens": 10000, "steps": 16, "depth": 4, "tool_calls": 4},
    provider,
    kind="rlm_loop",
    seed=0,
)
```

Expected result:

```json
{
  "outcome": "ok",
  "value": {
    "status": "complete",
    "answer": {
      "ok": true
    },
    "iterations": 1,
    "trace": [...],
    "notes": ""
  },
  "host_error": null
}
```
