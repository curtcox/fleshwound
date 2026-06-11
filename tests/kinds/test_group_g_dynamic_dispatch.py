from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._fake_provider import FakeProvider, text_result
from tests._golden import assert_deterministic


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


class TestConvention:
    def test_dynamic_dispatch_uses_literal_runtime_kind(self):
        value = assert_ok(
            run_step(
                {
                    "chooser": "literal",
                    "literal_kind": "constant",
                    "inner_input": {"value": "chosen"},
                },
                kind="dynamic_dispatch",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["chosen_kind"] == "constant"
        assert value["result"]["outcome"] == "ok"
        assert value["result"]["value"] == "chosen"

    def test_dynamic_dispatch_can_choose_kind_with_llm_and_catalog_prompt(self):
        fake = FakeProvider({"Choose one kind": text_result("echo", 1, 1)})
        value = assert_ok(
            run_step(
                {
                    "chooser": "llm",
                    "literal_kind": None,
                    "task_for_chooser": "repeat input",
                    "inner_input": {"x": 1},
                },
                kind="dynamic_dispatch",
                options=RunOptions(provider=fake),
            )
        )
        assert value["chosen_kind"] == "echo"
        assert value["result"]["value"] == {"x": 1}
        assert "constant" in fake.prompts[0]

    def test_meta_planner_executes_json_plan_from_model(self):
        fake = FakeProvider(
            {
                "Plan task with catalog": text_result(
                    '[{"kind": "constant", "input": {"value": 3}}]', 2, 2
                )
            }
        )
        value = assert_ok(
            run_step(
                {"task": "produce three"},
                kind="meta_planner",
                options=RunOptions(provider=fake),
            )
        )
        assert value["plan"] == [{"kind": "constant", "input": {"value": 3}}]
        assert [result["value"] for result in value["results"]] == [3]

    def test_cond_dispatch_uses_first_true_monty_predicate(self):
        value = assert_ok(
            run_step(
                {
                    "branches": [
                        {"when": "input['route'] == 'nope'", "kind": "noop_fail"},
                        {"when": "input['route'] == 'echo'", "kind": "echo"},
                    ],
                    "default_kind": "constant",
                    "inner_input": {"route": "echo"},
                },
                kind="cond_dispatch",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["chosen_kind"] == "echo"
        assert value["result"]["value"] == {"route": "echo"}

    def test_cascade_stops_only_when_predicate_accepts_value(self):
        value = assert_ok(
            run_step(
                {
                    "inner_input": {"value": "accepted"},
                    "kinds": ["echo", "constant"],
                    "stop_predicate": "input == 'accepted'",
                },
                kind="cascade",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["tried"] == ["echo", "constant"]
        assert value["chosen_kind"] == "constant"
        assert value["result"]["value"] == "accepted"


class TestBudget:
    def test_runtime_chosen_kind_is_recorded_on_allocate_event(self):
        ledger = BudgetLedger({"tokens": 20, "steps": 4, "depth": 3, "tool_calls": 0})
        assert_ok(
            run_step(
                {
                    "chooser": "literal",
                    "literal_kind": "constant",
                    "inner_input": {"value": "x"},
                },
                kind="dynamic_dispatch",
                options=RunOptions(provider=provider(), ledger=ledger),
            )
        )
        allocate_events = [
            event for event in ledger.events if event.kind == "allocate_child"
        ]
        assert [event.resolved_kind for event in allocate_events] == ["constant"]

    def test_meta_planner_allocates_plan_children_in_order(self):
        ledger = BudgetLedger({"tokens": 30, "steps": 6, "depth": 3, "tool_calls": 0})
        fake = FakeProvider(
            {
                "Plan task with catalog": text_result(
                    '[{"kind": "echo", "input": 1}, {"kind": "constant", "input": {"value": 2}}]',
                    2,
                    2,
                )
            }
        )
        assert_ok(
            run_step(
                {"task": "two steps"},
                kind="meta_planner",
                options=RunOptions(provider=fake, ledger=ledger),
            )
        )
        child_ids = [
            event.budget_id for event in ledger.events if event.kind == "close_child"
        ]
        resolved = [
            event.resolved_kind
            for event in ledger.events
            if event.kind == "allocate_child"
        ]
        assert child_ids == ["root.1", "root.2"]
        assert resolved == ["echo", "constant"]


class TestFailure:
    def test_dynamic_dispatch_surfaces_unknown_runtime_kind_as_child_error(self):
        value = assert_ok(
            run_step(
                {
                    "chooser": "literal",
                    "literal_kind": "missing_kind",
                    "inner_input": {},
                },
                kind="dynamic_dispatch",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["result"]["outcome"] == "host_error"
        assert value["result"]["host_error"]["code"] == "unknown_kind"

    def test_meta_planner_treats_malformed_model_plan_as_empty_plan(self):
        value = assert_ok(
            run_step(
                {"task": "bad plan"},
                kind="meta_planner",
                options=RunOptions(provider=provider("not json")),
            )
        )
        assert value == {"plan": [], "results": []}

    def test_cond_dispatch_unknown_default_kind_is_returned_as_child_error(self):
        value = assert_ok(
            run_step(
                {"branches": [], "default_kind": "missing_kind", "inner_input": {}},
                kind="cond_dispatch",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["chosen_kind"] == "missing_kind"
        assert value["result"]["host_error"]["code"] == "unknown_kind"


class TestDeterminism:
    def test_dynamic_dispatch_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "dynamic_dispatch",
            {
                "chooser": "literal",
                "literal_kind": "constant",
                "inner_input": {"value": "x"},
            },
            provider=provider(),
            budget={"tokens": 20, "steps": 4, "depth": 3, "tool_calls": 0},
        )
        assert len(digest) == 64

    def test_meta_planner_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "meta_planner",
            {"task": "produce x"},
            provider=provider('[{"kind": "constant", "input": {"value": "x"}}]'),
            budget={"tokens": 30, "steps": 4, "depth": 3, "tool_calls": 0},
        )
        assert len(digest) == 64
