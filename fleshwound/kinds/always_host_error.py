"""Built-in catalog kind: always_host_error.

Test fixture that triggers a specific ``host_error.code`` via raise, malformed
return, or budget denial depending on ``input.code``.

When to use: exhaustive host-error-path regression with ``catalog_self_test``.

Similar kinds: ``noop_fail`` / ``noop_fail_monty``; ``budget_hog``;
``infinite_descent``.

Prefer alternatives when: use ``noop_fail*`` for generic failures; use
``budget_hog`` or ``infinite_descent`` for budget-specific behavior."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ..errors import HostError


@register("always_host_error", convention="input.code triggers one host_error code")
def always_host_error(input: dict[str, Any], ctx: Any) -> Any:
    code = input.get("code")
    if code == "malformed_result":
        return object()
    if code in {
        "budget_exhausted",
        "budget_denied",
        "monty_error",
        "spawn_failed",
        "spawn_protocol_error",
        "unknown_kind",
        "unresolvable_default",
        "executor_error",
    }:
        raise HostError(code, f"forced {code}")
    raise RuntimeError(f"forced {code or 'executor_error'}")

