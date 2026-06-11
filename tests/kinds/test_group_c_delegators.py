from __future__ import annotations
import pytest
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._fake_provider import FakeProvider, text_result
from tests._fake_user import FakeAskUser
from tests._golden import assert_deterministic


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


class TestConvention:
    def test_map_reduce_maps_items_and_reduces_values(self):
        value = assert_ok(
            run_step(
                {
                    "items": [{"value": 1}, {"value": 2}],
                    "map_kind": "constant",
                    "reduce_kind": "echo",
                },
                kind="map_reduce",
                options=RunOptions(provider=provider()),
            )
        )
        assert value == {"mapped": [1, 2], "reduced": [1, 2], "errors": []}

    def test_retry_wrapper_stops_after_first_ok(self):
        value = assert_ok(
            run_step(
                {
                    "inner_kind": "constant",
                    "inner_input": {"value": "done"},
                    "max_attempts": 3,
                },
                kind="retry_wrapper",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["attempts"] == 1
        assert value["result"]["value"] == "done"

    def test_ensemble_aggregates_with_model_when_prompt_is_supplied(self):
        fake = FakeProvider({"Pick best": text_result("chosen-by-model", 2, 2)})
        value = assert_ok(
            run_step(
                {
                    "inner_kind": "constant",
                    "inner_input": {"value": "candidate"},
                    "n": 2,
                    "aggregator_prompt": "Pick best",
                },
                kind="ensemble",
                options=RunOptions(provider=fake),
            )
        )
        assert value == {
            "chosen": "chosen-by-model",
            "candidates": ["candidate", "candidate"],
        }
        assert "Candidates" in fake.prompts[0]

    def test_clarify_then_delegate_records_question_answer_and_child_result(self):
        ask_user = FakeAskUser(["make it short"])
        value = assert_ok(
            run_step(
                {"task": "summarize", "child_kind": "echo"},
                kind="clarify_then_delegate",
                options=RunOptions(provider=provider(), ask_user=ask_user),
            )
        )
        assert value["clarification_q"] == "Clarify task: summarize"
        assert value["clarification_a"] == "make it short"
        assert value["result"]["value"] == {
            "task": "summarize",
            "clarification": "make it short",
        }


class TestBudget:
    def test_map_reduce_allocates_children_in_order_and_refunds_each_child(self):
        ledger = BudgetLedger({"tokens": 30, "steps": 8, "depth": 3, "tool_calls": 0})
        assert_ok(
            run_step(
                {"items": [{"value": "a"}, {"value": "b"}], "map_kind": "constant"},
                kind="map_reduce",
                options=RunOptions(provider=provider(), ledger=ledger),
            )
        )
        child_ids = [
            event.budget_id for event in ledger.events if event.kind == "close_child"
        ]
        assert child_ids == ["root.1", "root.2"]
        for child_id in child_ids:
            close_index = next(
                (
                    idx
                    for idx, event in enumerate(ledger.events)
                    if event.kind == "close_child" and event.budget_id == child_id
                )
            )
            assert ledger.events[close_index - 1].kind == "refund_child"

    def test_retry_wrapper_refunds_failed_child_before_next_attempt(self):
        ledger = BudgetLedger({"tokens": 20, "steps": 6, "depth": 3, "tool_calls": 0})
        value = assert_ok(
            run_step(
                {"inner_kind": "noop_fail", "inner_input": {}, "max_attempts": 2},
                kind="retry_wrapper",
                options=RunOptions(provider=provider(), ledger=ledger),
            )
        )
        assert value["attempts"] == 2
        assert value["result"]["host_error"]["code"] == "executor_error"
        refund_indices = [
            idx
            for idx, event in enumerate(ledger.events)
            if event.kind == "refund_child"
        ]
        close_indices = [
            idx
            for idx, event in enumerate(ledger.events)
            if event.kind == "close_child"
        ]
        assert refund_indices
        assert all(
            (refund < close for refund, close in zip(refund_indices, close_indices))
        )


class TestFailure:
    def test_map_reduce_records_child_error_without_failing_parent(self):
        value = assert_ok(
            run_step(
                {"items": [{"value": "ok"}, {}], "map_kind": "constant"},
                kind="map_reduce",
                options=RunOptions(provider=provider()),
            )
        )
        assert value == {"mapped": ["ok", None], "reduced": None, "errors": [1]}

    def test_retry_wrapper_zero_attempts_returns_no_result(self):
        value = assert_ok(
            run_step(
                {
                    "inner_kind": "constant",
                    "inner_input": {"value": "unused"},
                    "max_attempts": 0,
                },
                kind="retry_wrapper",
                options=RunOptions(provider=provider()),
            )
        )
        assert value == {"attempts": 0, "result": None}

    def test_judge_defaults_to_fail_when_model_does_not_pass(self):
        value = assert_ok(
            run_step(
                {"candidate": "answer", "criteria": "strict"},
                kind="judge",
                options=RunOptions(provider=provider("not good enough")),
            )
        )
        assert value == {"verdict": "fail", "rationale": "not good enough"}


@pytest.mark.integration
class TestEndToEnd:
    def test_judge_passes_on_model_pass_text(self):
        value = assert_ok(
            run_step(
                {"candidate": "answer", "criteria": "strict"},
                kind="judge",
                options=RunOptions(provider=provider("PASS: meets the bar")),
            )
        )
        assert value["verdict"] == "pass"

    def test_clarify_then_delegate_works_without_ask_user(self):
        value = assert_ok(
            run_step(
                {"task": "summarize", "child_kind": "echo"},
                kind="clarify_then_delegate",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["clarification_q"] is None
        assert value["result"]["value"] == {"task": "summarize", "clarification": None}


class TestDeterminism:
    def test_map_reduce_is_deterministic(self):
        digest = assert_deterministic(
            "map_reduce",
            {
                "items": [{"value": "a"}, {"value": "b"}],
                "map_kind": "constant",
                "reduce_kind": "echo",
            },
            provider=provider(),
        )
        assert len(digest) == 64

    def test_ensemble_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "ensemble",
            {
                "inner_kind": "constant",
                "inner_input": {"value": "x"},
                "n": 2,
                "aggregator_prompt": "Pick",
            },
            provider=provider("x"),
        )
        assert len(digest) == 64
