"""Built-in catalog kind: dynamic_dispatch.

Chooses a kind name (literal or LLM over ``ctx.catalog``), then delegates
``inner_input`` with ``kind=chosen_kind``.

When to use: runtime routing when the target kind is not known at plan time.

Similar kinds: ``meta_planner``; ``cond_dispatch``; ``kind_chooser``;
``subset_pick`` / ``random_pick``.

Prefer alternatives when: use ``meta_planner`` for multi-step plans; use
``cond_dispatch`` for deterministic rules; use ``kind_chooser`` when selection and
execution should split."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("dynamic_dispatch", convention="choose kind literally or by llm then delegate")
def dynamic_dispatch(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    chosen = input.get("literal_kind")
    if input.get("chooser") == "llm":
        chosen = ctx.llm(f"Choose one kind from {sorted(ctx.catalog)} for {input.get('task_for_chooser')}").get("text", "").strip()
    return {"chosen_kind": chosen, "result": ctx.step(input.get("inner_input"), request(ctx), kind=chosen)}

