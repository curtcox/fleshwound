"""Built-in catalog kind: program_writer.

LLM generates Monty-subset Python from a task, executes it via ``monty_run``, and
returns ``{status, program, notes}``. Prompt asset:
``program_writer_prompt.md``.

When to use: primary budget-bounded program-writing path on Monty.

Similar kinds: ``prose_writer``; ``monty_exec``; ``function_map_writer``;
``directory_input``; ``rlm_loop``.

Prefer alternatives when: use ``prose_writer`` for non-code; use ``monty_exec`` when
code is known; use ``function_map_writer`` for many functions; use ``rlm_loop`` for
multi-iteration agentic reasoning."""

from __future__ import annotations

import re
from pathlib import Path

from typing import Any

from ..catalog import register
from ._shared import monty_run

@register("program_writer", convention="task/context/output_schema -> status/program/notes")
def program_writer(input: dict[str, Any], ctx: Any) -> Any:
    prompt_path = Path(__file__).with_name("program_writer_prompt.md")
    prompt = prompt_path.read_text() if prompt_path.exists() else "Write Monty-subset Python."
    result = ctx.llm(
        f"{prompt}\n\ntask = {input.get('task')!r}\ncontext = {input.get('context')!r}\n"
        f"output_schema = {input.get('output_schema')!r}"
    )
    if result["status"] == "error":
        return {"status": "error", "program": "", "notes": result["error"]["message"], "error": result["error"]}
    text = result["text"]
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    code = (match.group(1) if match else text).strip()
    if not code:
        return {"status": "partial", "program": "", "notes": "empty model response"}
    return monty_run(code, input, ctx)

