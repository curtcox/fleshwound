# Spawned Mode — Future Issues

> v1 of Fleshwound is **embedded-only**. This document collects the known design and implementation issues that must be resolved before spawned mode (running a Fleshwound step in a child process under a serialized budget) is enabled. The intended wire protocol is sketched in [`spawned-worker-protocol.md`](spawned-worker-protocol.md); this document is its companion punch list.

Spawned mode was originally motivated by two use cases:

1. **Process isolation** — limit blast radius of a misbehaving Monty step.
2. **Larql-owned top process** — Larql's CLI/server wants to invoke Fleshwound as a leaf tool without embedding Python.

Neither is required for the v1 milestone (Fleshwound owns the process; Larql is a provider, not a parent host). When either becomes load-bearing, work through the issues below.

## 1. Value semantics drift

The contract guarantees `value` is JSON-serializable in **both** modes (recursion-contract.md §4). Embedded executors, however, can in practice produce any Python object and only have it rejected at envelope time. Spawned mode would catch the same failure earlier (at serialization). This is consistent on the surface, but executors that happen to "work" embedded by returning, say, a `datetime` will break under spawn. Need a single shared `assert_json_serializable` helper invoked by both paths to keep their failure surfaces identical.

## 2. Budget ledger identity

Embedded mode shares a single in-memory `BudgetLedger`. Spawned mode hands the child a **serialized budget allocation** (a limit, not the ledger). The child must:

- run its own ephemeral ledger rooted at the allocated limit;
- return `used` totals plus its emitted events;
- never see the parent's events.

Open questions:

- Does the child report **all** ledger events back for replay, or only a `used` summary? Replay is auditable but doubles ledger size; summary is cheaper but loses sub-step granularity.
- Are child budget IDs `root.N` (re-rooted) or `parent_id.N` (continued)? Re-rooted is simpler; continued preserves global IDs for debugging. Recommend continued, with the child told its `parent_budget_id` so it can prefix.

## 3. `ask_user` across the process boundary

`ask_user` is a parent-supplied callback. A spawned child cannot call back into the parent process for a human prompt without a side channel. Options:

- **Disallow** — spawn the child with `ask_user=None`; child must proceed best-effort. Simplest, but cuts off a real use case.
- **Round-trip via stdout/stdin** — the worker emits an `ask_user_request` JSON record and blocks until the parent writes the answer back on stdin. Doable, but means the worker is no longer "one JSON in, one JSON out"; the protocol becomes a small synchronous RPC.

The current `spawned-worker-protocol.md` is silent on this. Pick one before v2.

## 4. Provider transport across the boundary

`spawned-worker-protocol.md` §5 lets the parent pass `{"kind": "larql", "transport": "http", "endpoint": "..."}`. That works for Larql but not for an in-process `CallableProvider` (used in tests). Spawned mode therefore breaks the test provider — tests have to switch providers depending on mode. Either:

- restrict spawned mode to network-reachable providers, or
- introduce a "callback provider" where the worker tunnels `llm()` calls back over stdout/stdin (same machinery as §3).

## 5. Determinism under fork/exec

The v1 seed derivation (`sha256(f"{run_seed}|{budget_id}")`) is process-independent, so spawned mode does not break determinism for **random default-policy resolution**. But Monty's own RNG state, if it has one, must also be derivable from `(run_seed, budget_id)` — confirm with the Monty author. Also confirm that Python's hash randomization (`PYTHONHASHSEED`) is fixed in the worker (we already constrain executors against dict-order-dependent code, but worth pinning explicitly).

## 6. Error code coverage

`spawn_failed` and `spawn_protocol_error` are listed in the host-error table (`recursion-contract.md` §4) but cannot fire in embedded mode. They are dead code in v1. Either:

- keep them in the table with the deferred-mode note (current choice), or
- move them to a "spawned-mode additions" section to keep the v1 surface minimal.

## 7. Refund event identity across boundary

Embedded refunds debit the child's ledger and credit the parent's atomically. Spawned refunds happen after the worker exits: the parent reads `used`, computes `refund = allocated - used`, emits `refund_child`. There is a one-event-write window during which the worker is gone but the refund isn't recorded yet. A crash there leaks the entire envelope. Need: durable parent-side write of `allocate_child` **before** spawn, and a recovery rule on parent restart for orphaned child IDs (treat as fully refunded).

## 8. Logging discipline

`spawned-worker-protocol.md` §3 mandates "logs only to stderr." Easy to state, easy to violate (any `print`, any third-party library that writes to stdout). Need either a stdout-redirect wrapper around `run_step` in the worker entry point, or an assertion that the worker's stdout contains exactly one line.

## 9. Resource limits

Process isolation is **not** a sandbox (already noted in `spawned-worker-protocol.md` §9). Adding real limits (filesystem, network, CPU, memory) is out of v1 scope and may want a separate runner (e.g. invoke the worker under `firejail`, Docker, or a Modal/E2B sandbox). The contract should remain transport-neutral about which sandbox is in use.

## 10. Acceptance criteria for "enable spawned mode"

Before flipping spawned mode on:

- Issues 1, 2, 5, 7, 8 resolved with code, not just doc.
- Issue 3 resolved as either "no ask_user in spawned" or "RPC over stdin/stdout."
- Contract test: a fixed `(input, budget, seed, provider, kind)` produces byte-identical `value` and identical refund accounting in both modes.
- Contract test: every `host_error.code` reachable in embedded mode is also reachable in spawned mode (or explicitly documented as embedded-only).
