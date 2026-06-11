"""Built-in catalog kind: noop_fail_monty.

Runs Monty code that deliberately raises, producing ``monty_error``.

When to use: contract tests for Monty executors vs host Python failures.

Similar kinds: ``noop_fail``; ``monty_exec``.

Prefer alternatives when: use ``noop_fail`` for non-Monty executors; use
``monty_exec`` for controlled Monty behavior."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import monty_run

@register("noop_fail_monty", convention="always raises inside Monty", monty=True)
def noop_fail_monty(input: Any, ctx: Any) -> Any:
    return monty_run('raise Exception("deliberate noop_fail_monty")', input, ctx)

