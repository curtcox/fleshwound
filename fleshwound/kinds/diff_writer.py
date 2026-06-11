"""Built-in catalog kind: diff_writer.

One LLM call produces a unified diff for a single file given content and change
description.

When to use: single-file edit proposals applied outside the sandbox.

Similar kinds: ``patch_set_writer``; ``directory_writer``; ``patch_applier_proxy``.

Prefer alternatives when: use ``patch_set_writer`` for multi-file changes; use
``program_writer`` for executable code output."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "diff_writer",
    "Write a unified diff.",
    lambda i, t: {"diff": t, "format": "unified"},
    convention="file/content/change -> unified diff via ctx.llm",
)
