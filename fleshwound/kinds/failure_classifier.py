"""Built-in catalog kind: failure_classifier.

LLM classifies a ``StepResult`` into failure categories (host_error vs convention
vs semantic ok).

When to use: triage when parents pass full envelopes; tests StepResult JSON
round-trip as input.

Similar kinds: ``classifier``; ``judge``; ``regression_canary``.

Prefer alternatives when: use ``classifier`` for non-envelope text; use
deterministic parent checks when rules are fixed."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "failure_classifier",
    "Classify failure.",
    lambda i, t: {"category": "ok", "subcategory": "", "evidence": t},
    convention="step_result -> failure category/evidence via ctx.llm",
)
