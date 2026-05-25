# Fleshwound/Larql Provider Protocol

Protocol version: `fleshwound-larql/1`

## 1. Purpose

This specification defines communication between Fleshwound and Larql when Larql is used as a rich model provider for Fleshwound.

The protocol supports:

1. Fleshwound calling Larql for model generation.
2. Larql returning either final text or a structured tool call.
3. Larql calling back into Fleshwound as a budget-aware tool.
4. Embedded and spawned Fleshwound tool execution.
5. Shared deterministic budget accounting.

Fleshwound remains a Monty-subset execution system. Full Python support is not part of this protocol.

## 2. Participants

### Fleshwound

Fleshwound is the recursive orchestration runtime.

Responsibilities:

- own the authoritative budget ledger;
- execute Monty-subset step code;
- expose host functions to Monty: `llm`, `step`, `ask_user`, and `budget`;
- call Larql as a model provider;
- execute `fleshwound` tool calls requested by Larql;
- reconcile child budget usage.

### Larql

Larql is a rich model provider.

Responsibilities:

- accept generation requests from Fleshwound;
- receive budget snapshots and tool specs;
- generate either final text or a tool call;
- request child budget when calling Fleshwound;
- report token usage;
- never mint, extend, or silently clamp budget.

### Fleshwound tool

The `fleshwound` tool is the recursive callback exposed to Larql. It lets a Larql model delegate a subproblem back into Fleshwound under a child budget allocated by Fleshwound.

## 3. Transport modes

The protocol is transport-neutral. Two execution modes are required.

### Embedded mode

Embedded mode is used when Fleshwound owns the top-level process.

```text
Fleshwound process
  -> LarqlProvider
      -> Larql generation
          -> tool_call: fleshwound
              -> same-process Fleshwound runner
```

Properties:

- shared in-memory budget ledger;
- no child ledger serialization except for transcript/debug output;
- preferred mode for normal Fleshwound use;
- single-threaded synchronous execution.

### Spawned mode

Spawned mode is used when Larql or another host owns the top-level process, or when process isolation is desired.

```text
Larql process
  -> spawned Fleshwound worker
      -> JSON request over stdin
      -> JSON response over stdout
```

Properties:

- one request at a time;
- no concurrent execution;
- child receives a serialized budget allocation;
- parent reconciles returned usage;
- v1 should use one request per process.

## 4. Determinism requirements

1. No concurrent tool calls.
2. No parallel child steps.
3. One Larql tool call per generation round.
4. Tool-call responses are processed synchronously.
5. Budget event ordering is stable and sequential.
6. Budget IDs are deterministic path-like IDs: `root`, `root.1`, `root.1.1`.
7. Retrying is explicit. Hidden retries are forbidden.
8. Budget denial returns a structured error, not a silent clamp.

## 5. Shared budget model

### BudgetLimit

```json
{
  "tokens": 20000,
  "steps": 8,
  "depth": 3,
  "tool_calls": 4
}
```

Field meanings:

| Field | Meaning |
|---|---|
| `tokens` | Maximum model/token budget available to this scope. |
| `steps` | Maximum Fleshwound recursive steps available. |
| `depth` | Maximum recursive Fleshwound depth remaining. |
| `tool_calls` | Maximum Larql tool calls available. |

### BudgetUsage

```json
{
  "tokens": 1234,
  "steps": 1,
  "tool_calls": 1
}
```

### BudgetSnapshot

```json
{
  "budget_id": "root.1",
  "parent_budget_id": "root",
  "limit": {
    "tokens": 4000,
    "steps": 2,
    "depth": 1,
    "tool_calls": 1
  },
  "used": {
    "tokens": 800,
    "steps": 1,
    "tool_calls": 0
  },
  "remaining": {
    "tokens": 3200,
    "steps": 1,
    "depth": 1,
    "tool_calls": 1
  }
}
```

### BudgetRequest

Used by Larql when requesting a Fleshwound child call.

```json
{
  "tokens": 3000,
  "steps": 1,
  "depth": 1,
  "tool_calls": 1
}
```

Validation rules (must match `recursion-contract.md` §5.1):

1. `tokens <= parent.remaining.tokens` and `tokens >= 0`
2. `steps <= parent.remaining.steps` and `steps >= 1`
3. `tool_calls <= parent.remaining.tool_calls` and `tool_calls >= 0`
4. `depth <= parent.remaining.depth - 1` and `depth >= 1`
5. all values must be integers
6. all requested fields are required in v1

If validation fails, Fleshwound returns `budget_denied`.

## 6. Fleshwound to Larql generation request

```json
{
  "type": "larql.generate",
  "protocol_version": "fleshwound-larql/1",
  "request_id": "root.req.1",
  "model": "gemma3-4b-it-vindex",
  "prompt": "Write Monty-subset code for this Fleshwound step...",
  "budget": {
    "budget_id": "root",
    "parent_budget_id": null,
    "limit": {
      "tokens": 20000,
      "steps": 8,
      "depth": 3,
      "tool_calls": 4
    },
    "used": {
      "tokens": 0,
      "steps": 0,
      "tool_calls": 0
    },
    "remaining": {
      "tokens": 20000,
      "steps": 8,
      "depth": 3,
      "tool_calls": 4
    }
  },
  "tools": [
    {
      "name": "fleshwound",
      "description": "Run a recursive Fleshwound step under a child budget.",
      "input_schema": {
        "type": "object",
        "properties": {
          "input": {"description": "Opaque JSON value passed verbatim to the child step. Shape is defined by the selected catalog entry's convention."},
          "budget_request": {"type": "object"},
          "kind": {"type": "string", "description": "Optional catalog entry name. If omitted, the active default-resolution policy applies."}
        },
        "required": ["input", "budget_request"]
      }
    }
  ],
  "options": {
    "max_tokens": 2048,
    "max_tool_rounds": 4,
    "tool_choice": "auto"
  }
}
```

Required fields:

| Field | Required | Notes |
|---|---:|---|
| `type` | yes | Must be `larql.generate`. |
| `protocol_version` | yes | Must be `fleshwound-larql/1` for v1. |
| `request_id` | yes | Stable deterministic ID. |
| `model` | yes | Larql model/vindex identifier. |
| `prompt` | yes | Prompt text. |
| `budget` | yes | Current authoritative Fleshwound budget snapshot. |
| `tools` | yes | May be empty. |
| `options` | yes | Generation options. |

## 7. Larql to Fleshwound generation response

Larql may return either final text or a tool call.

### Text response

```json
{
  "type": "larql.text",
  "protocol_version": "fleshwound-larql/1",
  "request_id": "root.req.1",
  "text": "```python\n...\n```",
  "usage": {
    "prompt_tokens": 1200,
    "completion_tokens": 700,
    "total_tokens": 1900
  },
  "finish_reason": "stop"
}
```

Fleshwound charges `usage.total_tokens` to the active budget. The Monty-visible `llm()` host function repackages this into its always-dict return shape (`{status: "ok", text, usage, error: None}`). On provider failure, the host charges whatever usage was reported (typically prompt tokens only) and returns `{status: "error", text: "", usage, error: {code, message}}`.

### Tool-call response

```json
{
  "type": "larql.tool_call",
  "protocol_version": "fleshwound-larql/1",
  "request_id": "root.req.1",
  "tool_call_id": "root.req.1.tool.1",
  "name": "fleshwound",
  "arguments": {
    "input": {
      "task": "Write only the parser component.",
      "context": {
        "language": "rust",
        "interface": "fn parse(input: &str) -> Result<Ast, ParseError>"
      },
      "output_schema": {
        "type": "object",
        "required": ["status", "program", "notes"]
      }
    },
    "budget_request": {
      "tokens": 3000,
      "steps": 1,
      "depth": 1,
      "tool_calls": 1
    },
    "kind": "program_writer"
  },
  "usage": {
    "prompt_tokens": 1200,
    "completion_tokens": 180,
    "total_tokens": 1380
  }
}
```

Fleshwound must:

1. charge Larql response usage;
2. validate `budget_request`;
3. allocate a child budget;
4. execute the tool;
5. send a tool result back into the Larql conversation if more generation is needed.

## 8. Fleshwound tool arguments

```json
{
  "input": "<any JSON value>",
  "budget_request": {
    "tokens": "integer",
    "steps": "integer",
    "depth": "integer",
    "tool_calls": "integer"
  },
  "kind": "string|null"
}
```

`input` is opaque to Fleshwound's transport layer; its shape is dictated by the catalog entry named in `kind`. `budget_request` must be explicit. If `kind` is omitted or null, the host applies the active default-resolution policy (see `recursion-contract.md` §6.3); embedded-vs-spawned execution is a host policy decision, not a tool-call argument.

## 9. Fleshwound tool result

### Success

```json
{
  "type": "fleshwound.tool_result",
  "protocol_version": "fleshwound-larql/1",
  "tool_call_id": "root.req.1.tool.1",
  "status": "ok",
  "result": {
    "outcome": "ok",
    "value": {
      "status": "complete",
      "program": "fn parse(...) { ... }",
      "notes": "Implements recursive descent parser.",
      "error": null
    },
    "host_error": null
  },
  "budget": {
    "budget_id": "root.1",
    "parent_budget_id": "root",
    "limit": {
      "tokens": 3000,
      "steps": 1,
      "depth": 1,
      "tool_calls": 1
    },
    "used": {
      "tokens": 2100,
      "steps": 1,
      "tool_calls": 0
    },
    "remaining": {
      "tokens": 900,
      "steps": 0,
      "depth": 0,
      "tool_calls": 1
    }
  }
}
```

The `result` field is the host's wrapped step envelope (see `recursion-contract.md` §4):

```python
{
    "outcome": "ok" | "host_error",
    "value": Any,                                          # opaque; defined by the kind's convention
    "host_error": {"code": str, "message": str} | None,
}
```

The transport carries this verbatim. The outer envelope's `status` field (`"ok"` vs `"error"`) reflects the *tool-call dispatch* — whether the call was validly issued, the child allocated, and the response returned. The inner envelope's `outcome` reflects whether the *child step itself* ran to completion. Both can be populated independently:

| Outer `status` | Inner `outcome` | Meaning |
|---|---|---|
| `"ok"` | `"ok"` | Call dispatched, child completed. `value` is the child's value. |
| `"ok"` | `"host_error"` | Call dispatched, child could not complete. `host_error` carries the reason. |
| `"error"` | — | Call did not dispatch (validation, allocation, spawn failed). No inner envelope. |

### Budget denial

```json
{
  "type": "fleshwound.tool_result",
  "protocol_version": "fleshwound-larql/1",
  "tool_call_id": "root.req.1.tool.1",
  "status": "error",
  "error": {
    "code": "budget_denied",
    "message": "Requested child budget exceeds remaining parent budget.",
    "requested": {
      "tokens": 10000,
      "steps": 2,
      "depth": 2,
      "tool_calls": 2
    },
    "available": {
      "tokens": 3000,
      "steps": 1,
      "depth": 1,
      "tool_calls": 1
    }
  }
}
```

### Invalid tool call

```json
{
  "type": "fleshwound.tool_result",
  "protocol_version": "fleshwound-larql/1",
  "tool_call_id": "root.req.1.tool.1",
  "status": "error",
  "error": {
    "code": "invalid_tool_call",
    "message": "Missing required field: budget_request."
  }
}
```

## 10. Error codes

| Code | Meaning |
|---|---|
| `budget_denied` | Requested child budget exceeds remaining budget. |
| `budget_exhausted` | Budget was exhausted during execution. |
| `invalid_tool_call` | Tool call failed schema validation. |
| `unknown_tool` | Larql requested an unregistered tool. |
| `tool_loop_exceeded` | More tool rounds requested than allowed. |
| `spawn_failed` | Spawned Fleshwound worker could not start. |
| `spawn_protocol_error` | Spawned worker returned malformed output. |
| `model_error` | Larql generation failed. |
| `monty_error` | Generated Monty code failed to execute. |

## 11. Versioning

Protocol versions use this string format:

```text
fleshwound-larql/1
```

Breaking changes increment the integer suffix.

Non-breaking additions are allowed if:

1. old readers ignore unknown fields;
2. required fields are not removed;
3. existing field meanings do not change.

Every request and response must include `protocol_version`.
