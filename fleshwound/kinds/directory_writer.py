"""Built-in catalog kind: directory_writer."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "directory_writer",
    "Write a virtual directory tree.",
    lambda i, t: {"tree": {}, "notes": t},
)
