"""Built-in catalog kind: attack_generator.

LLM crafts adversarial input for a target kind using its catalog convention and
an attack goal string.

When to use: red-team setup inside ``adversarial_loop`` or convention fuzzing.

Similar kinds: ``adversarial_loop``; ``failure_classifier``; ``noop_fail``.

Prefer alternatives when: use ``noop_fail`` for deterministic errors; use
``adversarial_loop`` for multi-round search."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "attack_generator",
    "Generate an adversarial input.",
    lambda i, t: {"crafted_input": i.get("target_input_template", {}), "rationale": t},
    convention="target_kind/goal -> crafted_input/rationale via ctx.llm",
)
