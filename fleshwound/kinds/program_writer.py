"""Built-in catalog kind: program_writer."""

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

