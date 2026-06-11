"""Built-in catalog kind: directory_input.

Assembles prose context from a virtual ``tree`` and delegates to
``program_writer`` with the caller's ``task``.

When to use: repo-shaped tasks with caller-materialized file JSON.

Similar kinds: ``program_writer``; ``repo_walker``; ``directory_writer``.

Prefer alternatives when: use ``program_writer`` when context is already a dict;
use ``repo_walker`` for per-file processing."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("directory_input", convention="delegate virtual tree task to program_writer")
def directory_input(input: dict[str, Any], ctx: Any) -> Any:
    return ctx.step({"task": input.get("task"), "context": {"tree": input.get("tree")}}, request(ctx), kind="program_writer")

