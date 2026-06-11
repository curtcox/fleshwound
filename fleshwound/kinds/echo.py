"""Built-in catalog kind: echo.

Returns the entire ``input`` unchanged; the simplest successful step.

When to use: identity steps, envelope smoke tests, and inner kind for
``budget_hog`` (steps target).

Similar kinds: ``constant``; ``monty_exec``.

Prefer alternatives when: use ``constant`` for explicit ``{"value": ...}`` input;
use ``monty_exec`` for computed returns."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("echo", convention="input -> input verbatim; host charges one step")
def echo(input: Any, ctx: Any) -> Any:
    return input

