"""Contract-shaped Fleshwound runner with legacy doctor compatibility."""

from __future__ import annotations

import hashlib
import json
import random
import re
import traceback
from pathlib import Path
from typing import Any, Callable

from .budget import BudgetLedger, BudgetLimit
from .catalog import Catalog, UnknownKind, catalog as default_catalog
from .context import RunContext
from .errors import HostError
from .provider import CallableProvider, ModelProvider, Usage

import fleshwound.kinds  # noqa: F401  side-effect: register built-ins


STEP_PROMPT_PATH = Path(__file__).resolve().parent.parent / "Recursive_step_prompt.md"
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


def ok(value: Any) -> dict[str, Any]:
    return {"outcome": "ok", "value": value, "host_error": None}


def host_error(code: str, message: str) -> dict[str, Any]:
    return {"outcome": "host_error", "value": None, "host_error": {"code": code, "message": message}}


def derive_seed(run_seed: int, budget_id: str) -> int:
    digest = hashlib.sha256(f"{run_seed}|{budget_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _jsonable(value: Any) -> bool:
    try:
        json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return False
    return True


def _usage_total(usage: Any) -> int:
    if isinstance(usage, Usage):
        return usage.to_dict()["total_tokens"]
    if hasattr(usage, "to_dict"):
        return int(usage.to_dict().get("total_tokens", 0))
    if isinstance(usage, dict):
        return int(usage.get("total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)))
    return 0


def _usage_dict(usage: Any) -> dict[str, int]:
    if isinstance(usage, Usage):
        return usage.to_dict()
    if hasattr(usage, "to_dict"):
        return usage.to_dict()
    if isinstance(usage, dict):
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": int(usage.get("total_tokens", prompt + completion))}
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _resolve_kind(
    kind: str | None,
    *,
    default_policy: Any,
    parent_kind: str | None,
    catalog: Catalog,
    seed: int,
    child_budget_id: str | None = None,
) -> str | dict[str, Any]:
    if kind is not None:
        try:
            catalog.lookup(kind)
        except UnknownKind:
            return host_error("unknown_kind", f"Unknown kind: {kind}")
        return kind
    policy = default_policy
    if policy == "same_as_parent":
        if parent_kind is None:
            return host_error("unresolvable_default", "same_as_parent cannot resolve at root")
        return parent_kind
    if policy == "random":
        names = sorted(catalog.entries)
        if not names:
            return host_error("unresolvable_default", "catalog is empty")
        return random.Random(derive_seed(seed, child_budget_id or "root")).choice(names)
    if isinstance(policy, dict) and "random_from_subset" in policy:
        names = sorted(dict.fromkeys(policy.get("random_from_subset") or []))
        if not names:
            return host_error("unresolvable_default", "random_from_subset is empty")
        missing = [name for name in names if name not in catalog.entries]
        if missing:
            return host_error("unknown_kind", f"Unknown kind: {missing[0]}")
        return random.Random(derive_seed(seed, child_budget_id or "root")).choice(names)
    return host_error("unresolvable_default", f"Unsupported default policy: {policy!r}")


def run_step(
    input: Any = None,
    budget: BudgetLimit | dict[str, int] | None = None,
    provider: ModelProvider | Callable[[str], str] | None = None,
    *,
    kind: str | None = None,
    default_policy: Any = "same_as_parent",
    seed: int = 0,
    ask_user: Callable[[str], str] | None = None,
    catalog: Catalog | None = None,
    ledger: BudgetLedger | None = None,
    task: str | None = None,
    llm: Callable[[str], str] | None = None,
    context: dict | None = None,
    output_schema: dict | None = None,
    token_budget: int = 100_000,
    depth_remaining: int = 3,
) -> dict[str, Any]:
    """Run one step.

    The modern contract API returns a StepResult envelope. The legacy
    ``run_step(task=..., llm=...)`` path returns the raw value to keep the
    original doctor test and README example working.
    """

    if task is not None or llm is not None:
        return _legacy_run_step(
            task=task or "",
            llm=llm or (lambda prompt: ""),
            context=context,
            output_schema=output_schema,
            token_budget=token_budget,
            depth_remaining=depth_remaining,
        )

    active_catalog = catalog or default_catalog
    active_provider: ModelProvider
    if provider is None:
        active_provider = CallableProvider(lambda prompt: "")
    elif callable(provider) and not hasattr(provider, "generate"):
        active_provider = CallableProvider(provider)  # type: ignore[arg-type]
    else:
        active_provider = provider  # type: ignore[assignment]
    active_ledger = ledger or BudgetLedger(budget or DEFAULT_BUDGET)
    return _run_allocated_step(
        input,
        budget_id="root",
        kind=kind,
        parent_kind=None,
        default_policy=default_policy,
        seed=seed,
        provider=active_provider,
        ask_user=ask_user,
        catalog=active_catalog,
        ledger=active_ledger,
    )


def _run_allocated_step(
    input: Any,
    *,
    budget_id: str,
    kind: str | None,
    parent_kind: str | None,
    default_policy: Any,
    seed: int,
    provider: ModelProvider,
    ask_user: Callable[[str], str] | None,
    catalog: Catalog,
    ledger: BudgetLedger,
) -> dict[str, Any]:
    resolved = _resolve_kind(
        kind,
        default_policy=default_policy,
        parent_kind=parent_kind,
        catalog=catalog,
        seed=seed,
        child_budget_id=budget_id,
    )
    if isinstance(resolved, dict):
        ledger._event(budget_id, "deny", {}, resolved["host_error"]["message"])
        return resolved

    entry = catalog.lookup(resolved)
    if not ledger.charge_step(budget_id, f"run kind={resolved}"):
        return host_error("budget_exhausted", "No step budget remains.")

    def llm_fn(prompt: str) -> dict[str, Any]:
        try:
            result = provider.generate(prompt)
            usage = _usage_dict(result.usage)
            charged = ledger.charge_tokens(budget_id, usage["total_tokens"], "llm generation")
            if not charged:
                return {
                    "status": "error",
                    "text": "",
                    "usage": usage,
                    "error": {"code": "budget_exhausted", "message": "Token budget exhausted."},
                }
            return {"status": "ok", "text": result.text, "usage": usage, "error": None}
        except Exception as exc:
            usage = {"prompt_tokens": len(str(prompt).split()), "completion_tokens": 0, "total_tokens": len(str(prompt).split())}
            ledger.charge_tokens(budget_id, usage["total_tokens"], "llm generation (provider_error)")
            return {"status": "error", "text": "", "usage": usage, "error": {"code": "provider_error", "message": str(exc)}}

    def step_fn(
        child_input: Any,
        request: dict[str, int],
        *,
        kind: str | None = None,
        default_policy: Any = default_policy,
        provider: ModelProvider = provider,
        ask_user: Callable[[str], str] | None = ask_user,
    ) -> dict[str, Any]:
        predicted_child_id = f"{budget_id}.{ledger._node(budget_id).child_count + 1}"
        resolved_child = _resolve_kind(
            kind,
            default_policy=default_policy,
            parent_kind=resolved,
            catalog=catalog,
            seed=seed,
            child_budget_id=predicted_child_id,
        )
        if isinstance(resolved_child, dict):
            ledger._event(budget_id, "deny", BudgetLimit.from_value(request).to_dict(), resolved_child["host_error"]["message"])
            return resolved_child
        child_id = ledger.allocate_child(
            budget_id,
            request,
            f"allocate_child kind={resolved_child}",
            resolved_kind=resolved_child,
        )
        if child_id is None:
            return host_error("budget_denied", "Requested child budget exceeds remaining parent budget.")
        try:
            return _run_allocated_step(
                child_input,
                budget_id=child_id,
                kind=resolved_child,
                parent_kind=resolved,
                default_policy=default_policy,
                seed=seed,
                provider=provider,
                ask_user=ask_user,
                catalog=catalog,
                ledger=ledger,
            )
        finally:
            ledger.close_child(child_id, f"close_child kind={resolved_child}")

    ctx = RunContext(
        ledger=ledger,
        budget_id=budget_id,
        kind=resolved,
        provider=provider,
        catalog_obj=catalog,
        seed=seed,
        default_policy=default_policy,
        ask_user=ask_user,
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
        return host_error("malformed_result", f"Step value is not JSON-serializable for kind {resolved}.")
    return ok(value)


def _legacy_run_step(
    *,
    task: str,
    llm: Callable[[str], str],
    context: dict | None,
    output_schema: dict | None,
    token_budget: int,
    depth_remaining: int,
) -> dict[str, Any]:
    try:
        import pydantic_monty
    except ImportError as exc:
        raise RuntimeError("pydantic_monty is required for legacy Monty execution") from exc

    system = STEP_PROMPT_PATH.read_text()
    user_msg = (
        f"task = {task!r}\n"
        f"context = {context!r}\n"
        f"output_schema = {output_schema!r}\n"
        "\nProduce your Monty-subset Python now. The value of the final "
        "expression must be the output dict."
    )
    raw = llm(system + "\n\n---\n\n" + user_msg)
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    code = (match.group(1) if match else raw).strip()
    budget_state = {"tokens_remaining": token_budget, "depth_remaining": depth_remaining}

    def host_llm(prompt: str) -> str:
        budget_state["tokens_remaining"] -= 1000
        return llm(prompt)

    def host_step(sub_input: dict, request: int) -> dict:
        if budget_state["depth_remaining"] <= 0:
            return {"status": "partial", "program": "", "notes": "depth exhausted"}
        budget_state["tokens_remaining"] -= request
        return _legacy_run_step(
            task=sub_input.get("task", ""),
            llm=llm,
            context=sub_input.get("context"),
            output_schema=sub_input.get("output_schema"),
            token_budget=request,
            depth_remaining=budget_state["depth_remaining"] - 1,
        )

    m = pydantic_monty.Monty(code, inputs=["task", "context", "output_schema"])
    complete = m.run(
        inputs={"task": task, "context": context, "output_schema": output_schema},
        external_functions={
            "llm": host_llm,
            "step": host_step,
            "ask_user": lambda question: (_ for _ in ()).throw(RuntimeError(f"ask_user unavailable: {question!r}")),
            "budget": lambda: dict(budget_state),
        },
    )
    result = getattr(complete, "output", complete)
    if not isinstance(result, dict):
        raise RuntimeError(f"step did not return a dict; got {type(result).__name__}: {result!r}")
    return result
