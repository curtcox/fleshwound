"""Built-in catalog kind: constant."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("constant", convention="input.value -> value verbatim; host charges one step")
def constant(input: Any, ctx: Any) -> Any:
    return input["value"]

