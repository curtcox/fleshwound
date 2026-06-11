"""Built-in catalog kind: classifier.

One LLM call assigns a label from a fixed list with optional confidence and
rationale extracted from the response.

When to use: simple categorization or routing labels.

Similar kinds: ``judge``; ``rubric_grader``; ``failure_classifier``.

Prefer alternatives when: use ``judge`` for pass/fail; use ``rubric_grader`` for
weighted multi-criterion grading; use ``failure_classifier`` for StepResult input."""

from __future__ import annotations

import re

from typing import Any

from ..catalog import register


@register("classifier", convention="text/labels -> label/confidence/rationale using ctx.llm")
def classifier(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    labels = list(input.get("labels") or [])
    result = ctx.llm(f"Classify this text into one of {labels}: {input.get('text', '')}")
    text = result.get("text", "").strip()
    label = next((label for label in labels if re.search(rf"\b{re.escape(label)}\b", text, re.I)), None)
    return {"label": label or (labels[0] if labels else ""), "confidence": None, "rationale": text}

