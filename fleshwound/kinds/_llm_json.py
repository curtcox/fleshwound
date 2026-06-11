"""Factory for LLM-backed structured JSON catalog kinds."""

from __future__ import annotations

import json
from typing import Any, Callable

from ..catalog import register


def register_llm_json_kind(
    name: str,
    prompt: str,
    fallback: Callable[[Any, str], Any],
    *,
    convention: str | None = None,
) -> None:
    summary = convention or f"LLM JSON kind {name}"
    @register(name, convention=summary)
    def executor(input: Any, ctx: Any) -> Any:
        text = ctx.llm(f"{prompt}\nInput: {json.dumps(input, sort_keys=True)}").get("text", "")
        try:
            return json.loads(text)
        except Exception:
            return fallback(input, text)
