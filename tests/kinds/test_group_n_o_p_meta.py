from __future__ import annotations
import hashlib
import json
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "{}", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


def value_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class TestConvention:
    def test_scoring_and_grading_kinds_return_documented_shapes(self):
        rubric = assert_ok(
            run_step(
                {
                    "candidate": "answer",
                    "rubric": [
                        {"criterion": "correctness", "weight": 2, "scale": "0-5"}
                    ],
                },
                kind="rubric_grader",
                options=RunOptions(
                    provider=provider(
                        '{"scores": [{"criterion": "correctness", "score": 4, "rationale": "solid"}], "weighted_total": 8, "notes": "ok"}'
                    )
                ),
            )
        )
        preference = assert_ok(
            run_step(
                {"a": "short", "b": "clear", "criterion": "best"},
                kind="pairwise_preference",
                options=RunOptions(
                    provider=provider(
                        '{"winner": "b", "rationale": "clearer", "confidence": 0.8}'
                    )
                ),
            )
        )
        aggregate = assert_ok(
            run_step(
                {
                    "scores": [{"score": 2, "weight": 1}, {"score": 4, "weight": 3}],
                    "policy": "weighted_mean",
                },
                kind="score_aggregator",
            )
        )
        assert rubric["weighted_total"] == 8
        assert preference == {"winner": "b", "rationale": "clearer", "confidence": 0.8}
        assert aggregate == {"aggregate": 3.5, "n": 2}

    def test_adversarial_and_failure_kinds_round_trip_structured_values(self):
        attack = assert_ok(
            run_step(
                {
                    "target_kind": "echo",
                    "target_input_template": {"x": 1},
                    "attack_goal": "make it fail",
                },
                kind="attack_generator",
                options=RunOptions(
                    provider=provider(
                        '{"crafted_input": {"x": "bad"}, "rationale": "stress input"}'
                    )
                ),
            )
        )
        classified = assert_ok(
            run_step(
                {
                    "step_result": {
                        "outcome": "host_error",
                        "value": None,
                        "host_error": {"code": "executor_error", "message": "boom"},
                    }
                },
                kind="failure_classifier",
                options=RunOptions(
                    provider=provider(
                        '{"category": "host_error", "subcategory": "executor_error", "evidence": "boom"}'
                    )
                ),
            )
        )
        canary = assert_ok(
            run_step(
                {
                    "frozen_kind": "constant",
                    "frozen_input": {"value": {"stable": True}},
                    "expected_value_hash": value_hash({"stable": True}),
                },
                kind="regression_canary",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        assert attack["crafted_input"] == {"x": "bad"}
        assert classified["category"] == "host_error"
        assert canary["passed"] is True

    def test_translation_and_memo_kinds_compose_explicitly(self):
        adapted = assert_ok(
            run_step(
                {
                    "source_kind": "echo",
                    "target_kind": "constant",
                    "source_value": {"value": "ready"},
                },
                kind="convention_adapter",
                options=RunOptions(
                    provider=provider(
                        '{"target_input": {"value": "ready"}, "lossy": false, "notes": ""}'
                    )
                ),
            )
        )
        chained = assert_ok(
            run_step(
                {
                    "first_kind": "constant",
                    "first_input": {"value": {"value": "ready"}},
                    "second_kind": "constant",
                },
                kind="chain_with_adapter",
                options=RunOptions(
                    provider=provider(
                        '{"target_input": {"value": "ready"}, "lossy": false, "notes": ""}'
                    ),
                    budget={"tokens": 100, "steps": 8, "depth": 4, "tool_calls": 0},
                ),
            )
        )
        memo = assert_ok(
            run_step(
                {
                    "inner_kind": "constant",
                    "inner_input": {"value": "expensive"},
                    "memo": {},
                },
                kind="content_hash_memo",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        assert adapted == {
            "target_input": {"value": "ready"},
            "lossy": False,
            "notes": "",
        }
        assert chained["second_result"]["value"] == "ready"
        assert memo["hit"] is False
        assert memo["memo"][memo["hash"]] == "expensive"


class TestBudget:
    def test_calibration_fans_out_once_per_example(self):
        ledger = BudgetLedger({"tokens": 100, "steps": 6, "depth": 3, "tool_calls": 0})
        value = assert_ok(
            run_step(
                {
                    "grader_kind": "rubric_grader",
                    "examples": [
                        {"item": "a", "gold_score": 1},
                        {"item": "b", "gold_score": 1},
                    ],
                },
                kind="calibration",
                options=RunOptions(
                    provider=provider(
                        '{"scores": [], "weighted_total": 1, "notes": ""}'
                    ),
                    ledger=ledger,
                ),
            )
        )
        assert value["agreement"] == 1.0
        assert [
            event.resolved_kind
            for event in ledger.events
            if event.kind == "allocate_child"
        ] == ["rubric_grader", "rubric_grader"]

    def test_dedup_then_map_allocates_once_per_unique_item_hash(self):
        ledger = BudgetLedger({"tokens": 0, "steps": 5, "depth": 3, "tool_calls": 0})
        value = assert_ok(
            run_step(
                {
                    "items": [{"value": "same"}, {"value": "same"}, {"value": "other"}],
                    "inner_kind": "constant",
                },
                kind="dedup_then_map",
                options=RunOptions(ledger=ledger),
            )
        )
        assert len(value["results_by_hash"]) == 2
        assert value["items_to_hash"][0] == value["items_to_hash"][1]
        assert [
            event.resolved_kind
            for event in ledger.events
            if event.kind == "allocate_child"
        ] == ["constant", "constant"]


class TestFailure:
    def test_regression_canary_reports_hash_mismatch_as_value_not_host_error(self):
        value = assert_ok(
            run_step(
                {
                    "frozen_kind": "constant",
                    "frozen_input": {"value": "changed"},
                    "expected_value_hash": "not-the-hash",
                },
                kind="regression_canary",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        assert value["passed"] is False
        assert value["result"]["outcome"] == "ok"

    def test_adversarial_loop_records_target_host_error_as_success(self):
        value = assert_ok(
            run_step(
                {
                    "target_kind": "noop_fail",
                    "seed_input": {},
                    "max_rounds": 1,
                    "success_predicate": "host_error",
                },
                kind="adversarial_loop",
                options=RunOptions(
                    provider=provider(
                        '{"crafted_input": {}, "rationale": "force failure"}'
                    ),
                    budget={"tokens": 100, "steps": 6, "depth": 3, "tool_calls": 0},
                ),
            )
        )
        assert value["rounds"] == 1
        assert value["history"][0]["successful"] is True
        assert (
            value["history"][0]["target_result"]["host_error"]["code"]
            == "executor_error"
        )

    def test_content_hash_memo_hit_does_not_allocate_child(self):
        inner = {"value": "cached"}
        key = value_hash({"kind": "constant", "input": inner})
        ledger = BudgetLedger({"tokens": 0, "steps": 2, "depth": 2, "tool_calls": 0})
        value = assert_ok(
            run_step(
                {
                    "inner_kind": "constant",
                    "inner_input": inner,
                    "memo": {key: "cached"},
                },
                kind="content_hash_memo",
                options=RunOptions(ledger=ledger),
            )
        )
        assert value["hit"] is True
        assert [
            event for event in ledger.events if event.kind == "allocate_child"
        ] == []


class TestDeterminism:
    def test_score_aggregator_is_deterministic(self):
        digest = assert_deterministic(
            "score_aggregator",
            {
                "scores": [{"score": 1, "weight": 1}, {"score": 3, "weight": 1}],
                "policy": "median",
            },
            provider=provider(),
            budget={"tokens": 0, "steps": 2, "depth": 1, "tool_calls": 0},
        )
        assert len(digest) == 64

    def test_regression_canary_is_deterministic(self):
        digest = assert_deterministic(
            "regression_canary",
            {
                "frozen_kind": "constant",
                "frozen_input": {"value": 1},
                "expected_value_hash": value_hash(1),
            },
            provider=provider(),
            budget={"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0},
        )
        assert len(digest) == 64

    def test_chain_with_adapter_is_deterministic(self):
        digest = assert_deterministic(
            "chain_with_adapter",
            {
                "first_kind": "constant",
                "first_input": {"value": {"value": "ready"}},
                "second_kind": "constant",
            },
            provider=provider(
                '{"target_input": {"value": "ready"}, "lossy": false, "notes": ""}'
            ),
            budget={"tokens": 100, "steps": 8, "depth": 4, "tool_calls": 0},
        )
        assert len(digest) == 64
