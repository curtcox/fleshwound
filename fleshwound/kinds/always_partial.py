"""Built-in catalog kind: always_partial.

Always returns a ``program_writer``-shaped value with ``status: "partial"`` and
empty program.

When to use: verify parents treat convention-level partial as ok ``outcome``, not
``host_error``.

Similar kinds: ``program_writer`` (real partial paths); ``noop_fail`` (hard
failures).

Prefer alternatives when: use ``program_writer`` for natural partial output; use
``noop_fail`` for exception paths."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("always_partial", convention="returns a deliberate partial value")
def always_partial(input: Any, ctx: Any) -> dict[str, str]:
    return {"status": "partial", "program": "", "notes": "deliberate partial for tests"}

