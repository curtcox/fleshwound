"""Built-in catalog kind: kind_chooser.

One LLM call selects a catalog kind name for a task using rendered ``ctx.catalog``.

When to use: planning/routing where execution happens in a separate parent step.

Similar kinds: ``dynamic_dispatch``; ``meta_planner``; ``random_pick``.

Prefer alternatives when: use ``dynamic_dispatch`` to choose and run together; use
``meta_planner`` for multi-step plans."""

from __future__ import annotations

import json

from typing import Any

from ..catalog import register


@register("kind_chooser", convention="task -> chosen_kind/rationale using catalog-grounded llm")
def kind_chooser(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    catalog_doc = json.dumps(dict(sorted(ctx.catalog.items())), sort_keys=True)
    text = ctx.llm(f"Choose a catalog kind for this task.\nCatalog: {catalog_doc}\nTask: {input.get('task')}").get("text", "")
    try:
        return json.loads(text)
    except Exception:
        return {"chosen_kind": text.strip(), "rationale": text}

