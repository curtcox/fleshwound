"""Built-in catalog kind: diff_writer."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "diff_writer",
    "Write a unified diff.",
    lambda i, t: {"diff": t, "format": "unified"},
)
