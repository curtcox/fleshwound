"""Built-in catalog kind: monty_exec.

Evaluates Monty ``code`` with full ``ctx.*`` bound as externals; returns the final
expression value.

When to use: ad-hoc step logic without registering a dedicated kind.

Similar kinds: ``program_writer``; ``transformer``; ``precondition_gate``.

Prefer alternatives when: use ``program_writer`` when an LLM should author code;
use dedicated kinds when logic is stable and reusable."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import monty_run

@register("monty_exec", convention="code -> final Monty expression", monty=True)
def monty_exec(input: dict[str, Any], ctx: Any) -> Any:
    return monty_run(str(input.get("code", "")), input, ctx)

