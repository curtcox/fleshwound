"""Built-in catalog kind: retry_wrapper.

Calls ``inner_kind`` up to ``max_attempts`` until ``outcome == "ok"``.

When to use: transient failures where refund semantics must allow retries.

Similar kinds: ``cascade``; ``refine_until``; ``ensemble``.

Prefer alternatives when: use ``cascade`` for different fallback kinds; use
``refine_until`` when each round changes the candidate."""

from __future__ import annotations

from typing import Any

from ..catalog import register
from ._shared import request


@register("retry_wrapper", convention="retry inner_kind until ok or max_attempts")
def retry_wrapper(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    max_attempts = max(0, int(input.get("max_attempts", 1)))
    last = None
    for attempt in range(max_attempts):
        last = ctx.step(input.get("inner_input"), request(ctx, max_attempts - attempt), kind=input.get("inner_kind"))
        if last["outcome"] == "ok":
            return {"attempts": attempt + 1, "result": last}
    return {"attempts": max_attempts, "result": last}

