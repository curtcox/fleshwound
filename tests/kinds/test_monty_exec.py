from __future__ import annotations

import pytest

from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import run_step

from conftest import assert_host_error, assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "model text", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(prompt_tokens=1, completion_tokens=1)))


class TestConvention:
    def test_trivial_expression_returns_final_value(self):
        value = assert_ok(run_step({"code": "input['x'] + 1", "x": 41}, provider=provider(), kind="monty_exec"))

        assert value == 42

    def test_code_can_call_llm_external(self):
        value = assert_ok(
            run_step(
                {"code": "llm('say hi')['text']"},
                {"tokens": 5, "steps": 1, "depth": 1, "tool_calls": 0},
                provider=provider("hi", Usage(1, 1)),
                kind="monty_exec",
            )
        )

        assert value == "hi"

    def test_code_can_call_budget_external(self):
        value = assert_ok(run_step({"code": "budget()['budget_id']"}, provider=provider(), kind="monty_exec"))

        assert value == "root"


class TestBudget:
    def test_monty_exec_charges_step_and_external_llm_tokens(self):
        ledger = BudgetLedger({"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0})

        value = assert_ok(
            run_step(
                {"code": "llm('token charge')['status']"},
                provider=provider("ok", Usage(2, 3)),
                kind="monty_exec",
                ledger=ledger,
            )
        )

        assert value == "ok"
        assert [event.kind for event in ledger.events] == ["create_root", "charge_step", "charge_tokens"]
        assert ledger.events[-1].amount == {"tokens": 5}


class TestFailure:
    def test_code_raising_is_monty_error(self):
        result = run_step({"code": "raise Exception('boom')"}, provider=provider(), kind="monty_exec")

        error = assert_host_error(result, "monty_error")
        assert "boom" in error["message"]

    def test_non_serializable_final_expression_is_malformed_result(self):
        result = run_step({"code": "{1, 2}"}, provider=provider(), kind="monty_exec")

        assert_host_error(result, "malformed_result")


@pytest.mark.integration
class TestEndToEnd:
    def test_code_can_call_step_recursively(self):
        value = assert_ok(
            run_step(
                {
                    "code": "step({'value': 'child'}, {'tokens': 0, 'steps': 1, 'depth': 1, 'tool_calls': 0}, kind='constant')['value']"
                },
                {"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0},
                provider=provider(),
                kind="monty_exec",
            )
        )

        assert value == "child"


class TestDeterminism:
    def test_monty_exec_is_deterministic(self):
        digest = assert_deterministic(
            "monty_exec",
            {"code": "{'x': input['x'], 'twice': input['x'] * 2}", "x": 7},
            provider=provider(),
            budget={"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0},
        )

        assert len(digest) == 64
