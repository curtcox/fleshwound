"""Built-in catalog kind: adversarial_loop.

Alternates ``attack_generator`` and ``target_kind`` up to ``max_rounds``, stopping
on the first target ``host_error`` or when a success predicate matches.

When to use: end-to-end red-team loops; any kind can be both attacker parent and
victim child.

Similar kinds: ``attack_generator`` (one crafted input); ``refine_until`` (benign
iterate/judge); ``cascade`` (try kinds, not adaptive attacks).

Prefer alternatives when: use ``attack_generator`` alone for one-shot inputs; use
``refine_until`` for quality iteration; use fixed pytest inputs for stable CI."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("adversarial_loop", convention="attack target repeatedly")
def adversarial_loop(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    history = []
    current = input.get("seed_input")
    winning = None
    for _ in range(max(0, int(input.get("max_rounds", 1)))):
        attack = ctx.step({"target_kind": input.get("target_kind"), "target_input_template": current, "attack_goal": input.get("success_predicate")}, request(ctx), kind="attack_generator")
        current = attack.get("value", {}).get("crafted_input", current) if attack["outcome"] == "ok" else current
        target = ctx.step(current, request(ctx), kind=input.get("target_kind"))
        successful = target["outcome"] == "host_error"
        history.append({"input": current, "target_result": target, "successful": successful})
        if successful:
            winning = current
            break
    return {"rounds": len(history), "history": history, "winning_input": winning}

