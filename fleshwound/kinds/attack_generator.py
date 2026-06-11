"""Built-in catalog kind: attack_generator."""

from __future__ import annotations

from ._llm_json import register_llm_json_kind

register_llm_json_kind(
    "attack_generator",
    "Generate an adversarial input.",
    lambda i, t: {"crafted_input": i.get("target_input_template", {}), "rationale": t},
)
