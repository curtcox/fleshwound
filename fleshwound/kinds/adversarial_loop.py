"""Built-in catalog kind: adversarial_loop."""

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

