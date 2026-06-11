"""Built-in catalog kind: echo."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("echo", convention="input -> input verbatim; host charges one step")
def echo(input: Any, ctx: Any) -> Any:
    return input

