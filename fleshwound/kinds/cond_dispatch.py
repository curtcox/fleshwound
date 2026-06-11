"""Built-in catalog kind: cond_dispatch.

Evaluates Monty ``when`` predicates on ``inner_input`` in branch order,
dispatching to the first matching ``kind`` or ``default_kind``.

When to use: deterministic routing without an LLM round.

Similar kinds: ``dynamic_dispatch``; ``precondition_gate``; ``subset_pick``.

Prefer alternatives when: use ``dynamic_dispatch`` for fuzzy rules; use
``precondition_gate`` for a single inner kind; use ``subset_pick`` for seeded
randomness within a set."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, monty_run

@register("cond_dispatch", convention="first true Monty predicate dispatches")
def cond_dispatch(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    chosen = input.get("default_kind")
    for branch in input.get("branches", []):
        if monty_run(str(branch.get("when", "False")), input.get("inner_input"), ctx):
            chosen = branch.get("kind")
            break
    return {"chosen_kind": chosen, "result": ctx.step(input.get("inner_input"), request(ctx), kind=chosen)}

