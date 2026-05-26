"""Built-in Fleshwound catalog entries."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from ..catalog import register
from ..errors import HostError

RLM_ACTION_PROTOCOL = "fleshwound-rlm-action/1"
RLM_ACTIONS = {"answer", "step", "llm", "think", "fail"}


def _request(ctx: Any, parts: int = 1) -> dict[str, int]:
    snap = ctx.budget()
    steps = max(1, snap["steps_remaining"] // max(parts, 1))
    depth = max(1, snap["depth_remaining"] - 1)
    return {
        "tokens": max(0, snap["tokens_remaining"] // max(parts, 1)),
        "steps": steps,
        "depth": depth,
        "tool_calls": max(0, snap["tool_calls_remaining"] // max(parts, 1)),
    }


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
    strict: bool = False,
    budget: dict[str, Any] | None = None,
) -> str | None:
    if not isinstance(action, dict):
        return "action must be a JSON object"
    if strict and action.get("protocol") != RLM_ACTION_PROTOCOL:
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
        }
    except (TypeError, ValueError):
        return "step.request values must be integers"


def _request_over_budget(request: dict[str, int], budget: dict[str, Any]) -> str | None:
    if request["tokens"] < 0 or request["steps"] < 1 or request["depth"] < 1 or request["tool_calls"] < 0:
        return "step.request has invalid budget values"
    if request["tokens"] > int(budget["tokens_remaining"]):
        return "step.request exceeds available tokens"
    if request["steps"] > int(budget["steps_remaining"]):
        return "step.request exceeds available steps"
    if request["depth"] > int(budget["depth_remaining"]) - 1:
        return "step.request exceeds available depth"
    if request["tool_calls"] > int(budget["tool_calls_remaining"]):
        return "step.request exceeds available tool calls"
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
    strict = bool(input.get("strict_protocol", False))
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
        parse_error = _strict_rlm_text_error(model_text) if strict else None
        action = None
        if parse_error is None:
            action, parse_error = _parse_rlm_action(model_text)
        if parse_error:
            observation = {"type": "parse_error", "message": parse_error}
            action = None
        else:
            validation_error = _validate_rlm_action(action, strict=strict, budget=ctx.budget())
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


def _monty_run(code: str, input: Any, ctx: Any) -> Any:
    try:
        import pydantic_monty
    except ImportError as exc:
        raise RuntimeError("pydantic_monty is required for Monty-backed kinds") from exc

    m = pydantic_monty.Monty(code, inputs=["input"])
    complete = m.run(
        inputs={"input": input},
        external_functions={
            "llm": ctx.llm,
            "step": ctx.step,
            "ask_user": ctx.ask_user,
            "budget": ctx.budget,
            "catalog": lambda: dict(ctx.catalog),
        },
    )
    return getattr(complete, "output", complete)


@register("constant", convention="input.value -> value verbatim; host charges one step")
def constant(input: Any, ctx: Any) -> Any:
    return input["value"]


@register("echo", convention="input -> input verbatim; host charges one step")
def echo(input: Any, ctx: Any) -> Any:
    return input


@register("noop_fail", convention="always raises a host-Python exception")
def noop_fail(input: Any, ctx: Any) -> Any:
    raise RuntimeError("deliberate noop_fail")


@register("noop_fail_monty", convention="always raises inside Monty", monty=True)
def noop_fail_monty(input: Any, ctx: Any) -> Any:
    return _monty_run('raise Exception("deliberate noop_fail_monty")', input, ctx)


@register("prose_writer", convention="task/context -> {'text', 'notes'} using ctx.llm")
def prose_writer(input: dict[str, Any], ctx: Any) -> dict[str, str]:
    result = ctx.llm(f"Write prose for task: {input.get('task')}\nContext: {input.get('context')}")
    return {"text": result.get("text", ""), "notes": "model_error" if result["status"] == "error" else ""}


@register("classifier", convention="text/labels -> label/confidence/rationale using ctx.llm")
def classifier(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    labels = list(input.get("labels") or [])
    result = ctx.llm(f"Classify this text into one of {labels}: {input.get('text', '')}")
    text = result.get("text", "").strip()
    label = next((label for label in labels if re.search(rf"\b{re.escape(label)}\b", text, re.I)), None)
    return {"label": label or (labels[0] if labels else ""), "confidence": None, "rationale": text}


@register("ask_user_only", convention="question -> {'answer'} or unavailable note")
def ask_user_only(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    if ctx.ask_user is None:
        return {"answer": None, "notes": "ask_user unavailable"}
    return {"answer": ctx.ask_user(str(input.get("question", "")))}


@register("monty_exec", convention="code -> final Monty expression", monty=True)
def monty_exec(input: dict[str, Any], ctx: Any) -> Any:
    return _monty_run(str(input.get("code", "")), input, ctx)


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
    return _monty_run(code, input, ctx)


@register("map_reduce", convention="map items through map_kind; optional reduce_kind")
def map_reduce(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    items = list(input.get("items") or [])
    mapped, errors = [], []
    parts = len(items) + (1 if input.get("reduce_kind") else 0)
    for idx, item in enumerate(items):
        result = ctx.step(item, _request(ctx, parts), kind=input.get("map_kind"))
        mapped.append(result.get("value") if result["outcome"] == "ok" else None)
        if result["outcome"] != "ok":
            errors.append(idx)
    reduced = None
    if input.get("reduce_kind"):
        reduced_result = ctx.step(mapped, _request(ctx, parts), kind=input["reduce_kind"])
        reduced = reduced_result.get("value") if reduced_result["outcome"] == "ok" else None
    return {"mapped": mapped, "reduced": reduced, "errors": errors}


@register("retry_wrapper", convention="retry inner_kind until ok or max_attempts")
def retry_wrapper(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    max_attempts = max(0, int(input.get("max_attempts", 1)))
    last = None
    for attempt in range(max_attempts):
        last = ctx.step(input.get("inner_input"), _request(ctx, max_attempts - attempt), kind=input.get("inner_kind"))
        if last["outcome"] == "ok":
            return {"attempts": attempt + 1, "result": last}
    return {"attempts": max_attempts, "result": last}


@register("ensemble", convention="run inner_kind n times and aggregate with llm")
def ensemble(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    n = max(0, int(input.get("n", 1)))
    candidates = [ctx.step(input.get("inner_input"), _request(ctx, n + 1), kind=input.get("inner_kind")) for _ in range(n)]
    ok_values = [r["value"] for r in candidates if r["outcome"] == "ok"]
    chosen = ok_values[0] if ok_values else None
    if ok_values and input.get("aggregator_prompt"):
        result = ctx.llm(f"{input['aggregator_prompt']}\nCandidates: {json.dumps(ok_values, sort_keys=True)}")
        chosen = result.get("text") or chosen
    return {"chosen": chosen, "candidates": ok_values}


@register("judge", convention="candidate/criteria -> pass/fail/rationale")
def judge(input: dict[str, Any], ctx: Any) -> dict[str, str]:
    result = ctx.llm(f"Judge pass or fail.\nCriteria: {input.get('criteria')}\nCandidate: {input.get('candidate')}")
    text = result.get("text", "")
    return {"verdict": "pass" if "pass" in text.lower() else "fail", "rationale": text}


@register("clarify_then_delegate", convention="optionally ask then delegate")
def clarify_then_delegate(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    q = f"Clarify task: {input.get('task')}"
    a = ctx.ask_user(q) if ctx.ask_user else None
    result = ctx.step({"task": input.get("task"), "clarification": a}, _request(ctx), kind=input.get("child_kind"))
    return {"clarification_q": q if ctx.ask_user else None, "clarification_a": a, "result": result}


@register("random_pick", convention="delegate using random default policy")
def random_pick(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"result": ctx.step(input.get("inner_input"), _request(ctx), kind=None, default_policy="random")}


@register("subset_pick", convention="delegate using random_from_subset default policy")
def subset_pick(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"result": ctx.step(input.get("inner_input"), _request(ctx), kind=None, default_policy={"random_from_subset": input.get("subset", [])})}


@register("inherit_chain", convention="recursively calls same kind until depth expires")
def inherit_chain(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    depth = int(input.get("depth", 0))
    trace = [ctx.kind]
    if depth <= 0:
        return {"trace": trace}
    result = ctx.step({"task": input.get("task"), "depth": depth - 1}, _request(ctx), kind=None)
    if result["outcome"] == "ok":
        trace.extend(result["value"].get("trace", []))
    else:
        trace.append(result["host_error"]["code"])
    return {"trace": trace}


@register("always_host_error", convention="input.code triggers one host_error code")
def always_host_error(input: dict[str, Any], ctx: Any) -> Any:
    code = input.get("code")
    if code == "malformed_result":
        return object()
    if code in {
        "budget_exhausted",
        "budget_denied",
        "monty_error",
        "spawn_failed",
        "spawn_protocol_error",
        "unknown_kind",
        "unresolvable_default",
        "executor_error",
    }:
        raise HostError(code, f"forced {code}")
    raise RuntimeError(f"forced {code or 'executor_error'}")


@register("always_partial", convention="returns a deliberate partial value")
def always_partial(input: Any, ctx: Any) -> dict[str, str]:
    return {"status": "partial", "program": "", "notes": "deliberate partial for tests"}


@register("budget_hog", convention="burns target budget and observes exhaustion")
def budget_hog(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    target = input.get("target")
    if target == "tokens":
        ctx.llm("x " * (ctx.budget()["tokens_remaining"] + 1))
    elif target == "tool_calls":
        ctx.ledger.charge_tool_call(ctx.budget_id, "budget_hog")
    elif target == "steps":
        result = ctx.step({}, {"tokens": 0, "steps": ctx.budget()["steps_remaining"] + 1, "depth": 1, "tool_calls": 0}, kind="echo")
        return {"target": target, "result": result}
    return {"target": target, "budget": ctx.budget()}


@register("infinite_descent", convention="descends until child allocation is denied")
def infinite_descent(input: Any, ctx: Any) -> dict[str, Any]:
    result = ctx.step({}, _request(ctx), kind="infinite_descent")
    return {"result": result}


@register("provider_swap", convention="delegates with supplied provider object if present")
def provider_swap(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    provider = input.get("inner_provider") or ctx.provider
    return {"result": ctx.step(input.get("inner_input"), _request(ctx), kind=input.get("inner_kind"), provider=provider)}


@register("dynamic_dispatch", convention="choose kind literally or by llm then delegate")
def dynamic_dispatch(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    chosen = input.get("literal_kind")
    if input.get("chooser") == "llm":
        chosen = ctx.llm(f"Choose one kind from {sorted(ctx.catalog)} for {input.get('task_for_chooser')}").get("text", "").strip()
    return {"chosen_kind": chosen, "result": ctx.step(input.get("inner_input"), _request(ctx), kind=chosen)}


@register("cond_dispatch", convention="first true Monty predicate dispatches")
def cond_dispatch(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    chosen = input.get("default_kind")
    for branch in input.get("branches", []):
        if _monty_run(str(branch.get("when", "False")), input.get("inner_input"), ctx):
            chosen = branch.get("kind")
            break
    return {"chosen_kind": chosen, "result": ctx.step(input.get("inner_input"), _request(ctx), kind=chosen)}


@register("cascade", convention="try kinds in order until one succeeds")
def cascade(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    tried = []
    result = None
    stop_predicate = input.get("stop_predicate")
    for kind in input.get("kinds", []):
        tried.append(kind)
        result = ctx.step(input.get("inner_input"), _request(ctx, len(input.get("kinds", [])) or 1), kind=kind)
        if result["outcome"] != "ok":
            continue
        if not stop_predicate or _monty_run(str(stop_predicate), result.get("value"), ctx):
            return {"chosen_kind": kind, "result": result, "tried": tried}
    return {"chosen_kind": None, "result": result, "tried": tried}


@register("kind_lister", convention="{} -> catalog names and conventions")
def kind_lister(input: Any, ctx: Any) -> dict[str, Any]:
    return {"kinds": [{"name": name, "convention": convention} for name, convention in sorted(ctx.catalog.items())]}


@register("score_aggregator", convention="aggregate scores by weighted_mean, median, or min")
def score_aggregator(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    scores = list(input.get("scores") or [])
    values = [float(s.get("score", 0)) for s in scores]
    policy = input.get("policy", "weighted_mean")
    if not values:
        aggregate = 0.0
    elif policy == "min":
        aggregate = min(values)
    elif policy == "median":
        aggregate = sorted(values)[len(values) // 2]
    else:
        total_w = sum(float(s.get("weight", 1)) for s in scores) or 1.0
        aggregate = sum(float(s.get("score", 0)) * float(s.get("weight", 1)) for s in scores) / total_w
    return {"aggregate": aggregate, "n": len(values)}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@register("content_hash_memo", convention="explicit input/output memoization")
def content_hash_memo(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    key = _hash({"kind": input.get("inner_kind"), "input": input.get("inner_input")})
    memo = dict(input.get("memo") or {})
    if key in memo:
        return {"hash": key, "value": memo[key], "hit": True, "memo": memo}
    result = ctx.step(input.get("inner_input"), _request(ctx), kind=input.get("inner_kind"))
    value = result.get("value") if result["outcome"] == "ok" else result
    memo[key] = value
    return {"hash": key, "value": value, "hit": False, "memo": memo}


@register("dedup_then_map", convention="run inner_kind once per unique item hash")
def dedup_then_map(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    items = list(input.get("items") or [])
    item_hashes = [_hash(item) for item in items]
    results = {}
    for item_hash, item in zip(item_hashes, items):
        if item_hash not in results:
            results[item_hash] = ctx.step(item, _request(ctx, len(set(item_hashes)) or 1), kind=input.get("inner_kind"))
    return {"results_by_hash": results, "items_to_hash": item_hashes}


def _llm_json_kind(name: str, prompt: str, fallback: Any):
    @register(name, convention=f"LLM-backed structured kind {name}")
    def executor(input: Any, ctx: Any) -> Any:
        text = ctx.llm(f"{prompt}\nInput: {json.dumps(input, sort_keys=True)}").get("text", "")
        try:
            return json.loads(text)
        except Exception:
            return fallback(input, text)
    return executor


_llm_json_kind("schema_designer", "Design a JSON schema.", lambda i, t: {"schema": {}, "rationale": t})
_llm_json_kind("diff_writer", "Write a unified diff.", lambda i, t: {"diff": t, "format": "unified"})
_llm_json_kind("patch_set_writer", "Write patch set JSON.", lambda i, t: {"patches": []})
_llm_json_kind("directory_writer", "Write a virtual directory tree.", lambda i, t: {"tree": {}, "notes": t})
_llm_json_kind("conversation", "Continue the conversation.", lambda i, t: {"reply": t, "turns": list(i.get("turns", [])) + [{"role": "assistant", "content": t}]})
_llm_json_kind("rubric_grader", "Grade using the rubric.", lambda i, t: {"scores": [], "weighted_total": 0, "notes": t})
_llm_json_kind("pairwise_preference", "Choose a winner.", lambda i, t: {"winner": "tie", "rationale": t, "confidence": 0.0})
_llm_json_kind("attack_generator", "Generate an adversarial input.", lambda i, t: {"crafted_input": i.get("target_input_template", {}), "rationale": t})
_llm_json_kind("failure_classifier", "Classify failure.", lambda i, t: {"category": "ok", "subcategory": "", "evidence": t})
_llm_json_kind("convention_adapter", "Adapt one kind's output to another kind's input.", lambda i, t: {"target_input": i.get("source_value"), "lossy": False, "notes": t})


@register("kind_chooser", convention="task -> chosen_kind/rationale using catalog-grounded llm")
def kind_chooser(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    catalog_doc = json.dumps(dict(sorted(ctx.catalog.items())), sort_keys=True)
    text = ctx.llm(f"Choose a catalog kind for this task.\nCatalog: {catalog_doc}\nTask: {input.get('task')}").get("text", "")
    try:
        return json.loads(text)
    except Exception:
        return {"chosen_kind": text.strip(), "rationale": text}


@register("function_map_writer", convention="write functions for signatures")
def function_map_writer(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    functions = {}
    for name, spec in (input.get("signatures") or {}).items():
        result = ctx.step({"task": f"Write {spec}", "context": input.get("context")}, _request(ctx), kind="program_writer")
        if result["outcome"] == "ok":
            functions[name] = {"source": result["value"].get("program", ""), "notes": result["value"].get("notes", "")}
    return {"functions": functions, "missing": [name for name in (input.get("signatures") or {}) if name not in functions]}


@register("function_map_editor", convention="edit function map data")
def function_map_editor(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    updated = dict(input.get("current") or {})
    removed, added = [], []
    for edit in input.get("edits", []):
        name = edit.get("name")
        if edit.get("instruction") == "remove" and name in updated:
            removed.append(name)
            updated.pop(name)
        elif name:
            added.append(name) if name not in updated else None
            updated[name] = {"source": edit.get("instruction", updated.get(name, {}).get("source", ""))}
    return {"updated": updated, "removed": removed, "added": added}


@register("ast_transform", convention="return transformed AST data")
def ast_transform(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    return {"ast": input.get("ast", {}), "changes": [str(input.get("transform", ""))]}


@register("directory_input", convention="delegate virtual tree task to program_writer")
def directory_input(input: dict[str, Any], ctx: Any) -> Any:
    return ctx.step({"task": input.get("task"), "context": {"tree": input.get("tree")}}, _request(ctx), kind="program_writer")


@register("repo_walker", convention="run per_file_kind for matching virtual files")
def repo_walker(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    tree = input.get("tree") or {}
    predicate = str(input.get("predicate", "True"))
    matching: list[tuple[str, Any]] = []
    skipped = []
    for path, data in tree.items():
        child_input = {"path": path, "data": data}
        try:
            include = bool(_monty_run(predicate, child_input, ctx))
        except Exception:
            skipped.append({"path": path, "reason": "predicate_error"})
            continue
        if include:
            matching.append((path, data))
        else:
            skipped.append({"path": path, "reason": "predicate_false"})

    per_file = {}
    for path, data in matching:
        per_file[path] = ctx.step({"path": path, "data": data}, _request(ctx, len(matching) or 1), kind=input.get("per_file_kind"))
    result = {"per_file": per_file}
    if skipped:
        result["skipped"] = skipped
    return result


@register("patch_applier_proxy", convention="pure-data patch apply simulation")
def patch_applier_proxy(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    applied = []
    rejected = []
    for patch in input.get("patches", []):
        path = patch.get("path", "")
        diff = patch.get("diff", "")
        if not path:
            rejected.append({"path": path, "reason": "missing path"})
        elif not diff:
            rejected.append({"path": path, "reason": "missing diff"})
        else:
            applied.append(path)
    return {"applied": applied, "rejected": rejected}


@register("pipeline", convention="sequential stage composition")
def pipeline(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    current = input.get("initial")
    stages = []
    for stage in input.get("stages", []):
        result = ctx.step(current, _request(ctx), kind=stage.get("kind"))
        stages.append(result)
        if result["outcome"] == "ok":
            current = result["value"]
    return {"stages": stages, "final": current}


@register("precondition_gate", convention="predicate-gated delegation")
def precondition_gate(input: dict[str, Any], ctx: Any) -> Any:
    ok = bool(_monty_run(str(input.get("predicate", "False")), input.get("inner_input"), ctx))
    if not ok:
        return {"gated": True, "reason": "predicate false"}
    return ctx.step(input.get("inner_input"), _request(ctx), kind=input.get("inner_kind"))


@register("transformer", convention="preprocess/delegate/postprocess wrapper")
def transformer(input: dict[str, Any], ctx: Any) -> Any:
    inner_input = input.get("inner_input_template")
    if input.get("preprocess"):
        inner_input = _monty_run(input["preprocess"], inner_input, ctx)
    result = ctx.step(inner_input, _request(ctx), kind=input.get("inner_kind"))
    if input.get("postprocess"):
        return _monty_run(input["postprocess"], result, ctx)
    return result


@register("meta_planner", convention="LLM JSON plan then sequential execution")
def meta_planner(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    text = ctx.llm(f"Plan task with catalog {sorted(ctx.catalog)}: {input.get('task')}").get("text", "[]")
    try:
        plan = json.loads(text)
    except Exception:
        plan = []
    results = [ctx.step(item.get("input"), _request(ctx, len(plan) or 1), kind=item.get("kind")) for item in plan]
    return {"plan": plan, "results": results}


@register("catalog_self_test", convention="run minimal inputs for listed kinds")
def catalog_self_test(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    names = input.get("kinds_to_exercise") or sorted(ctx.catalog)
    results = []
    expected_failure_kinds = {"always_host_error", "budget_hog", "infinite_descent", "noop_fail", "noop_fail_monty"}
    for name in names:
        if name == "catalog_self_test":
            continue
        result = ctx.step(_minimal_input(name), _request(ctx, len(names) or 1), kind=name)
        expected_host_error = name in expected_failure_kinds
        unexpected = result["outcome"] == "host_error" and not expected_host_error
        results.append(
            {
                "kind": name,
                "outcome": result["outcome"],
                "host_error": result.get("host_error"),
                "expected_host_error": expected_host_error,
                "unexpected_host_error": unexpected,
            }
        )
    return {"results": results, "unexpected_host_errors": [row for row in results if row["unexpected_host_error"]]}


def _minimal_input(name: str) -> Any:
    return {
        "constant": {"value": None},
        "ask_user_only": {"question": "?"},
        "monty_exec": {"code": "input"},
        "prose_writer": {"task": "test", "context": None},
        "classifier": {"text": "a", "labels": ["a"]},
        "judge": {"candidate": "x", "criteria": "ok"},
        "program_writer": {"task": "return ok", "context": None, "output_schema": {}},
        "map_reduce": {"items": [], "map_kind": "echo", "reduce_kind": None},
        "retry_wrapper": {"inner_input": {"value": 1}, "inner_kind": "constant", "max_attempts": 1},
        "ensemble": {"inner_input": {"value": 1}, "inner_kind": "constant", "n": 0, "aggregator_prompt": ""},
        "clarify_then_delegate": {"task": "x", "child_kind": "echo"},
        "random_pick": {"inner_input": {}},
        "subset_pick": {"inner_input": {"value": 1}, "subset": ["constant"]},
        "inherit_chain": {"task": "x", "depth": 0},
        "always_host_error": {"code": "executor_error"},
        "budget_hog": {"target": "steps"},
        "provider_swap": {"inner_input": {"value": 1}, "inner_kind": "constant"},
        "dynamic_dispatch": {"chooser": "literal", "literal_kind": "constant", "inner_input": {"value": 1}},
        "cond_dispatch": {"branches": [], "default_kind": "constant", "inner_input": {"value": 1}},
        "cascade": {"inner_input": {"value": 1}, "kinds": ["constant"], "stop_predicate": "True"},
        "score_aggregator": {"scores": [], "policy": "weighted_mean"},
        "content_hash_memo": {"inner_kind": "constant", "inner_input": {"value": 1}, "memo": {}},
        "dedup_then_map": {"items": [], "inner_kind": "echo"},
        "schema_designer": {"domain": "test", "examples": []},
        "diff_writer": {"file": "a.txt", "content": "", "change": "none"},
        "patch_set_writer": {"files": {}, "task": "none"},
        "directory_writer": {"task": "empty tree", "shape": "tree"},
        "conversation": {"system": "s", "turns": []},
        "kind_chooser": {"task": "return input"},
        "rubric_grader": {"candidate": "x", "rubric": []},
        "pairwise_preference": {"a": 1, "b": 2, "criterion": "best"},
        "attack_generator": {"target_kind": "echo", "target_input_template": {}, "attack_goal": "none"},
        "failure_classifier": {"step_result": {"outcome": "ok", "value": 1, "host_error": None}},
        "convention_adapter": {"source_kind": "echo", "target_kind": "echo", "source_value": {"value": 1}},
        "function_map_writer": {"signatures": {}, "context": None},
        "function_map_editor": {"current": {}, "edits": []},
        "ast_transform": {"ast": {}, "transform": "none"},
        "directory_input": {"tree": {}, "task": "return empty"},
        "repo_walker": {"tree": {}, "per_file_kind": "echo", "predicate": "True"},
        "patch_applier_proxy": {"patches": []},
        "pipeline": {"stages": [], "initial": None},
        "precondition_gate": {"predicate": "False", "inner_kind": "echo", "inner_input": {}},
        "transformer": {"inner_input_template": {"value": 1}, "inner_kind": "constant"},
        "meta_planner": {"task": "do nothing"},
        "refine_until": {"inner_input": {"value": "ok"}, "inner_kind": "constant", "judge_kind": "judge", "max_rounds": 0},
        "tournament": {"candidates": [], "judge_kind": "pairwise_preference"},
        "calibration": {"grader_kind": "rubric_grader", "examples": []},
        "adversarial_loop": {"target_kind": "echo", "seed_input": {}, "max_rounds": 0, "success_predicate": "none"},
        "regression_canary": {"frozen_kind": "constant", "frozen_input": {"value": 1}, "expected_value_hash": _hash(1)},
        "chain_with_adapter": {"first_kind": "constant", "first_input": {"value": {"value": 1}}, "second_kind": "constant"},
        "kind_lister": {},
        "always_partial": {},
        "rlm_loop": {"task": "return ok", "max_iterations": 1},
    }.get(name, {})


@register("refine_until", convention="iterative refine/judge loop")
def refine_until(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    history = []
    final = None
    for _ in range(max(0, int(input.get("max_rounds", 1)))):
        candidate = ctx.step(input.get("inner_input"), _request(ctx), kind=input.get("inner_kind"))
        verdict = ctx.step(candidate, _request(ctx), kind=input.get("judge_kind"))
        history.append({"candidate": candidate, "verdict": verdict})
        final = candidate.get("value")
        if verdict["outcome"] == "ok" and "pass" in json.dumps(verdict["value"]).lower():
            break
    return {"rounds": len(history), "history": history, "final": final}


@register("tournament", convention="pairwise preference bracket")
def tournament(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    candidates = list(input.get("candidates") or [])
    bracket = []
    while len(candidates) > 1:
        a, b, *rest = candidates
        result = ctx.step({"a": a, "b": b, "criterion": "best"}, _request(ctx), kind=input.get("judge_kind"))
        winner = a if result["outcome"] != "ok" or result["value"].get("winner") != "b" else b
        bracket.append({"a": a, "b": b, "result": result})
        candidates = [winner] + rest
    return {"winner": candidates[0] if candidates else None, "bracket": bracket}


@register("calibration", convention="compare grader outputs to gold scores")
def calibration(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    per = []
    for example in input.get("examples", []):
        result = ctx.step(example.get("item"), _request(ctx), kind=input.get("grader_kind"))
        predicted = result.get("value", {}).get("weighted_total", 0) if result["outcome"] == "ok" else 0
        per.append({"predicted": predicted, "gold": example.get("gold_score", 0)})
    agreement = sum(1 for row in per if row["predicted"] == row["gold"]) / (len(per) or 1)
    return {"agreement": agreement, "per_example": per, "bias": 0.0}


@register("adversarial_loop", convention="attack target repeatedly")
def adversarial_loop(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    history = []
    current = input.get("seed_input")
    winning = None
    for _ in range(max(0, int(input.get("max_rounds", 1)))):
        attack = ctx.step({"target_kind": input.get("target_kind"), "target_input_template": current, "attack_goal": input.get("success_predicate")}, _request(ctx), kind="attack_generator")
        current = attack.get("value", {}).get("crafted_input", current) if attack["outcome"] == "ok" else current
        target = ctx.step(current, _request(ctx), kind=input.get("target_kind"))
        successful = target["outcome"] == "host_error"
        history.append({"input": current, "target_result": target, "successful": successful})
        if successful:
            winning = current
            break
    return {"rounds": len(history), "history": history, "winning_input": winning}


@register("regression_canary", convention="hash child value and compare to expected")
def regression_canary(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    result = ctx.step(input.get("frozen_input"), _request(ctx), kind=input.get("frozen_kind"))
    actual = _hash(result.get("value")) if result["outcome"] == "ok" else _hash(result)
    return {"passed": actual == input.get("expected_value_hash"), "actual_hash": actual, "result": result}


@register("chain_with_adapter", convention="first -> adapter -> second")
def chain_with_adapter(input: dict[str, Any], ctx: Any) -> dict[str, Any]:
    first = ctx.step(input.get("first_input"), _request(ctx), kind=input.get("first_kind"))
    adapted = ctx.step({"source_kind": input.get("first_kind"), "target_kind": input.get("second_kind"), "source_value": first.get("value")}, _request(ctx), kind="convention_adapter")
    second_input = adapted.get("value", {}).get("target_input") if adapted["outcome"] == "ok" else None
    second = ctx.step(second_input, _request(ctx), kind=input.get("second_kind"))
    return {"first_result": first, "adapted_input": second_input, "second_result": second}
