from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


class TestConvention:
    def test_subset_pick_delegates_to_a_kind_from_the_subset(self):
        value = assert_ok(
            run_step(
                {"inner_input": {"value": "chosen"}, "subset": ["constant"]},
                kind="subset_pick",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["result"]["outcome"] == "ok"
        assert value["result"]["value"] == "chosen"

    def test_inherit_chain_uses_same_as_parent_by_default(self):
        value = assert_ok(
            run_step(
                {"task": "descend", "depth": 2},
                kind="inherit_chain",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 20, "steps": 8, "depth": 4, "tool_calls": 0},
                ),
            )
        )
        assert value["trace"] == ["inherit_chain", "inherit_chain", "inherit_chain"]


class TestBudget:
    def test_subset_pick_records_resolved_kind_on_allocate_child_event(self):
        ledger = BudgetLedger({"tokens": 20, "steps": 4, "depth": 3, "tool_calls": 0})
        assert_ok(
            run_step(
                {"inner_input": {"value": "x"}, "subset": ["constant"]},
                kind="subset_pick",
                options=RunOptions(provider=provider(), ledger=ledger),
            )
        )
        allocate_events = [
            event for event in ledger.events if event.kind == "allocate_child"
        ]
        assert [event.resolved_kind for event in allocate_events] == ["constant"]

    def test_random_pick_resolution_is_seed_stable_on_the_ledger(self):

        def resolved_kind_for_seed(seed: int) -> str:
            ledger = BudgetLedger(
                {"tokens": 20, "steps": 4, "depth": 3, "tool_calls": 0}
            )
            assert_ok(
                run_step(
                    {"inner_input": {"value": "x"}},
                    kind="random_pick",
                    options=RunOptions(provider=provider(), seed=seed, ledger=ledger),
                )
            )
            resolved_kind = next(
                (
                    event.resolved_kind
                    for event in ledger.events
                    if event.kind == "allocate_child"
                )
            )
            assert resolved_kind is not None
            return resolved_kind

        assert resolved_kind_for_seed(13) == resolved_kind_for_seed(13)


class TestFailure:
    def test_inherit_chain_hits_depth_floor_as_budget_denied(self):
        value = assert_ok(
            run_step(
                {"task": "descend", "depth": 3},
                kind="inherit_chain",
                options=RunOptions(
                    provider=provider(),
                    budget={"tokens": 20, "steps": 8, "depth": 2, "tool_calls": 0},
                ),
            )
        )
        assert value["trace"] == ["inherit_chain", "inherit_chain", "budget_denied"]

    def test_empty_subset_is_unresolvable_default(self):
        value = assert_ok(
            run_step(
                {"inner_input": {"value": "x"}, "subset": []},
                kind="subset_pick",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["result"]["outcome"] == "host_error"
        assert value["result"]["host_error"]["code"] == "unresolvable_default"

    def test_unknown_name_in_subset_is_unknown_kind(self):
        value = assert_ok(
            run_step(
                {"inner_input": {"value": "x"}, "subset": ["constant", "missing_kind"]},
                kind="subset_pick",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["result"]["outcome"] == "host_error"
        assert value["result"]["host_error"]["code"] == "unknown_kind"


class TestDeterminism:
    def test_subset_pick_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "subset_pick",
            {"inner_input": {"value": "x"}, "subset": ["constant"]},
            provider=provider(),
            budget={"tokens": 20, "steps": 4, "depth": 3, "tool_calls": 0},
        )
        assert len(digest) == 64
