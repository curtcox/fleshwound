"""Built-in catalog kind: regression_canary.

Runs frozen ``(frozen_kind, frozen_input)``, content-hashes the value, compares to
``expected_value_hash``.

When to use: determinism regression (§7) and golden-hash CI gates.

Similar kinds: ``catalog_self_test``; ``constant`` / ``echo``; ``content_hash_memo``.

Prefer alternatives when: use ``catalog_self_test`` for broad smoke; use pytest
goldens for full value comparison."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request, content_hash

@register("regression_canary", convention="hash child value and compare to expected")
def regression_canary(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    result = ctx.step(input.get("frozen_input"), request(ctx), kind=input.get("frozen_kind"))
    actual = content_hash(result.get("value")) if result["outcome"] == "ok" else content_hash(result)
    return {"passed": actual == input.get("expected_value_hash"), "actual_hash": actual, "result": result}

