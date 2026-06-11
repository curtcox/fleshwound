from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, HOST_ERROR_CODES, run_step
from conftest import assert_host_error, assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


class TestConvention:
    def test_always_partial_returns_deliberate_partial_value(self):
        value = assert_ok(
            run_step({}, kind="always_partial", options=RunOptions(provider=provider()))
        )
        assert value == {
            "status": "partial",
            "program": "",
            "notes": "deliberate partial for tests",
        }

    def test_provider_swap_uses_supplied_provider_for_child_subtree(self):
        inner_provider = provider("child provider text", Usage(1, 1))
        value = assert_ok(
            run_step(
                {
                    "inner_input": {"task": "draft", "context": None},
                    "inner_kind": "prose_writer",
                    "inner_provider": inner_provider,
                },
                kind="provider_swap",
                options=RunOptions(
                    provider=provider("outer provider text", Usage(1, 1))
                ),
            )
        )
        assert value["result"]["outcome"] == "ok"
        assert value["result"]["value"]["text"] == "child provider text"


class TestBudget:
    def test_budget_hog_steps_reports_child_budget_denial(self):
        value = assert_ok(
            run_step(
                {"target": "steps"},
                kind="budget_hog",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 10, "steps": 2, "depth": 3, "tool_calls": 0},
                ),
            )
        )
        assert value["result"]["outcome"] == "host_error"
        assert value["result"]["host_error"]["code"] == "budget_denied"

    def test_budget_hog_tool_calls_records_denial_when_exhausted(self):
        ledger = BudgetLedger({"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0})
        value = assert_ok(
            run_step(
                {"target": "tool_calls"},
                kind="budget_hog",
                options=RunOptions(provider=provider(), ledger=ledger),
            )
        )
        assert value["target"] == "tool_calls"
        assert any(
            (
                event.kind == "deny" and event.amount == {"tool_calls": 1}
                for event in ledger.events
            )
        )


class TestFailure:
    def test_always_host_error_can_produce_every_contract_host_error_code(self):
        observed = set()
        for code in sorted(HOST_ERROR_CODES):
            error = assert_host_error(
                run_step(
                    {"code": code},
                    kind="always_host_error",
                    options=RunOptions(provider=provider()),
                ),
                code,
            )
            observed.add(error["code"])
        assert observed == HOST_ERROR_CODES

    def test_budget_hog_tokens_surfaces_llm_budget_exhaustion_as_data(self):
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
        assert value["budget"]["tokens_remaining"] == 2


class TestDeterminism:
    def test_provider_swap_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "provider_swap",
            {
                "inner_input": {"task": "draft", "context": None},
                "inner_kind": "prose_writer",
                "inner_provider": provider("child text", Usage(1, 1)),
            },
            provider=provider("outer text", Usage(1, 1)),
            budget={"tokens": 20, "steps": 4, "depth": 3, "tool_calls": 0},
        )
        assert len(digest) == 64
