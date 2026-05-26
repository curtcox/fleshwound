from __future__ import annotations

import pytest

from fleshwound.budget import BudgetLedger
from fleshwound.catalog import Catalog
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import run_step

from conftest import assert_host_error, assert_ok


def provider(text="ok", usage=None):
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


def test_budget_ledger_allocates_refunds_and_orders_events():
    ledger = BudgetLedger({"tokens": 10, "steps": 4, "depth": 3, "tool_calls": 1})
    child = ledger.allocate_child(
        "root",
        {"tokens": 5, "steps": 2, "depth": 1, "tool_calls": 0},
        "allocate_child kind=echo",
        resolved_kind="echo",
    )
    assert child == "root.1"
    assert ledger.charge_step(child, "run kind=echo")
    ledger.close_child(child)
    assert [event.kind for event in ledger.events] == [
        "create_root",
        "allocate_child",
        "charge_step",
        "refund_child",
        "close_child",
    ]
    assert ledger.events[1].resolved_kind == "echo"
    assert ledger.events[1].to_dict()["resolved_kind"] == "echo"
    assert ledger.snapshot("root").remaining.steps == 3


def test_catalog_registration_and_duplicate_rejection():
    catalog = Catalog()

    @catalog.register("x", convention="x")
    def x(input, ctx):
        return input

    assert catalog.lookup("x").executor is x
    assert catalog.conventions["x"] == "x"
    with pytest.raises(TypeError):
        catalog.conventions["x"] = "mutate"
    with pytest.raises(ValueError):
        catalog.register("x", convention="again")(x)


def test_constant_echo_and_failure_envelopes():
    budget = {"tokens": 0, "steps": 3, "depth": 2, "tool_calls": 0}
    assert_ok(run_step({"value": {"a": 1}}, budget, provider(), kind="constant")) == {"a": 1}
    assert_ok(run_step(["x"], budget, provider(), kind="echo")) == ["x"]
    assert_host_error(run_step({}, budget, provider(), kind="noop_fail"), "executor_error")


def test_llm_charges_usage_and_returns_value():
    result = run_step(
        {"task": "say hi", "context": None},
        {"tokens": 5, "steps": 2, "depth": 2, "tool_calls": 0},
        provider("hi", Usage(2, 2)),
        kind="prose_writer",
    )
    assert assert_ok(result)["text"] == "hi"


def test_unknown_kind_and_unresolvable_default_are_host_errors():
    budget = {"tokens": 0, "steps": 2, "depth": 2, "tool_calls": 0}
    assert_host_error(run_step({}, budget, provider(), kind="missing"), "unknown_kind")
    assert_host_error(run_step({}, budget, provider(), kind=None), "unresolvable_default")


def test_default_policy_resolution_is_recorded_on_allocate_child_event():
    ledger = BudgetLedger({"tokens": 0, "steps": 4, "depth": 3, "tool_calls": 0})
    result = run_step(
        {"inner_input": {"value": "picked"}, "subset": ["constant"]},
        provider=provider(),
        kind="subset_pick",
        ledger=ledger,
    )

    assert assert_ok(result)["result"]["value"] == "picked"
    allocations = [event for event in ledger.events if event.kind == "allocate_child"]
    assert len(allocations) == 1
    assert allocations[0].resolved_kind == "constant"
