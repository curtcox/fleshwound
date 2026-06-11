"""Built-in catalog kind: always_partial."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("always_partial", convention="returns a deliberate partial value")
def always_partial(input: Any, ctx: Any) -> dict[str, str]:
    return {"status": "partial", "program": "", "notes": "deliberate partial for tests"}

