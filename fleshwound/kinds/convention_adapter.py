"""Built-in catalog kind: convention_adapter.

LLM translates a ``source_value`` from one kind's convention into ``target_input``
for another kind, flagging lossiness.

When to use: composing pipelines where adjacent kinds disagree on JSON shapes.

Similar kinds: ``chain_with_adapter``; ``transformer``; ``monty_exec``.

Prefer alternatives when: use ``transformer`` for deterministic mapping; use
``monty_exec`` for hand-written transforms."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "convention_adapter",
    "Adapt one kind's output to another kind's input.",
    lambda i, t: {"target_input": i.get("source_value"), "lossy": False, "notes": t},
    convention="source_kind/target_kind/source_value -> target_input via ctx.llm",
)
