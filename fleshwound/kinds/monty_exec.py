"""Built-in catalog kind: monty_exec."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import monty_run

@register("monty_exec", convention="code -> final Monty expression", monty=True)
def monty_exec(input: dict[str, Any], ctx: Any) -> Any:
    return monty_run(str(input.get("code", "")), input, ctx)

