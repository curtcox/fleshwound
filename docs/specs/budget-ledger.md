# Fleshwound Budget Ledger Specification

Protocol version: `fleshwound-larql/1`

## 1. Purpose

The budget ledger is the authoritative accounting mechanism for Fleshwound runs, including Larql-backed model calls and Larql-requested Fleshwound tool calls.

The ledger exists so that embedded and spawned Fleshwound calls can share the same semantics:

- finite budget;
- deterministic child allocation;
- explicit accounting;
- structured denial when insufficient budget remains.

## 2. Budget dimensions

```json
{
  "tokens": 20000,
  "steps": 8,
  "depth": 3,
  "tool_calls": 4
}
```

| Dimension | Meaning |
|---|---|
| `tokens` | Model/token budget. Charged for Larql generation and other model calls. |
| `steps` | Fleshwound recursive step budget. Charged when a Fleshwound step is run. |
| `depth` | Recursive depth budget. Child Fleshwound calls must receive less depth than the parent. |
| `tool_calls` | Number of Larql tool calls available. Charged when Larql requests a tool. |

## 3. Budget IDs

Budget IDs must be deterministic.

Examples:

```text
root
root.1
root.2
root.2.1
```

Rules:

1. Root budget ID is `root` by default.
2. Child IDs are allocated by appending a 1-based child index.
3. Child index order is based on allocation order.
4. IDs must not use random UUIDs in normal deterministic execution.

## 4. Ledger events

Every mutation to the ledger creates a budget event.

```json
{
  "seq": 3,
  "budget_id": "root.1",
  "kind": "charge_tokens",
  "amount": {
    "tokens": 1200
  },
  "reason": "larql generation"
}
```

Required fields:

| Field | Meaning |
|---|---|
| `seq` | Monotonic sequence number starting at 1. |
| `budget_id` | Budget scope affected by the event. |
| `kind` | Event kind. |
| `amount` | Object containing changed dimensions. |
| `reason` | Human-readable reason. |

Event kinds:

| Kind | Meaning |
|---|---|
| `create_root` | Root budget created. |
| `allocate_child` | Parent budget reserved for a child. |
| `charge_tokens` | Tokens charged. |
| `charge_step` | Step charged. |
| `charge_tool_call` | Tool call charged. |
| `refund_child` | Unused child budget returned to parent. |
| `close_child` | Child budget completed. |
| `deny` | Budget request denied. |

## 5. Allocation semantics

When Larql requests a Fleshwound tool call, Fleshwound validates the requested child budget against the parent budget.

Validation (canonical wording in `recursion-contract.md` §5.1):

```text
request.tokens     <= parent.remaining.tokens     ;  request.tokens     >= 0
request.steps      <= parent.remaining.steps      ;  request.steps      >= 1
request.tool_calls <= parent.remaining.tool_calls ;  request.tool_calls >= 0
request.depth      <= parent.remaining.depth - 1  ;  request.depth      >= 1
```

If valid:

1. Parent budget reserves the requested amount.
2. Child budget is created.
3. Child execution runs under that budget.
4. Child usage is reconciled on close.
5. Unused child budget is refunded to the parent.

**Default: refund unused child budget.** A refund emits a `refund_child` event whose `amount` records the dimensions returned to the parent. This default is part of the recursion contract — step authors are told their unused requests come back — and may not be silently disabled.

Refund fires on **every** child close, regardless of the child's outcome:

- `status: "complete"` — refund whatever is left in the child envelope.
- `status: "partial"` — refund whatever is left.
- `status: "error"` (including `monty_error`, `budget_exhausted`, `model_error`) — refund whatever is left. The child does not "forfeit" its envelope by failing.

A child killed by `budget_exhausted` may report `used == limit` in one or more dimensions; in that case the refund amount for those dimensions is zero, which is correct and still emits the event.

## 6. Charging rules

### Step charge

A Fleshwound recursive step charges one `step` at start.

If no steps remain, the step is denied before model generation.

### Token charge

Larql generation charges tokens using reported usage:

```json
{
  "prompt_tokens": 1200,
  "completion_tokens": 700,
  "total_tokens": 1900
}
```

If exact usage is not available, the provider may use a deterministic estimate. The estimate must be recorded as an estimated charge in the event reason.

Tokens are charged for whatever the provider reports, **including on failure**. A failed `llm()` call (`model_error`, network error, malformed response) typically charges the prompt tokens but no completion tokens. The charge event's `reason` should distinguish success from failure (e.g. `"larql generation (model_error)"`) so the ledger is auditable.

### Tool-call charge

A Larql tool-call response charges one `tool_call` before executing the requested tool.

If no tool calls remain, Fleshwound returns `budget_denied` or `budget_exhausted`.

### Depth charge

Depth is not a mutable consumed counter in the same way as tokens. It is a structural limit.

Child depth must satisfy:

```text
child.depth <= parent.remaining.depth - 1
```

## 7. Snapshot shape

```json
{
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
```

## 8. Monty-visible budget

The host function `budget()` should expose a read-only simplified snapshot to Monty code.

Recommended shape:

```json
{
  "budget_id": "root.1",
  "tokens_remaining": 900,
  "steps_remaining": 0,
  "depth_remaining": 0,
  "tool_calls_remaining": 1
}
```

Monty code cannot mutate budget.

## 9. Budget denial

Budget denial is a structured result, not an exception for normal control flow.

```json
{
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

## 10. Implementation sketch

```python
@dataclass
class BudgetLimit:
    tokens: int
    steps: int
    depth: int
    tool_calls: int

@dataclass
class BudgetUsage:
    tokens: int = 0
    steps: int = 0
    tool_calls: int = 0

@dataclass
class BudgetSnapshot:
    budget_id: str
    parent_budget_id: str | None
    limit: BudgetLimit
    used: BudgetUsage
    remaining: BudgetLimit

@dataclass
class BudgetEvent:
    seq: int
    budget_id: str
    kind: str
    amount: dict
    reason: str

class BudgetLedger:
    def snapshot(self, budget_id: str) -> BudgetSnapshot: ...
    def charge_tokens(self, budget_id: str, amount: int, reason: str) -> None: ...
    def charge_step(self, budget_id: str, reason: str) -> None: ...
    def charge_tool_call(self, budget_id: str, reason: str) -> None: ...
    def allocate_child(self, parent_budget_id: str, requested: BudgetLimit, reason: str) -> str: ...
    def close_child(self, child_budget_id: str) -> BudgetSnapshot: ...
```

## 11. Determinism requirements

1. Event sequence numbers are stable.
2. Child budget IDs are stable.
3. Allocation order is observable and deterministic.
4. Hidden retries are forbidden.
5. Concurrency is forbidden.
6. Refund policy is explicit and deterministic.
