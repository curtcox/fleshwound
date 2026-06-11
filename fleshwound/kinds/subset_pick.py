"""Built-in catalog kind: subset_pick.

Delegates with ``random_from_subset`` default policy over listed kind names.

When to use: constrained random dispatch and §6.3 edge-case tests.

Similar kinds: ``random_pick``; ``cond_dispatch``; ``dynamic_dispatch``.

Prefer alternatives when: use ``random_pick`` for full-catalog random; use
``cond_dispatch`` for deterministic rules."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("subset_pick", convention="delegate using random_from_subset default policy")
def subset_pick(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"result": ctx.step(input.get("inner_input"), request(ctx), kind=None, default_policy={"random_from_subset": input.get("subset", [])})}

