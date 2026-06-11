"""Built-in catalog kind: rlm_loop and RLM action protocol helpers.

Iterative RLM agent: LLM cycles emit structured actions (``answer``, ``step``,
``llm``, ``think``, ``fail``), executed via ``ctx.step`` / ``ctx.llm`` with trace
and state in the value. Full spec: ``docs/specs/rlm-loop-kind.md``.

When to use: multi-iteration reasoning with inspectable traces and child delegation.

Similar kinds: ``meta_planner``; ``refine_until``; ``program_writer``;
``conversation``.

Prefer alternatives when: use ``meta_planner`` for one-shot plans; use
``refine_until`` for simple judge loops; use ``program_writer`` for one-shot code."""

from __future__ import annotations

import json
import re
from typing import Any

from ..catalog import register

RLM_ACTION_PROTOCOL = "fleshwound-rlm-action/1"
RLM_ACTIONS = {"answer", "step", "llm", "think", "fail"}

def _is_jsonable(value: Any) -> bool:
    try:
        json.dumps(value, sort_keys=True)
    except (TypeError, ValueError):
        return False
    return True


def _json_object_candidates(text: str) -> list[str]:
    fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fenced:
        return fenced

    candidates = [text.strip()]
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            _, end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        candidates.append(text[match.start() : match.start() + end])
    return candidates


def _parse_rlm_action(text: str) -> tuple[dict[str, Any] | None, str | None]:
    first_object: dict[str, Any] | None = None
    for candidate in _json_object_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            first_object = first_object or parsed
            if "action" in parsed:
                return parsed, None
    if first_object is not None:
        return first_object, None
    return None, "model output did not contain a valid JSON object action"


def _strict_rlm_text_error(text: str) -> str | None:
    stripped = text.strip()
    for candidate in re.findall(r"```(?:json)?\s*(.*?)\s*```", text, re.S):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "action" in parsed:
            return None
    if stripped.startswith("```"):
        return None
    try:
        _, end = json.JSONDecoder().raw_decode(stripped)
    except json.JSONDecodeError:
        return "strict protocol requires a single JSON object or fenced JSON block"
    if stripped[end:].strip():
        return "strict protocol rejects prose outside the JSON action"
    return None


def _validate_rlm_action(
    action: dict[str, Any] | None,
    *,
    budget: dict[str, Any] | None = None,
) -> str | None:
    if not isinstance(action, dict):
        return "action must be a JSON object"
    if action.get("protocol") != RLM_ACTION_PROTOCOL:
        return f"protocol must be {RLM_ACTION_PROTOCOL!r}"

    action_name = action.get("action")
    if action_name not in RLM_ACTIONS:
        return f"unknown action: {action_name!r}"

    assign = action.get("assign")
    if assign is not None and not (isinstance(assign, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", assign)):
        return "assign must be a safe variable key"

    if action_name == "step":
        kind = action.get("kind")
        if kind is not None and not isinstance(kind, str):
            return "step.kind must be a string"
        if "input" in action and not _is_jsonable(action.get("input")):
            return "step.input must be JSON-serializable"
        request = action.get("request")
        if request is not None:
            if not isinstance(request, dict):
                return "step.request must be an object"
            normalized = _normalize_budget_request(request)
            if isinstance(normalized, str):
                return normalized
            if budget is not None:
                over = _request_over_budget(normalized, budget)
                if over is not None:
                    return over

    if action_name == "llm" and not isinstance(action.get("prompt"), str):
        return "llm.prompt must be a string"

    return None


def _normalize_budget_request(value: dict[str, Any]) -> dict[str, int] | str:
    try:
        return {
            "tokens": int(value.get("tokens", 0)),
            "steps": int(value.get("steps", 0)),
            "depth": int(value.get("depth", 0)),
            "tool_calls": int(value.get("tool_calls", 0)),
            "compute": int(value.get("compute", 0)),
        }
    except (TypeError, ValueError):
        return "step.request values must be integers"


def _request_over_budget(request: dict[str, int], budget: dict[str, Any]) -> str | None:
    if (
        request["tokens"] < 0
        or request["steps"] < 1
        or request["depth"] < 1
        or request["tool_calls"] < 0
        or request["compute"] < 0
    ):
        return "step.request has invalid budget values"
    if request["tokens"] > int(budget["tokens_remaining"]):
        return "step.request exceeds available tokens"
    if request["steps"] > int(budget["steps_remaining"]):
        return "step.request exceeds available steps"
    if request["depth"] > int(budget["depth_remaining"]) - 1:
        return "step.request exceeds available depth"
    if request["tool_calls"] > int(budget["tool_calls_remaining"]):
        return "step.request exceeds available tool calls"
    if request["compute"] > int(budget["compute_remaining"]):
        return "step.request exceeds available compute"
    return None


def _default_child_request(ctx: Any, input: dict[str, Any]) -> dict[str, int] | None:
    snap = ctx.budget()
    if int(snap["depth_remaining"]) <= 1:
        return None
    requested = dict(input.get("child_request") or {})
    return {
        "tokens": min(int(requested.get("tokens", int(snap["tokens_remaining"]) // 2)), int(snap["tokens_remaining"])),
        "steps": max(1, min(int(requested.get("steps", int(snap["steps_remaining"]) // 2)), int(snap["steps_remaining"]))),
        "depth": max(1, min(int(requested.get("depth", int(snap["depth_remaining"]) - 1)), int(snap["depth_remaining"]) - 1)),
        "tool_calls": min(
            int(requested.get("tool_calls", int(snap["tool_calls_remaining"]) // 2)),
            int(snap["tool_calls_remaining"]),
        ),
        "compute": min(
            int(requested.get("compute", int(snap["compute_remaining"]) // 2)),
            int(snap["compute_remaining"]),
        ),
    }


def _build_rlm_loop_prompt(task: str, state: dict[str, Any], ctx: Any, input: dict[str, Any], iteration: int) -> str:
    return (
        "You are controlling a Fleshwound RLM loop.\n"
        "Return exactly one JSON object and no prose.\n"
        f'The JSON object must match protocol: "{RLM_ACTION_PROTOCOL}".\n'
        "Allowed actions: answer, step, llm, think, fail.\n"
        'Examples: {"protocol":"fleshwound-rlm-action/1","action":"answer","value":{"ok":true}}\n'
        f"Available catalog: {json.dumps(dict(ctx.catalog), sort_keys=True)}\n"
        f"Current state: {json.dumps(state, sort_keys=True)}\n"
        f"Budget: {json.dumps(ctx.budget(), sort_keys=True)}\n"
        f"System hint: {input.get('system_hint', '')}\n"
        f"Answer schema: {json.dumps(input.get('answer_schema'), sort_keys=True)}\n"
        f"Task: {task}\n"
        f"iteration {iteration}"
    )


def _execute_rlm_action(
    action: dict[str, Any],
    root_input: dict[str, Any],
    ctx: Any,
    state: dict[str, Any],
) -> dict[str, Any]:
    action_name = action["action"]
    if action_name == "think":
        return {"type": "thought", "notes": str(action.get("notes", ""))}
    if action_name == "llm":
        result = ctx.llm(action["prompt"])
        observation = {"type": "llm_result", "result": result}
    elif action_name == "step":
        request = action.get("request")
        if request is None:
            request = _default_child_request(ctx, root_input)
            if request is None:
                return {"type": "budget_limit", "message": "depth remaining is too low for child step"}
        else:
            request = _normalize_budget_request(request)
            if isinstance(request, str):
                return {"type": "validation_error", "message": request}
        kind = action.get("kind") or root_input.get("child_kind")
        result = ctx.step(action.get("input", {}), request, kind=kind)
        observation = {"type": "step_result", "result": result}
    else:
        observation = {"type": action_name}

    assign = action.get("assign")
    if assign:
        state["vars"][assign] = observation.get("result", observation)
    return observation



@register("rlm_loop", convention="task/context -> answer via structured iterative llm+step recursion")
def rlm_loop(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    task = str(input.get("task", ""))
    max_iterations = max(0, int(input.get("max_iterations", 8)))
    trace: list[dict[str, Any]] = []
    state: dict[str, Any] = {"task": task, "context": input.get("context", {}), "vars": {}, "trace": trace}

    for iteration in range(1, max_iterations + 1):
        result = ctx.llm(_build_rlm_loop_prompt(task, state, ctx, input, iteration))
        if result["status"] == "error":
            return {
                "status": "partial",
                "answer": None,
                "iterations": iteration - 1,
                "trace": trace,
                "state": state,
                "notes": "llm error: " + result["error"]["message"],
            }

        model_text = result.get("text", "")
        parse_error = _strict_rlm_text_error(model_text)
        action = None
        if parse_error is None:
            action, parse_error = _parse_rlm_action(model_text)
        if parse_error:
            observation = {"type": "parse_error", "message": parse_error}
            action = None
        else:
            validation_error = _validate_rlm_action(action, budget=ctx.budget())
            observation = (
                {"type": "validation_error", "message": validation_error}
                if validation_error
                else _execute_rlm_action(action or {}, input, ctx, state)
            )

        trace.append(
            {
                "iteration": iteration,
                "model_text": model_text,
                "action": action,
                "observation": observation,
            }
        )

        if action and observation.get("type") not in {"validation_error", "parse_error"}:
            if action.get("action") == "answer":
                return {
                    "status": "complete",
                    "answer": action.get("value"),
                    "iterations": iteration,
                    "trace": trace,
                    "state": state,
                    "notes": str(action.get("notes", "")),
                }
            if action.get("action") == "fail":
                return {
                    "status": "error",
                    "answer": None,
                    "iterations": iteration,
                    "trace": trace,
                    "state": state,
                    "notes": str(action.get("message", "rlm loop failed")),
                }

    return {
        "status": "partial",
        "answer": None,
        "iterations": max_iterations,
        "trace": trace,
        "state": state,
        "notes": "max_iterations reached",
    }

