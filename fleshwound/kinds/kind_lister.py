"""Built-in catalog kind: kind_lister.

Returns sorted catalog names and one-line ``convention`` strings from ``ctx.catalog``.

When to use: introspection and regression that ``ctx.catalog`` stays wired.

Similar kinds: ``kind_chooser``; ``catalog_self_test``; ``dynamic_dispatch``.

Prefer alternatives when: use ``kind_chooser`` for recommendations; use
``catalog_self_test`` to validate execution."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("kind_lister", convention="{} -> catalog names and conventions")
def kind_lister(input: Any, ctx: Any) -> dict[str, Any]:
    return {"kinds": [{"name": name, "convention": convention} for name, convention in sorted(ctx.catalog.items())]}

