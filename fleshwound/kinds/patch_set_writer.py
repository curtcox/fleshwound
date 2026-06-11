"""Built-in catalog kind: patch_set_writer.

One LLM call returns a list of ``{path, diff}`` patches for multiple files.

When to use: batch edit planning across a virtual file set.

Similar kinds: ``diff_writer``; ``directory_writer``; ``patch_applier_proxy``.

Prefer alternatives when: use ``diff_writer`` for one file; use ``repo_walker`` when
each file needs different processing."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "patch_set_writer",
    "Write patch set JSON.",
    lambda i, t: {"patches": []},
    convention="files/task -> patch list via ctx.llm",
)
