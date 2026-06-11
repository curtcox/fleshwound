"""Built-in catalog kind: ask_user_only.

Asks one question via ``ctx.ask_user`` and returns the answer, or a structured
unavailable response when no callback was bound.

When to use: human-in-the-loop leaves and ``ask_user`` gating tests.

Similar kinds: ``clarify_then_delegate``; ``rlm_loop``.

Prefer alternatives when: use ``clarify_then_delegate`` when clarification feeds a
downstream kind; use a custom parent for multiple questions."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("ask_user_only", convention="question -> {'answer'} or unavailable note")
def ask_user_only(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    if ctx.ask_user is None:
        return {"answer": None, "notes": "ask_user unavailable"}
    return {"answer": ctx.ask_user(str(input.get("question", "")))}

