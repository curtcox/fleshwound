"""Built-in catalog kind: conversation.

One LLM turn appends an assistant reply to caller-supplied ``turns`` (no hidden
host state).

When to use: chat steps where determinism requires full history in every input.

Similar kinds: ``prose_writer``; ``rlm_loop``; ``clarify_then_delegate``.

Prefer alternatives when: use ``prose_writer`` for one-shot text; use ``rlm_loop``
when step actions are needed between turns."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "conversation",
    "Continue the conversation.",
    lambda i, t: {"reply": t, "turns": list(i.get("turns", [])) + [{"role": "assistant", "content": t}]},
    convention="system/turns -> reply and appended turns via ctx.llm",
)
