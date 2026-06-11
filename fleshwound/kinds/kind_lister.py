"""Built-in catalog kind: kind_lister."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("kind_lister", convention="{} -> catalog names and conventions")
def kind_lister(input: Any, ctx: Any) -> dict[str, Any]:
    return {"kinds": [{"name": name, "convention": convention} for name, convention in sorted(ctx.catalog.items())]}

