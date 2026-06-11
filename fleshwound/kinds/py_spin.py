"""Built-in catalog kind: py_spin.

Deliberate non-Monty infinite loop for executor timeout contract tests.

When to use: verify plain-Python executors are guarded by pytest-timeout.

Similar kinds: ``budget_hog`` target ``spin``; ``noop_fail``.

Prefer alternatives when: testing Monty preemption — use ``budget_hog`` spin target."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("py_spin", convention="non-Monty infinite loop fixture")
def py_spin(input: dict[str, Any], ctx: Any) -> dict[str, str]:
    if not input.get("spin"):
        return {"status": "idle"}
    while True:
        pass
