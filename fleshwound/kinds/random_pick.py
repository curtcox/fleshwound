"""Built-in catalog kind: random_pick.

Delegates ``inner_input`` with ``default_policy="random"`` (seed-derived kind).

When to use: §6.3 seed-stable random default resolution tests.

Similar kinds: ``subset_pick``; ``dynamic_dispatch``; ``kind_chooser``.

Prefer alternatives when: use ``subset_pick`` to constrain candidates; use
``dynamic_dispatch`` for explicit or LLM choice."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("random_pick", convention="delegate using random default policy")
def random_pick(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"result": ctx.step(input.get("inner_input"), request(ctx), kind=None, default_policy="random")}

