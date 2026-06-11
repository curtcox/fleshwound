from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


class RecordingProvider:
    def __init__(self, text: str):
        self.text = text
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> ModelTextResult:
        self.prompts.append(prompt)
        return ModelTextResult(self.text, Usage(1, 1))


class TestConvention:
    def test_refine_until_stops_when_judge_passes(self):
        value = assert_ok(
            run_step(
                {
                    "inner_input": {"value": "draft"},
                    "inner_kind": "constant",
                    "judge_kind": "judge",
                    "max_rounds": 3,
                },
                kind="refine_until",
                options=RunOptions(
                    provider=provider("pass: good enough"),
                    budget={"tokens": 100, "steps": 8, "depth": 3, "tool_calls": 0},
                ),
            )
        )
        assert value["rounds"] == 1
        assert value["final"] == "draft"
        assert value["history"][0]["verdict"]["value"]["verdict"] == "pass"

    def test_conversation_carries_all_state_in_input_turns(self):
        value = assert_ok(
            run_step(
                {"system": "Be brief.", "turns": [{"role": "user", "content": "Hi"}]},
                kind="conversation",
                options=RunOptions(
                    provider=provider(
                        '{"reply": "Hello", "turns": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}]}'
                    )
                ),
            )
        )
        assert value["reply"] == "Hello"
        assert value["turns"] == [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]

    def test_tournament_uses_pairwise_judge_in_bracket_order(self):
        value = assert_ok(
            run_step(
                {"candidates": ["a", "b", "c"], "judge_kind": "pairwise_preference"},
                kind="tournament",
                options=RunOptions(
                    provider=provider(
                        '{"winner": "b", "rationale": "second wins", "confidence": 0.9}'
                    ),
                    budget={"tokens": 100, "steps": 6, "depth": 3, "tool_calls": 0},
                ),
            )
        )
        assert value["winner"] == "c"
        assert [(match["a"], match["b"]) for match in value["bracket"]] == [
            ("a", "b"),
            ("b", "c"),
        ]

    def test_pipeline_transformer_precondition_and_catalog_kinds(self):
        pipeline = assert_ok(
            run_step(
                {
                    "initial": {"value": "x"},
                    "stages": [{"kind": "constant"}, {"kind": "echo"}],
                },
                kind="pipeline",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 5, "depth": 3, "tool_calls": 0}
                ),
            )
        )
        transformed = assert_ok(
            run_step(
                {
                    "inner_input_template": {"value": "before"},
                    "preprocess": '{"value": input["value"] + "-pre"}',
                    "inner_kind": "constant",
                    "postprocess": '{"wrapped": input["value"]}',
                },
                kind="transformer",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        gated = assert_ok(
            run_step(
                {"predicate": "False", "inner_kind": "noop_fail", "inner_input": {}},
                kind="precondition_gate",
            )
        )
        listed = assert_ok(run_step({}, kind="kind_lister"))
        assert pipeline["final"] == "x"
        assert transformed == {"wrapped": "before-pre"}
        assert gated == {"gated": True, "reason": "predicate false"}
        assert {
            "name": "catalog_self_test",
            "convention": "run minimal inputs for listed kinds",
        } in listed["kinds"]

    def test_kind_chooser_prompt_is_grounded_in_catalog(self):
        fake = RecordingProvider(
            '{"chosen_kind": "echo", "rationale": "echo returns input"}'
        )
        value = assert_ok(
            run_step(
                {"task": "return input unchanged"},
                kind="kind_chooser",
                options=RunOptions(provider=fake),
            )
        )
        assert value == {"chosen_kind": "echo", "rationale": "echo returns input"}
        assert (
            '"echo": "input -> input verbatim; host charges one step"'
            in fake.prompts[0]
        )

    def test_catalog_self_test_reports_unexpected_host_errors(self):
        value = assert_ok(
            run_step(
                {"kinds_to_exercise": ["constant", "echo", "kind_lister", "noop_fail"]},
                kind="catalog_self_test",
                options=RunOptions(
                    budget={"tokens": 1000, "steps": 10, "depth": 3, "tool_calls": 0}
                ),
            )
        )
        assert value["unexpected_host_errors"] == []
        assert {row["kind"]: row["expected_host_error"] for row in value["results"]}[
            "noop_fail"
        ] is True

    def test_catalog_self_test_exercises_registered_catalog(self):
        value = assert_ok(
            run_step(
                {"kinds_to_exercise": None},
                kind="catalog_self_test",
                options=RunOptions(
                    budget={
                        "tokens": 1000000,
                        "steps": 300,
                        "depth": 8,
                        "tool_calls": 100,
                    }
                ),
            )
        )
        exercised = {row["kind"] for row in value["results"]}
        assert "catalog_self_test" not in exercised
        assert {"constant", "refine_until", "pipeline", "kind_chooser"}.issubset(
            exercised
        )
        assert value["unexpected_host_errors"] == []


class TestBudget:
    def test_refine_until_allocates_candidate_and_judge_each_round(self):
        ledger = BudgetLedger({"tokens": 100, "steps": 8, "depth": 3, "tool_calls": 0})
        assert_ok(
            run_step(
                {
                    "inner_input": {"value": "draft"},
                    "inner_kind": "constant",
                    "judge_kind": "judge",
                    "max_rounds": 2,
                },
                kind="refine_until",
                options=RunOptions(provider=provider("fail"), ledger=ledger),
            )
        )
        assert [
            event.resolved_kind
            for event in ledger.events
            if event.kind == "allocate_child"
        ] == ["constant", "judge", "constant", "judge"]

    def test_precondition_gate_false_does_not_allocate_child(self):
        ledger = BudgetLedger({"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0})
        assert_ok(
            run_step(
                {"predicate": "False", "inner_kind": "echo", "inner_input": {"x": 1}},
                kind="precondition_gate",
                options=RunOptions(ledger=ledger),
            )
        )
        assert [
            event for event in ledger.events if event.kind == "allocate_child"
        ] == []

    def test_catalog_self_test_fans_out_to_requested_kinds(self):
        ledger = BudgetLedger({"tokens": 100, "steps": 8, "depth": 3, "tool_calls": 0})
        assert_ok(
            run_step(
                {"kinds_to_exercise": ["constant", "echo", "kind_lister"]},
                kind="catalog_self_test",
                options=RunOptions(ledger=ledger),
            )
        )
        assert [
            event.resolved_kind
            for event in ledger.events
            if event.kind == "allocate_child"
        ] == ["constant", "echo", "kind_lister"]


class TestFailure:
    def test_pipeline_keeps_prior_value_when_stage_fails(self):
        value = assert_ok(
            run_step(
                {
                    "initial": "start",
                    "stages": [{"kind": "noop_fail"}, {"kind": "echo"}],
                },
                kind="pipeline",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 5, "depth": 3, "tool_calls": 0}
                ),
            )
        )
        assert value["stages"][0]["host_error"]["code"] == "executor_error"
        assert value["final"] == "start"

    def test_transformer_surfaces_bad_preprocess_as_executor_error(self):
        result = run_step(
            {
                "inner_input_template": {"value": "x"},
                "preprocess": "input['missing']",
                "inner_kind": "constant",
            },
            kind="transformer",
        )
        assert result["outcome"] == "host_error"
        assert result["host_error"]["code"] == "executor_error"

    def test_catalog_self_test_marks_unexpected_host_error(self):
        value = assert_ok(
            run_step(
                {"kinds_to_exercise": ["dynamic_dispatch"]},
                kind="catalog_self_test",
                options=RunOptions(
                    budget={"tokens": 100, "steps": 4, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        assert value["unexpected_host_errors"] == []


class TestDeterminism:
    def test_refine_until_is_deterministic(self):
        digest = assert_deterministic(
            "refine_until",
            {
                "inner_input": {"value": "draft"},
                "inner_kind": "constant",
                "judge_kind": "judge",
                "max_rounds": 2,
            },
            provider=provider("fail"),
            budget={"tokens": 100, "steps": 8, "depth": 3, "tool_calls": 0},
        )
        assert len(digest) == 64

    def test_pipeline_is_deterministic(self):
        digest = assert_deterministic(
            "pipeline",
            {
                "initial": {"value": "x"},
                "stages": [{"kind": "constant"}, {"kind": "echo"}],
            },
            provider=provider(),
            budget={"tokens": 0, "steps": 5, "depth": 3, "tool_calls": 0},
        )
        assert len(digest) == 64

    def test_catalog_self_test_is_deterministic(self):
        digest = assert_deterministic(
            "catalog_self_test",
            {"kinds_to_exercise": ["constant", "echo", "kind_lister"]},
            provider=provider(),
            budget={"tokens": 100, "steps": 8, "depth": 3, "tool_calls": 0},
        )
        assert len(digest) == 64
