"""Built-in catalog kind: noop_fail.

Raises an uncaught exception in host Python before returning a value.

When to use: host safety-net tests for ``executor_error`` wrapping.

Similar kinds: ``noop_fail_monty``; ``always_host_error``.

Prefer alternatives when: use ``noop_fail_monty`` for Monty path; use
``always_host_error`` for specific ``host_error.code`` values."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("noop_fail", convention="always raises a host-Python exception")
def noop_fail(input: Any, ctx: Any) -> Any:
    raise RuntimeError("deliberate noop_fail")

