# Fleshwound Spawned Worker Protocol

Protocol version: `fleshwound-larql/1`

> **Status: deferred.** v1 is embedded-only. This document describes the intended spawned-mode protocol but is not in force; the canonical contract is `recursion-contract.md`. Known issues that block turning spawned mode on are in [`spawned-mode-future.md`](spawned-mode-future.md).

## 1. Purpose

This document specifies the spawned-process communication protocol for running Fleshwound as a Larql-callable function/tool.

Spawned mode is required for cases where Larql owns the top-level process or process isolation is desired.

## 2. Invocation

```bash
python -m fleshwound.workers.spawned_child
```

## 3. Process rules

1. Worker reads exactly one JSON request from stdin.
2. Worker writes exactly one JSON response to stdout.
3. Worker writes logs only to stderr.
4. Worker exits after writing the response.
5. Worker never writes non-JSON data to stdout.
6. Worker rejects unknown `protocol_version`.
7. Worker processes no concurrent requests.

## 4. Request shape

```json
{
  "type": "fleshwound.spawned.run_step",
  "protocol_version": "fleshwound-larql/1",
  "request_id": "root.1.spawn.1",
  "input": {
    "task": "Write only the parser component.",
    "context": null,
    "output_schema": null
  },
  "kind": "program_writer",
  "default_policy": "same_as_parent",
  "seed": 0,
  "budget": {
    "budget_id": "root.1",
    "parent_budget_id": "root",
    "limit": {
      "tokens": 3000,
      "steps": 1,
      "depth": 1,
      "tool_calls": 1
    }
  },
  "provider": {
    "kind": "larql",
    "transport": "http",
    "endpoint": "http://127.0.0.1:8080",
    "model": "gemma3-4b-it-vindex"
  }
}
```

Required fields:

| Field | Required | Meaning |
|---|---:|---|
| `type` | yes | Must be `fleshwound.spawned.run_step`. |
| `protocol_version` | yes | Must be `fleshwound-larql/1`. |
| `request_id` | yes | Deterministic request ID. |
| `input` | yes | Opaque JSON value handed to the step. The host does not inspect it; the shape is the selected `kind`'s convention. |
| `kind` | yes | Catalog entry name. May be null only if `default_policy` can resolve without a parent. |
| `default_policy` | yes | Default-resolution policy for any `step()` calls inside this run that omit `kind=`. |
| `seed` | yes | Deterministic seed for any random default resolution. |
| `budget` | yes | Child budget allocation. |
| `provider` | yes | Provider configuration for the child. |

## 5. Provider shape

Larql HTTP provider:

```json
{
  "kind": "larql",
  "transport": "http",
  "endpoint": "http://127.0.0.1:8080",
  "model": "gemma3-4b-it-vindex"
}
```

Larql CLI provider:

```json
{
  "kind": "larql",
  "transport": "cli",
  "larql_bin": "larql",
  "model": "gemma3-4b-it-vindex"
}
```

## 6. Success response

```json
{
  "type": "fleshwound.spawned.result",
  "protocol_version": "fleshwound-larql/1",
  "request_id": "root.1.spawn.1",
  "status": "ok",
  "result": {
    "outcome": "ok",
    "value": {
      "status": "complete",
      "program": "...",
      "notes": "...",
      "error": null
    },
    "host_error": null
  },
  "budget": {
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
    },
    "events": []
  }
}
```

## 7. Error response

```json
{
  "type": "fleshwound.spawned.result",
  "protocol_version": "fleshwound-larql/1",
  "request_id": "root.1.spawn.1",
  "status": "error",
  "error": {
    "code": "monty_error",
    "message": "Generated Monty code failed to execute."
  },
  "budget": {
    "used": {
      "tokens": 800,
      "steps": 1,
      "tool_calls": 0
    },
    "remaining": {
      "tokens": 2200,
      "steps": 0,
      "depth": 0,
      "tool_calls": 1
    },
    "events": []
  }
}
```

## 8. Parent reconciliation

The parent process must:

1. parse stdout as JSON;
2. reject malformed response;
3. verify matching `request_id`;
4. verify matching `protocol_version`;
5. verify reported usage does not exceed child allocation;
6. close child budget;
7. refund unused budget if refund policy is enabled.

If the worker exits without valid JSON, parent returns:

```json
{
  "status": "error",
  "error": {
    "code": "spawn_protocol_error",
    "message": "Spawned worker did not return valid protocol JSON."
  }
}
```

## 9. Security and isolation notes

Spawned mode is process isolation, not a sandbox.

It does not by itself provide:

- filesystem isolation;
- network isolation;
- CPU limits;
- memory limits;
- OS-level sandboxing.

Those can be added later by invoking the worker inside a stricter runtime.

## 10. Determinism notes

For v1, spawn a fresh process for each request. A persistent worker can be added later, but only if it preserves:

- single request at a time;
- deterministic request order;
- deterministic budget events;
- no background work.
