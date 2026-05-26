"""Deterministic budget ledger for Fleshwound runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BudgetLimit:
    tokens: int
    steps: int
    depth: int
    tool_calls: int

    @classmethod
    def from_value(cls, value: "BudgetLimit | dict[str, int]") -> "BudgetLimit":
        if isinstance(value, cls):
            return value
        return cls(
            tokens=int(value.get("tokens", 0)),
            steps=int(value.get("steps", 0)),
            depth=int(value.get("depth", 0)),
            tool_calls=int(value.get("tool_calls", 0)),
        )

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class BudgetUsage:
    tokens: int = 0
    steps: int = 0
    tool_calls: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class BudgetSnapshot:
    budget_id: str
    parent_budget_id: str | None
    limit: BudgetLimit
    used: BudgetUsage
    remaining: BudgetLimit

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "parent_budget_id": self.parent_budget_id,
            "limit": self.limit.to_dict(),
            "used": self.used.to_dict(),
            "remaining": self.remaining.to_dict(),
        }


@dataclass(frozen=True)
class BudgetEvent:
    seq: int
    budget_id: str
    kind: str
    amount: dict[str, int]
    reason: str
    resolved_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _BudgetNode:
    budget_id: str
    parent_budget_id: str | None
    limit: BudgetLimit
    used: BudgetUsage
    child_count: int = 0
    closed: bool = False


class BudgetDenied(Exception):
    """Raised by low-level ledger APIs when a requested mutation is invalid."""


class BudgetLedger:
    def __init__(self, root: BudgetLimit | dict[str, int], *, root_id: str = "root") -> None:
        root_limit = BudgetLimit.from_value(root)
        self._nodes: dict[str, _BudgetNode] = {
            root_id: _BudgetNode(root_id, None, root_limit, BudgetUsage())
        }
        self.events: list[BudgetEvent] = []
        self._seq = 0
        self._event(root_id, "create_root", root_limit.to_dict(), "create_root")

    def _event(
        self,
        budget_id: str,
        kind: str,
        amount: dict[str, int],
        reason: str,
        *,
        resolved_kind: str | None = None,
    ) -> None:
        self._seq += 1
        self.events.append(
            BudgetEvent(
                self._seq,
                budget_id,
                kind,
                dict(amount),
                reason,
                resolved_kind,
            )
        )

    def _node(self, budget_id: str) -> _BudgetNode:
        try:
            return self._nodes[budget_id]
        except KeyError as exc:
            raise KeyError(f"unknown budget_id {budget_id!r}") from exc

    def snapshot(self, budget_id: str) -> BudgetSnapshot:
        node = self._node(budget_id)
        remaining = BudgetLimit(
            tokens=node.limit.tokens - node.used.tokens,
            steps=node.limit.steps - node.used.steps,
            depth=node.limit.depth,
            tool_calls=node.limit.tool_calls - node.used.tool_calls,
        )
        return BudgetSnapshot(
            budget_id=node.budget_id,
            parent_budget_id=node.parent_budget_id,
            limit=node.limit,
            used=BudgetUsage(node.used.tokens, node.used.steps, node.used.tool_calls),
            remaining=remaining,
        )

    def monty_snapshot(self, budget_id: str) -> dict[str, int | str]:
        snap = self.snapshot(budget_id)
        return {
            "budget_id": snap.budget_id,
            "tokens_remaining": snap.remaining.tokens,
            "steps_remaining": snap.remaining.steps,
            "depth_remaining": snap.remaining.depth,
            "tool_calls_remaining": snap.remaining.tool_calls,
        }

    def charge_tokens(self, budget_id: str, amount: int, reason: str) -> bool:
        if amount < 0:
            raise ValueError("token charge must be non-negative")
        node = self._node(budget_id)
        if node.used.tokens + amount > node.limit.tokens:
            self._event(budget_id, "deny", {"tokens": amount}, reason)
            return False
        node.used.tokens += amount
        self._event(budget_id, "charge_tokens", {"tokens": amount}, reason)
        return True

    def charge_step(self, budget_id: str, reason: str) -> bool:
        node = self._node(budget_id)
        if node.used.steps + 1 > node.limit.steps:
            self._event(budget_id, "deny", {"steps": 1}, reason)
            return False
        node.used.steps += 1
        self._event(budget_id, "charge_step", {"steps": 1}, reason)
        return True

    def charge_tool_call(self, budget_id: str, reason: str) -> bool:
        node = self._node(budget_id)
        if node.used.tool_calls + 1 > node.limit.tool_calls:
            self._event(budget_id, "deny", {"tool_calls": 1}, reason)
            return False
        node.used.tool_calls += 1
        self._event(budget_id, "charge_tool_call", {"tool_calls": 1}, reason)
        return True

    def allocate_child(
        self,
        parent_budget_id: str,
        requested: BudgetLimit | dict[str, int],
        reason: str,
        *,
        resolved_kind: str | None = None,
    ) -> str | None:
        request = BudgetLimit.from_value(requested)
        parent = self._node(parent_budget_id)
        available = self.snapshot(parent_budget_id).remaining
        valid = (
            request.tokens >= 0
            and request.steps >= 1
            and request.depth >= 1
            and request.tool_calls >= 0
            and request.tokens <= available.tokens
            and request.steps <= available.steps
            and request.depth <= available.depth - 1
            and request.tool_calls <= available.tool_calls
        )
        if not valid:
            self._event(parent_budget_id, "deny", request.to_dict(), reason)
            return None
        parent.child_count += 1
        child_id = f"{parent_budget_id}.{parent.child_count}"
        parent.used.tokens += request.tokens
        parent.used.steps += request.steps
        parent.used.tool_calls += request.tool_calls
        self._nodes[child_id] = _BudgetNode(child_id, parent_budget_id, request, BudgetUsage())
        self._event(
            parent_budget_id,
            "allocate_child",
            request.to_dict(),
            reason,
            resolved_kind=resolved_kind,
        )
        return child_id

    def close_child(self, child_budget_id: str, reason: str = "close_child") -> BudgetSnapshot:
        child = self._node(child_budget_id)
        if child.parent_budget_id is None:
            raise ValueError("root budget cannot be closed as a child")
        if child.closed:
            return self.snapshot(child_budget_id)
        parent = self._node(child.parent_budget_id)
        remaining = self.snapshot(child_budget_id).remaining
        parent.used.tokens -= remaining.tokens
        parent.used.steps -= remaining.steps
        parent.used.tool_calls -= remaining.tool_calls
        self._event(child.parent_budget_id, "refund_child", remaining.to_dict(), reason)
        child.closed = True
        self._event(child_budget_id, "close_child", {}, reason)
        return self.snapshot(child_budget_id)
