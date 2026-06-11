"""Contract tests for budget enforcement at host primitive boundaries."""

from __future__ import annotations

from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_host_error, assert_ok


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


class TestStepEntryRefusal:
    def test_run_step_refuses_entry_when_step_budget_already_spent(self):
        ledger = BudgetLedger({"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0})
        assert ledger.charge_step("root", "preflight")
        result = run_step(
            {"x": 1},
            kind="echo",
            options=RunOptions(provider=provider(), ledger=ledger),
        )
        error = assert_host_error(result, "budget_exhausted")
        assert "step budget" in error["message"].lower()
        assert ledger.events[-1].kind == "deny"


class TestMidExecutionPrimitiveBoundaries:
    def test_monty_second_step_call_is_denied_when_parent_step_budget_is_gone(self):
        value = assert_ok(
            run_step(
                {
                    "code": (
                        "first = step({'value': 1}, "
                        "{'tokens': 0, 'steps': 1, 'depth': 1, 'tool_calls': 0}, "
                        "kind='constant')\n"
                        "second = step({'value': 2}, "
                        "{'tokens': 0, 'steps': 1, 'depth': 1, 'tool_calls': 0}, "
                        "kind='constant')\n"
                        "{'first': first, 'second': second}"
                    )
                },
                kind="monty_exec",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 0, "steps": 2, "depth": 2, "tool_calls": 0},
                ),
            )
        )
        assert value["first"]["outcome"] == "ok"
        assert value["second"]["outcome"] == "host_error"
        assert value["second"]["host_error"]["code"] == "budget_denied"

    def test_monty_ignoring_denied_step_still_completes_without_forced_exit(self):
        value = assert_ok(
            run_step(
                {
                    "code": (
                        "step({'value': 1}, "
                        "{'tokens': 0, 'steps': 1, 'depth': 1, 'tool_calls': 0}, "
                        "kind='constant')\n"
                        "step({'value': 2}, "
                        "{'tokens': 0, 'steps': 1, 'depth': 1, 'tool_calls': 0}, "
                        "kind='constant')\n"
                        "'done'"
                    )
                },
                kind="monty_exec",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 0, "steps": 2, "depth": 2, "tool_calls": 0},
                ),
            )
        )
        assert value == "done"

    def test_monty_pure_computation_completes_after_step_entry_depletes_step_budget(
        self,
    ):
        value = assert_ok(
            run_step(
                {"code": "total = 0\nfor i in range(100):\n    total = total + 1\ntotal"},
                kind="monty_exec",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0},
                ),
            )
        )
        assert value == 100

    def test_llm_returns_budget_exhausted_when_token_budget_is_gone(self):
        value = assert_ok(
            run_step(
                {"target": "tokens"},
                kind="budget_hog",
                options=RunOptions(
                    provider=provider("too much", Usage(10, 0)),
                    budget={"tokens": 2, "steps": 1, "depth": 1, "tool_calls": 0},
                ),
            )
        )
        assert value["llm"]["status"] == "error"
        assert value["llm"]["error"]["code"] == "budget_exhausted"

    def test_budget_hog_tokens_stops_step_when_llm_budget_is_exhausted(self):
        assert_host_error(
            run_step(
                {"target": "tokens", "stop_on_exhaustion": True},
                kind="budget_hog",
                options=RunOptions(
                    provider=provider("too much", Usage(10, 0)),
                    budget={"tokens": 2, "steps": 1, "depth": 1, "tool_calls": 0},
                ),
            ),
            "budget_exhausted",
        )

    def test_budget_hog_tool_calls_stops_step_when_tool_budget_is_exhausted(self):
        assert_host_error(
            run_step(
                {"target": "tool_calls", "stop_on_exhaustion": True},
                kind="budget_hog",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0},
                ),
            ),
            "budget_exhausted",
        )

    def test_budget_hog_steps_stops_step_when_child_step_is_denied(self):
        assert_host_error(
            run_step(
                {"target": "steps", "stop_on_exhaustion": True},
                kind="budget_hog",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 10, "steps": 2, "depth": 3, "tool_calls": 0},
                ),
            ),
            "budget_denied",
        )


class TestDepthFloor:
    def test_infinite_descent_halts_with_budget_denied_at_depth_floor(self):
        value = assert_ok(
            run_step(
                {},
                kind="infinite_descent",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 0, "steps": 8, "depth": 1, "tool_calls": 0},
                ),
            )
        )
        result = value["result"]
        assert result["outcome"] == "host_error"
        assert result["host_error"]["code"] == "budget_denied"
