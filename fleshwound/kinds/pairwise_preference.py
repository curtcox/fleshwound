"""Built-in catalog kind: pairwise_preference."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "pairwise_preference",
    "Choose a winner.",
    lambda i, t: {"winner": "tie", "rationale": t, "confidence": 0.0},
)
