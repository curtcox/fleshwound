"""Built-in catalog kind: schema_designer."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "schema_designer",
    "Design a JSON schema.",
    lambda i, t: {"schema": {}, "rationale": t},
)
