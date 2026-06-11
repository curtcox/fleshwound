"""Built-in catalog kind: failure_classifier."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "failure_classifier",
    "Classify failure.",
    lambda i, t: {"category": "ok", "subcategory": "", "evidence": t},
)
