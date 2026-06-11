from __future__ import annotations
import json
from fleshwound.kinds.rlm_loop import _parse_rlm_action, _validate_rlm_action
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._fake_provider import FakeProvider, text_result


def test_parse_rlm_action_accepts_pure_json_action():
    action, error = _parse_rlm_action(
        '{"protocol":"fleshwound-rlm-action/1","action":"answer","value":"ok"}'
    )
    assert error is None
    assert action == {
        "protocol": "fleshwound-rlm-action/1",
        "action": "answer",
        "value": "ok",
    }


def test_parse_rlm_action_accepts_fenced_json():
    action, error = _parse_rlm_action(
        '```json\n{"protocol":"fleshwound-rlm-action/1","action":"answer","value":"ok"}\n```'
    )
    assert error is None
    assert action is not None
    assert action["action"] == "answer"


def test_parse_rlm_action_accepts_fenced_json_with_nested_value():
    action, error = _parse_rlm_action(
        '```json\n{"protocol":"fleshwound-rlm-action/1","action":"answer","value":{"ok":true}}\n```'
    )
    assert error is None
    assert action == {
        "protocol": "fleshwound-rlm-action/1",
        "action": "answer",
        "value": {"ok": True},
    }


def test_parse_rlm_action_uses_first_action_shaped_json_object():
    action, error = _parse_rlm_action(
        'metadata: {"ignored": true}\naction: {"protocol":"fleshwound-rlm-action/1","action":"answer","value":"ok"}'
    )
    assert error is None
    assert action is not None
    assert action["action"] == "answer"


def test_validate_rlm_action_rejects_unknown_action():
    error = _validate_rlm_action(
        {"protocol": "fleshwound-rlm-action/1", "action": "delete_everything"}
    )
    assert error is not None
    assert "unknown action" in error


def test_rlm_loop_assigns_step_result_to_vars():
    fake = FakeProvider(
        {
            "iteration 1": text_result(
                json.dumps(
                    {
                        "protocol": "fleshwound-rlm-action/1",
                        "action": "step",
                        "kind": "constant",
                        "input": {"value": 7},
                        "assign": "x",
                    }
                )
            ),
            "iteration 2": text_result(
                json.dumps(
                    {
                        "protocol": "fleshwound-rlm-action/1",
                        "action": "answer",
                        "value": {"done": True},
                    }
                )
            ),
        }
    )
    value = assert_ok(
        run_step(
            {"task": "assign", "max_iterations": 3},
            kind="rlm_loop",
            options=RunOptions(
                budget={"tokens": 200, "steps": 8, "depth": 3, "tool_calls": 0},
                provider=fake,
            ),
        )
    )
    assert value["status"] == "complete"
    assert value["state"]["vars"]["x"]["outcome"] == "ok"
    assert value["state"]["vars"]["x"]["value"] == 7


def test_rlm_loop_rejects_missing_protocol():
    fake = FakeProvider(
        {"iteration 1": text_result('{"action":"answer","value":"ok"}')}
    )
    value = assert_ok(
        run_step(
            {"task": "missing protocol", "max_iterations": 1},
            kind="rlm_loop",
            options=RunOptions(provider=fake),
        )
    )
    assert value["status"] == "partial"
    assert value["trace"][0]["observation"]["type"] == "validation_error"
    assert "protocol" in value["trace"][0]["observation"]["message"]


def test_rlm_loop_rejects_prose_wrapped_json():
    fake = FakeProvider(
        {
            "iteration 1": text_result(
                'Here is the action:\n{"protocol":"fleshwound-rlm-action/1","action":"answer","value":"ok"}'
            )
        }
    )
    value = assert_ok(
        run_step(
            {"task": "strict prose", "max_iterations": 1},
            kind="rlm_loop",
            options=RunOptions(provider=fake),
        )
    )
    assert value["status"] == "partial"
    assert value["trace"][0]["observation"]["type"] == "parse_error"


def test_rlm_loop_accepts_prose_wrapped_fenced_json():
    fake = FakeProvider(
        {
            "iteration 1": text_result(
                'Here is the action:\n```json\n{"protocol":"fleshwound-rlm-action/1","action":"answer","value":"ok"}\n```'
            )
        }
    )
    value = assert_ok(
        run_step(
            {"task": "strict fenced prose", "max_iterations": 1},
            kind="rlm_loop",
            options=RunOptions(provider=fake),
        )
    )
    assert value["status"] == "complete"
    assert value["answer"] == "ok"


def test_rlm_loop_rejects_explicit_over_budget_child_request():
    fake = FakeProvider(
        {
            "iteration 1": text_result(
                json.dumps(
                    {
                        "protocol": "fleshwound-rlm-action/1",
                        "action": "step",
                        "kind": "constant",
                        "input": {"value": 7},
                        "request": {
                            "tokens": 999,
                            "steps": 999,
                            "depth": 999,
                            "tool_calls": 999,
                        },
                    }
                )
            )
        }
    )
    value = assert_ok(
        run_step(
            {"task": "budget", "max_iterations": 1},
            kind="rlm_loop",
            options=RunOptions(
                budget={"tokens": 100, "steps": 4, "depth": 3, "tool_calls": 0},
                provider=fake,
            ),
        )
    )
    assert value["status"] == "partial"
    assert value["trace"][0]["observation"]["type"] == "validation_error"
