"""Built-in catalog kind: noop_fail."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("noop_fail", convention="always raises a host-Python exception")
def noop_fail(input: Any, ctx: Any) -> Any:
    raise RuntimeError("deliberate noop_fail")

