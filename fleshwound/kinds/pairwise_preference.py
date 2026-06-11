"""Built-in catalog kind: pairwise_preference.

One LLM call comparing ``a`` and ``b`` under a criterion; returns winner
(``a``|``b``|``tie``) plus rationale.

When to use: atomic comparison for ``tournament`` brackets or A/B tests.

Similar kinds: ``judge``; ``tournament``; ``ensemble``.

Prefer alternatives when: use ``judge`` for single-candidate criteria; use
``rubric_grader`` for numeric multi-criterion scores."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "pairwise_preference",
    "Choose a winner.",
    lambda i, t: {"winner": "tie", "rationale": t, "confidence": 0.0},
    convention="a/b/criterion -> winner/rationale via ctx.llm",
)
