# Open Contract Issues

Ambiguities surfaced while writing [`recursion-kinds-catalog.md`](recursion-kinds-catalog.md)
as a contract-stress fixture. Items C-1, C-2, and C-4 through C-12 are settled in
[`recursion-contract.md`](recursion-contract.md) and [`budget-ledger.md`](budget-ledger.md);
they are not listed here.

Three items remain open.

## C-3. Sibling child ID order

**Blocks:** Kinds that map sibling results by `budget_id` suffix (`map_reduce`, `ensemble`).

**Question:** Does `parent.N` mean the Nth child **started** or the Nth child **finished**?

**Answer (implemented, not yet spelled out in the ledger spec):** Indices come from the
order of successful `allocate_child` calls on the parent budget. The embedded ledger
increments a per-parent counter at allocation time (`root.1`, `root.2`, …). Child
completion order does not affect IDs.

**Still needed:** Tighten `budget-ledger.md` §3 rule 3 — replace "allocation order" with
"the order of successful `allocate_child` calls on the parent budget."

## C-5. Wall-clock and environment nondeterminism

**Blocks:** Hard replay guarantees for Monty-based executors.

**Question:** Is determinism enforced by the host or left to kind authors?

**Current state:** `recursion-contract.md` §7 tells executors not to rely on wall-clock
time, OS environment, or similar ambient state, but Monty still exposes `datetime`, `os`,
and `asyncio`. The host does not unbind or stub those reads today.

**Options:**

| Option | Effect |
|---|---|
| **(a) Host enforcement** *(recommended for v1)* | Unbind or stub ambient nondeterminism in Monty executors so violations fail at runtime instead of silently breaking replay. |
| **(b) Author responsibility** | Leave imports available; determinism becomes an audit/review requirement with no runtime guard. |

**Still needed:** Choose (a) or (b) and update §7 plus any Monty binding policy.

## C-6. Parent `ctx.budget()` while a child is running

**Blocks:** Kinds that split remaining budget across sequential children (`budget_hog`,
`map_reduce`, `rlm_loop` action validation).

**Question:** While a child is mid-flight, does the parent's `ctx.budget()` include the
child's reserved envelope in `*_remaining`, or exclude it?

**Answer (implemented, not yet documented):** **Exclude it.** On successful
`allocate_child`, the parent ledger debits the requested envelope immediately. The
parent's `tokens_remaining`, `steps_remaining`, and `tool_calls_remaining` therefore
show balances **after** all active child reservations. Unused child budget is refunded
when the child closes (`refund_child` → `close_child`). Spawned mode should preserve
the same semantics once `allocate_child` is durable before spawn.

**Still needed:** State this in `recursion-contract.md` §3 (`budget()`) and
`budget-ledger.md` §8 (Monty-visible snapshot).
