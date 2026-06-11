"""Built-in catalog kind: directory_input."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("directory_input", convention="delegate virtual tree task to program_writer")
def directory_input(input: dict[str, Any], ctx: Any) -> Any:
    return ctx.step({"task": input.get("task"), "context": {"tree": input.get("tree")}}, request(ctx), kind="program_writer")

