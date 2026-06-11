"""Built-in catalog kind: schema_designer.

One LLM call proposes a JSON Schema document plus rationale for a domain.

When to use: upfront schema design before structured outputs or ``program_writer``.

Similar kinds: ``prose_writer``; ``classifier``; ``ast_transform``.

Prefer alternatives when: use ``prose_writer`` when formal schema is unnecessary;
hand-author schema when shape is already known."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "schema_designer",
    "Design a JSON schema.",
    lambda i, t: {"schema": {}, "rationale": t},
    convention="domain/examples -> JSON schema/rationale via ctx.llm",
)
