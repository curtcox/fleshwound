from __future__ import annotations

import pytest

from fleshwound.budget import BudgetLedger
from fleshwound.catalog import catalog
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import run_step

from conftest import assert_host_error, assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "unused") -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, Usage(prompt_tokens=1)))


class TestConvention:
    def test_constant_returns_input_value_verbatim(self):
        result = run_step({"value": {"nested": [1, True, None]}}, provider=provider(), kind="constant")

        assert assert_ok(result) == {"nested": [1, True, None]}

    def test_echo_returns_whole_input_verbatim(self):
        value = {"value": "not special", "other": [1, 2]}

        result = run_step(value, provider=provider(), kind="echo")

        assert assert_ok(result) == value

    def test_group_a_kinds_are_registered_with_conventions(self):
        for name in ("constant", "echo", "noop_fail"):
            entry = catalog.lookup(name)
            assert entry.name == name
            assert entry.convention


class TestBudget:
    def test_constant_charges_only_the_step(self):
        ledger = BudgetLedger({"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0})

        result = run_step({"value": "x"}, provider=provider(), kind="constant", ledger=ledger)

        assert assert_ok(result) == "x"
        assert [(event.kind, event.amount) for event in ledger.events] == [
            ("create_root", {"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0}),
            ("charge_step", {"steps": 1}),
        ]

    def test_echo_refuses_when_step_budget_is_exhausted(self):
        ledger = BudgetLedger({"tokens": 0, "steps": 0, "depth": 1, "tool_calls": 0})

        result = run_step({"x": 1}, provider=provider(), kind="echo", ledger=ledger)

        assert_host_error(result, "budget_exhausted")
        assert ledger.events[-1].kind == "deny"
        assert ledger.events[-1].amount == {"steps": 1}


class TestFailure:
    def test_noop_fail_is_wrapped_as_executor_error(self):
        result = run_step({}, provider=provider(), kind="noop_fail")

        error = assert_host_error(result, "executor_error")
        assert "deliberate noop_fail" in error["message"]

    def test_constant_malformed_input_is_wrapped_as_executor_error(self):
        result = run_step({}, provider=provider(), kind="constant")

        error = assert_host_error(result, "executor_error")
        assert "KeyError" in error["message"]

    def test_non_jsonable_success_value_is_malformed_result(self):
        def returns_object(input, ctx):
            return object()

        from fleshwound.catalog import Catalog

        local_catalog = Catalog()
        local_catalog.register("object_value", convention="returns object")(returns_object)

        result = run_step({}, provider=provider(), kind="object_value", catalog=local_catalog)

        assert_host_error(result, "malformed_result")


@pytest.mark.integration
class TestEndToEnd:
    def test_constant_runs_through_runner_entrypoint(self):
        result = run_step({"value": ["runner", "path"]}, provider=provider(), kind="constant")

        assert assert_ok(result) == ["runner", "path"]

    def test_echo_runs_without_touching_provider(self):
        calls = []
        fake = CallableProvider(lambda prompt: calls.append(prompt) or "unused")

        result = run_step({"hello": "world"}, provider=fake, kind="echo")

        assert assert_ok(result) == {"hello": "world"}
        assert calls == []


class TestDeterminism:
    def test_constant_is_deterministic(self):
        digest = assert_deterministic(
            "constant",
            {"value": {"a": [1, 2], "b": "c"}},
            provider=provider(),
            budget={"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0},
        )

        assert len(digest) == 64

    def test_echo_is_deterministic(self):
        digest = assert_deterministic(
            "echo",
            {"a": [1, 2], "b": "c"},
            provider=provider(),
            budget={"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0},
        )

        assert len(digest) == 64
