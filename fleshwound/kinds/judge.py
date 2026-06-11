"""Built-in catalog kind: judge."""

from __future__ import annotations

from typing import Any

from ..catalog import register


@register("judge", convention="candidate/criteria -> pass/fail/rationale")
def judge(input: dict[str, Any], ctx: Any) -> dict[str, str]:
    result = ctx.llm(f"Judge pass or fail.\nCriteria: {input.get('criteria')}\nCandidate: {input.get('candidate')}")
    text = result.get("text", "")
    return {"verdict": "pass" if "pass" in text.lower() else "fail", "rationale": text}

