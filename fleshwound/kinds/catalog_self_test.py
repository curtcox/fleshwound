"""Built-in catalog kind: catalog_self_test.

Runs minimal viable input through each catalog kind (or a subset) via ``ctx.step``
and collects outcomes.

When to use: broad regression sweeps with ``_minimal_input.py`` and Group E fixtures.

Similar kinds: ``regression_canary``; ``kind_lister``; ``noop_fail``.

Prefer alternatives when: use ``regression_canary`` for golden-hash determinism on
one kind; use ``kind_lister`` for metadata only."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._minimal_input import minimal_input
from ._shared import request


@register("catalog_self_test", convention="run minimal inputs for listed kinds")
def catalog_self_test(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    names = input.get("kinds_to_exercise") or sorted(ctx.catalog)
    results = []
    expected_failure_kinds = {"always_host_error", "budget_hog", "infinite_descent", "noop_fail", "noop_fail_monty"}
    for name in names:
        if name == "catalog_self_test":
            continue
        result = ctx.step(minimal_input(name), request(ctx, len(names) or 1), kind=name)
        expected_host_error = name in expected_failure_kinds
        unexpected = result["outcome"] == "host_error" and not expected_host_error
        results.append(
            {
                "kind": name,
                "outcome": result["outcome"],
                "host_error": result.get("host_error"),
                "expected_host_error": expected_host_error,
                "unexpected_host_error": unexpected,
            }
        )
    return {"results": results, "unexpected_host_errors": [row for row in results if row["unexpected_host_error"]]}

