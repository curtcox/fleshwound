"""Shared helpers for built-in catalog kinds."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def request(ctx: Any, parts: int = 1) -> dict[str, int]:
    snap = ctx.budget()
    steps = max(1, snap["steps_remaining"] // max(parts, 1))
    depth = max(1, snap["depth_remaining"] - 1)
    return {
        "tokens": max(0, snap["tokens_remaining"] // max(parts, 1)),
        "steps": steps,
        "depth": depth,
        "tool_calls": max(0, snap["tool_calls_remaining"] // max(parts, 1)),
    }


def monty_run(code: str, input: Any, ctx: Any) -> Any:
    try:
        import pydantic_monty
    except ImportError as exc:
        raise RuntimeError("pydantic_monty is required for Monty-backed kinds") from exc

    m = pydantic_monty.Monty(code, inputs=["input"])
    complete = m.run(
        inputs={"input": input},
        external_functions={
            "llm": ctx.llm,
            "step": ctx.step,
            "ask_user": ctx.ask_user,
            "budget": ctx.budget,
            "catalog": lambda: dict(ctx.catalog),
        },
    )
    return getattr(complete, "output", complete)


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
