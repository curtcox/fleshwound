"""Contract-shaped Fleshwound runner."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from .budget import BudgetLedger, BudgetLimit
from .catalog import Catalog, UnknownKind, catalog as default_catalog
from .context import RunContext
from .errors import HostError
from .provider import CallableProvider, ModelProvider, Usage

import fleshwound.kinds  # noqa: F401  side-effect: register built-ins


DEFAULT_BUDGET = {"tokens": 100_000, "steps": 32, "depth": 8, "tool_calls": 16}
HOST_ERROR_CODES = {
    "budget_exhausted",
    "budget_denied",
    "monty_error",
    "malformed_result",
    "spawn_failed",
    "spawn_protocol_error",
    "unknown_kind",
    "unresolvable_default",
    "executor_error",
}


@dataclass(frozen=True)
class RunOptions:
    """Run-wide configuration threaded through the recursion tree.

    Passed to :func:`run_step` as ``options=`` and inherited by every step in
    the run. Individual fields may be overridden for a child's subtree via the
    matching kwargs on :meth:`RunContext.step` (``default_policy``, ``provider``,
    ``ask_user`` only).

    Attributes:
        budget: Root budget envelope. A :class:`~fleshwound.budget.BudgetLimit` or
            dict with keys ``tokens``, ``steps``, ``depth``, and ``tool_calls``.
            Used only when :attr:`ledger` is omitted; in that case a new root
            :class:`~fleshwound.budget.BudgetLedger` is created from this value
            (defaulting to :data:`DEFAULT_BUDGET` when both are omitted). Child
            budgets are carved out of this root by each ``ctx.step()`` call.
        provider: LLM backend for the run. Accepts a :class:`~fleshwound.provider.ModelProvider`
            (``.generate(prompt)``) or a bare ``Callable[[str], str]``, which is
            wrapped in :class:`~fleshwound.provider.CallableProvider`. When
            ``None``, normalizes to a no-op provider that returns empty text.
            Every step uses this provider for :meth:`RunContext.llm` unless a
            child overrides it via ``step(..., provider=...)``. Token usage from
            each call is charged to the active budget.
        default_policy: Kind-resolution policy applied whenever ``step()`` or
            ``run_step()`` is called without ``kind=``. Supported values:

            - ``"same_as_parent"`` (default) — use the calling step's kind.
              Cannot resolve at the root (``run_step(kind=None)``).
            - ``"random"`` — pick uniformly from the entire catalog.
            - ``{"random_from_subset": [names...]}`` — pick uniformly from the
              named subset (deduped). Empty subset → ``unresolvable_default``;
              unknown name → ``unknown_kind``.

            Inherited by children; overridable per child via
            ``step(..., default_policy=...)``. Random picks are deterministic
            via :func:`derive_seed` using :attr:`seed` and the child's budget id.
        seed: Run-wide seed for deterministic random default-policy picks.
            Combined with each child's ``budget_id`` through :func:`derive_seed`
            to derive per-allocation RNG state. Does not affect the provider or
            other sources of variation.
        ask_user: Optional human callback ``(question: str) -> str``. When
            ``None``, ``ctx.ask_user`` is unavailable to executors (kinds must
            handle absence). Not charged against any budget dimension; may block
            indefinitely. Inherited by children; overridable per child via
            ``step(..., ask_user=...)``.
        catalog: Kind registry override. When ``None``, uses the built-in
            registry (:data:`~fleshwound.catalog.catalog`). Primarily for
            testing or advanced callers that inject local entries. Static for
            the run; exposed read-only to executors as ``ctx.catalog``.
        ledger: Pre-built budget ledger. When ``None``, a new root ledger is
            created from :attr:`budget` (or :data:`DEFAULT_BUDGET`). When
            provided, :attr:`budget` is ignored for ledger construction.
            Primarily for testing (inspect events, pre-seed state) or advanced
            callers. The same ledger instance is threaded through the entire
            recursion tree.
    """

    budget: BudgetLimit | dict[str, int] | None = None
    provider: ModelProvider | Callable[[str], str] | None = None
    default_policy: Any = "same_as_parent"
    seed: int = 0
    ask_user: Callable[[str], str] | None = None
    catalog: Catalog | None = None
    ledger: BudgetLedger | None = None


@dataclass(frozen=True)
class _ResolvedRunOptions:
    default_policy: Any
    seed: int
    provider: ModelProvider
    ask_user: Callable[[str], str] | None
    catalog: Catalog
    ledger: BudgetLedger


def ok(value: Any) -> dict[str, Any]:
    return {"outcome": "ok", "value": value, "host_error": None}


def host_error(code: str, message: str) -> dict[str, Any]:
    return {
        "outcome": "host_error",
        "value": None,
        "host_error": {"code": code, "message": message},
    }


def derive_seed(run_seed: int, budget_id: str) -> int:
    digest = hashlib.sha256(f"{run_seed}|{budget_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _jsonable(value: Any) -> bool:
    try:
        json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return False
    return True


def _usage_dict(usage: Any) -> dict[str, int]:
    if isinstance(usage, Usage):
        return usage.to_dict()
    if hasattr(usage, "to_dict"):
        return usage.to_dict()
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": int(usage.get("total_tokens", prompt + completion)),
        }
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _normalize_provider(
    provider: ModelProvider | Callable[[str], str] | None,
) -> ModelProvider:
    if provider is None:
        return CallableProvider(lambda prompt: "")
    if callable(provider) and not hasattr(provider, "generate"):
        return CallableProvider(provider)  # type: ignore[arg-type]
    return provider  # type: ignore[return-value]


def _resolve_options(options: RunOptions | None) -> _ResolvedRunOptions:
    opts = options or RunOptions()
    return _ResolvedRunOptions(
        default_policy=opts.default_policy,
        seed=opts.seed,
        provider=_normalize_provider(opts.provider),
        ask_user=opts.ask_user,
        catalog=opts.catalog or default_catalog,
        ledger=opts.ledger or BudgetLedger(opts.budget or DEFAULT_BUDGET),
    )


def _merge_step_overrides(
    options: _ResolvedRunOptions,
    *,
    default_policy: Any | None = None,
    provider: ModelProvider | None = None,
    ask_user: Callable[[str], str] | None = None,
) -> _ResolvedRunOptions:
    updates: dict[str, Any] = {}
    if default_policy is not None:
        updates["default_policy"] = default_policy
    if provider is not None:
        updates["provider"] = provider
    if ask_user is not None:
        updates["ask_user"] = ask_user
    if not updates:
        return options
    return dataclasses.replace(options, **updates)


def _resolve_kind(
    kind: str | None,
    *,
    options: _ResolvedRunOptions,
    parent_kind: str | None,
    child_budget_id: str | None = None,
) -> str | dict[str, Any]:
    if kind is not None:
        try:
            options.catalog.lookup(kind)
        except UnknownKind:
            return host_error("unknown_kind", f"Unknown kind: {kind}")
        return kind
    policy = options.default_policy
    if policy == "same_as_parent":
        if parent_kind is None:
            return host_error(
                "unresolvable_default", "same_as_parent cannot resolve at root"
            )
        return parent_kind
    if policy == "random":
        names = sorted(options.catalog.entries)
        if not names:
            return host_error("unresolvable_default", "catalog is empty")
        return random.Random(
            derive_seed(options.seed, child_budget_id or "root")
        ).choice(names)
    if isinstance(policy, dict) and "random_from_subset" in policy:
        names = sorted(dict.fromkeys(policy.get("random_from_subset") or []))
        if not names:
            return host_error("unresolvable_default", "random_from_subset is empty")
        missing = [name for name in names if name not in options.catalog.entries]
        if missing:
            return host_error("unknown_kind", f"Unknown kind: {missing[0]}")
        return random.Random(
            derive_seed(options.seed, child_budget_id or "root")
        ).choice(names)
    return host_error("unresolvable_default", f"Unsupported default policy: {policy!r}")


def run_step(
    input: Any = None,
    *,
    kind: str | None = None,
    options: RunOptions | None = None,
) -> dict[str, Any]:
    """Run one step using the recursion contract API."""

    return _run_allocated_step(
        input,
        budget_id="root",
        kind=kind,
        parent_kind=None,
        options=_resolve_options(options),
    )


def _run_allocated_step(
    input: Any,
    *,
    budget_id: str,
    kind: str | None,
    parent_kind: str | None,
    options: _ResolvedRunOptions,
) -> dict[str, Any]:
    resolved = _resolve_kind(
        kind,
        options=options,
        parent_kind=parent_kind,
        child_budget_id=budget_id,
    )
    if isinstance(resolved, dict):
        options.ledger._event(budget_id, "deny", {}, resolved["host_error"]["message"])
        return resolved

    entry = options.catalog.lookup(resolved)
    if not options.ledger.charge_step(budget_id, f"run kind={resolved}"):
        return host_error("budget_exhausted", "No step budget remains.")

    def llm_fn(prompt: str) -> dict[str, Any]:
        try:
            result = options.provider.generate(prompt)
            usage = _usage_dict(result.usage)
            charged = options.ledger.charge_tokens(
                budget_id, usage["total_tokens"], "llm generation"
            )
            if not charged:
                return {
                    "status": "error",
                    "text": "",
                    "usage": usage,
                    "error": {
                        "code": "budget_exhausted",
                        "message": "Token budget exhausted.",
                    },
                }
            return {"status": "ok", "text": result.text, "usage": usage, "error": None}
        except Exception as exc:
            usage = {
                "prompt_tokens": len(str(prompt).split()),
                "completion_tokens": 0,
                "total_tokens": len(str(prompt).split()),
            }
            options.ledger.charge_tokens(
                budget_id, usage["total_tokens"], "llm generation (provider_error)"
            )
            return {
                "status": "error",
                "text": "",
                "usage": usage,
                "error": {"code": "provider_error", "message": str(exc)},
            }

    def step_fn(
        child_input: Any,
        request: dict[str, int],
        *,
        kind: str | None = None,
        default_policy: Any | None = None,
        provider: ModelProvider | None = None,
        ask_user: Callable[[str], str] | None = None,
    ) -> dict[str, Any]:
        child_options = _merge_step_overrides(
            options,
            default_policy=default_policy,
            provider=provider,
            ask_user=ask_user,
        )
        predicted_child_id = (
            f"{budget_id}.{options.ledger._node(budget_id).child_count + 1}"
        )
        resolved_child = _resolve_kind(
            kind,
            options=child_options,
            parent_kind=resolved,
            child_budget_id=predicted_child_id,
        )
        if isinstance(resolved_child, dict):
            options.ledger._event(
                budget_id,
                "deny",
                BudgetLimit.from_value(request).to_dict(),
                resolved_child["host_error"]["message"],
            )
            return resolved_child
        child_id = options.ledger.allocate_child(
            budget_id,
            request,
            f"allocate_child kind={resolved_child}",
            resolved_kind=resolved_child,
        )
        if child_id is None:
            return host_error(
                "budget_denied",
                "Requested child budget exceeds remaining parent budget.",
            )
        try:
            return _run_allocated_step(
                child_input,
                budget_id=child_id,
                kind=resolved_child,
                parent_kind=resolved,
                options=child_options,
            )
        finally:
            options.ledger.close_child(child_id, f"close_child kind={resolved_child}")

    ctx = RunContext(
        ledger=options.ledger,
        budget_id=budget_id,
        kind=resolved,
        provider=options.provider,
        catalog_obj=options.catalog,
        seed=options.seed,
        default_policy=options.default_policy,
        ask_user=options.ask_user,
        _step_fn=step_fn,
        _llm_fn=llm_fn,
    )
    try:
        value = entry.executor(input, ctx)
    except HostError as exc:
        return host_error(exc.code, exc.message)
    except Exception as exc:
        message = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        return host_error("monty_error" if entry.monty else "executor_error", message)
    if not _jsonable(value):
        return host_error(
            "malformed_result",
            f"Step value is not JSON-serializable for kind {resolved}.",
        )
    return ok(value)
