from __future__ import annotations
import json
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._fake_provider import FakeProvider, text_result


def _provider(*texts: str) -> FakeProvider:
    return FakeProvider(
        {
            f"iteration {idx}": text_result(text)
            for idx, text in enumerate(texts, start=1)
        }
    )


def test_rlm_loop_completes_with_direct_answer():
    fake = _provider(
        '{"protocol":"fleshwound-rlm-action/1","action":"answer","value":{"result":42}}'
    )
    value = assert_ok(
        run_step(
            {"task": "compute", "max_iterations": 3},
            kind="rlm_loop",
            options=RunOptions(provider=fake),
        )
    )
    assert value["status"] == "complete"
    assert value["answer"] == {"result": 42}
    assert value["iterations"] == 1
    assert value["trace"][0]["action"]["action"] == "answer"


def test_rlm_loop_delegates_to_child_step():
    fake = _provider(
        json.dumps(
            {
                "protocol": "fleshwound-rlm-action/1",
                "action": "step",
                "kind": "constant",
                "input": {"value": "child result"},
            }
        ),
        json.dumps(
            {"protocol": "fleshwound-rlm-action/1", "action": "answer", "value": "done"}
        ),
    )
    value = assert_ok(
        run_step(
            {
                "task": "delegate",
                "max_iterations": 4,
                "child_request": {
                    "tokens": 20,
                    "steps": 2,
                    "depth": 1,
                    "tool_calls": 0,
                },
            },
            kind="rlm_loop",
            options=RunOptions(
                budget={"tokens": 200, "steps": 8, "depth": 3, "tool_calls": 0},
                provider=fake,
            ),
        )
    )
    assert value["status"] == "complete"
    assert value["answer"] == "done"
    assert len(value["trace"]) == 2
    assert value["trace"][0]["observation"]["type"] == "step_result"
    assert value["trace"][0]["observation"]["result"]["outcome"] == "ok"
    assert value["trace"][0]["observation"]["result"]["value"] == "child result"


def test_rlm_loop_handles_unknown_child_kind_without_crashing():
    fake = _provider(
        json.dumps(
            {
                "protocol": "fleshwound-rlm-action/1",
                "action": "step",
                "kind": "missing_kind",
                "input": {},
            }
        ),
        json.dumps(
            {
                "protocol": "fleshwound-rlm-action/1",
                "action": "answer",
                "value": "recovered",
            }
        ),
    )
    value = assert_ok(
        run_step(
            {"task": "recover", "max_iterations": 3},
            kind="rlm_loop",
            options=RunOptions(provider=fake),
        )
    )
    assert value["status"] == "complete"
    assert value["trace"][0]["observation"]["type"] == "step_result"
    assert value["trace"][0]["observation"]["result"]["outcome"] == "host_error"
    assert (
        value["trace"][0]["observation"]["result"]["host_error"]["code"]
        == "unknown_kind"
    )


def test_rlm_loop_respects_max_iterations():
    fake = _provider(
        '{"protocol":"fleshwound-rlm-action/1","action":"think","notes":"continue"}',
        '{"protocol":"fleshwound-rlm-action/1","action":"think","notes":"continue"}',
    )
    value = assert_ok(
        run_step(
            {"task": "ponder", "max_iterations": 2},
            kind="rlm_loop",
            options=RunOptions(provider=fake),
        )
    )
    assert value["status"] == "partial"
    assert value["answer"] is None
    assert value["iterations"] == 2
    assert value["notes"] == "max_iterations reached"


def test_rlm_loop_handles_malformed_model_output():
    fake = _provider("not json")
    value = assert_ok(
        run_step(
            {"task": "bad", "max_iterations": 1},
            kind="rlm_loop",
            options=RunOptions(provider=fake),
        )
    )
    assert value["status"] == "partial"
    assert value["trace"][0]["observation"]["type"] == "parse_error"


def test_rlm_loop_avoids_child_step_at_depth_floor():
    fake = _provider(
        json.dumps(
            {
                "protocol": "fleshwound-rlm-action/1",
                "action": "step",
                "kind": "constant",
                "input": {"value": "x"},
            }
        )
    )
    value = assert_ok(
        run_step(
            {"task": "too shallow", "max_iterations": 1},
            kind="rlm_loop",
            options=RunOptions(
                budget={"tokens": 100, "steps": 4, "depth": 1, "tool_calls": 0},
                provider=fake,
            ),
        )
    )
    assert value["status"] == "partial"
    assert value["trace"][0]["observation"]["type"] == "budget_limit"
