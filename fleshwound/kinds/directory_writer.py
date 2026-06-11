"""Built-in catalog kind: directory_writer.

One LLM call generates a virtual directory ``tree`` plus notes from a task.

When to use: greenfield scaffold generation persisted by the caller.

Similar kinds: ``directory_input``; ``patch_set_writer``; ``function_map_writer``.

Prefer alternatives when: use ``patch_set_writer`` to modify existing paths; use
``directory_input`` when code must run in-process."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "directory_writer",
    "Write a virtual directory tree.",
    lambda i, t: {"tree": {}, "notes": t},
    convention="task/shape -> virtual tree/notes via ctx.llm",
)
