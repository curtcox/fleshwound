"""Built-in catalog kind: noop_fail_monty."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import monty_run

@register("noop_fail_monty", convention="always raises inside Monty", monty=True)
def noop_fail_monty(input: Any, ctx: Any) -> Any:
    return monty_run('raise Exception("deliberate noop_fail_monty")', input, ctx)

