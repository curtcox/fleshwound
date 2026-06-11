"""Built-in catalog kind: constant.

Returns ``input["value"]`` verbatim; no LLM, child steps, or Monty.

When to use: contract baselines and typed pass-through leaves.

Similar kinds: ``echo``; ``monty_exec``.

Prefer alternatives when: use ``echo`` for whole-input pass-through; use
``monty_exec`` for light computed returns."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("constant", convention="input.value -> value verbatim; host charges one step")
def constant(input: Any, ctx: Any) -> Any:
    return input["value"]

