"""Built-in catalog kind: patch_set_writer."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "patch_set_writer",
    "Write patch set JSON.",
    lambda i, t: {"patches": []},
)
