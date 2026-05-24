"""Minimal Fleshwound step runner.

Loads the step system prompt, asks an LLM for Monty-subset Python that
produces the step's output dict, and executes that code inside
pydantic-monty with the host tools (`llm`, `step`, `ask_user`, `budget`)
exposed as external functions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import pydantic_monty

STEP_PROMPT_PATH = Path(__file__).resolve().parent.parent / "Recursive_step_prompt.md"


def _load_step_prompt() -> str:
    return STEP_PROMPT_PATH.read_text()


def _strip_code_fence(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else text


def run_step(
    task: str,
    llm: Callable[[str], str],
    context: dict | None = None,
    output_schema: dict | None = None,
    token_budget: int = 100_000,
    depth_remaining: int = 3,
) -> dict[str, Any]:
    """Run one Fleshwound step. Returns the step's output dict."""

    system = _load_step_prompt()
    user_msg = (
        f"task = {task!r}\n"
        f"context = {context!r}\n"
        f"output_schema = {output_schema!r}\n"
        "\nProduce your Monty-subset Python now. The value of the final "
        "expression must be the output dict."
    )

    raw = llm(system + "\n\n---\n\n" + user_msg)
    code = _strip_code_fence(raw).strip()

    budget_state = {
        "tokens_remaining": token_budget,
        "depth_remaining": depth_remaining,
    }

    def host_llm(prompt: str) -> str:
        budget_state["tokens_remaining"] -= 1000
        return llm(prompt)

    def host_step(sub_input: dict, request: int) -> dict:
        if budget_state["depth_remaining"] <= 0:
            return {"status": "partial", "program": "", "notes": "depth exhausted"}
        budget_state["tokens_remaining"] -= request
        return run_step(
            task=sub_input.get("task", ""),
            llm=llm,
            context=sub_input.get("context"),
            output_schema=sub_input.get("output_schema"),
            token_budget=request,
            depth_remaining=budget_state["depth_remaining"] - 1,
        )

    def host_ask_user(question: str) -> str:
        raise RuntimeError(
            f"ask_user is not available in this run; question was: {question!r}"
        )

    def host_budget() -> dict:
        return dict(budget_state)

    m = pydantic_monty.Monty(
        code,
        inputs=["task", "context", "output_schema"],
    )

    complete = m.run(
        inputs={"task": task, "context": context, "output_schema": output_schema},
        external_functions={
            "llm": host_llm,
            "step": host_step,
            "ask_user": host_ask_user,
            "budget": host_budget,
        },
    )

    # `run()` may return a MontyComplete or the raw output value depending on
    # the pydantic-monty build; accept both.
    result = getattr(complete, "output", complete)
    if not isinstance(result, dict):
        raise RuntimeError(
            f"step did not return a dict; got {type(result).__name__}: {result!r}"
        )
    return result
