"""Built-in catalog kind: convention_adapter."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "convention_adapter",
    "Adapt one kind's output to another kind's input.",
    lambda i, t: {"target_input": i.get("source_value"), "lossy": False, "notes": t},
)
