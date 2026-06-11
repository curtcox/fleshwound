"""Built-in catalog kind: provider_swap.

Runs ``inner_kind`` under an overridden ``provider`` (per-subtree inheritance).

When to use: multi-model pipelines and provider override contract tests.

Similar kinds: ``transformer``; ``pipeline``.

Prefer alternatives when: use per-stage overrides in custom parents when only some
hops swap models."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("provider_swap", convention="delegates with supplied provider object if present")
def provider_swap(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    provider = input.get("inner_provider") or ctx.provider
    return {"result": ctx.step(input.get("inner_input"), request(ctx), kind=input.get("inner_kind"), provider=provider)}

