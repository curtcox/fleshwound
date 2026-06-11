"""Built-in catalog kind: conversation."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "conversation",
    "Continue the conversation.",
    lambda i, t: {"reply": t, "turns": list(i.get("turns", [])) + [{"role": "assistant", "content": t}]},
)
