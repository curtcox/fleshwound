from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.catalog import Catalog
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok


class RaisingProvider:
    def generate(self, prompt: str, *, tools=None):
        raise RuntimeError("provider unavailable")


def register_llm_probe() -> Catalog:
    catalog = Catalog()

    @catalog.register("llm_probe", convention="prompt -> ctx.llm result")
    def llm_probe(input, ctx):
        return ctx.llm(input["prompt"])

    @catalog.register("llm_then_value", convention="calls llm and returns normal value")
    def llm_then_value(input, ctx):
        first = ctx.llm(input["prompt"])
        second = ctx.llm(input["prompt"])
        return {"first": first["status"], "second": second["status"], "done": True}

    return catalog


class TestConvention:
    def test_llm_success_returns_always_dict_shape(self):
        catalog = register_llm_probe()
        provider = CallableProvider(
            lambda prompt: ModelTextResult("hello", Usage(2, 3))
        )
        value = assert_ok(
            run_step(
                {"prompt": "say hello"},
                kind="llm_probe",
                options=RunOptions(
                    budget={"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0},
                    provider=provider,
                    catalog=catalog,
                ),
            )
        )
        assert value == {
            "status": "ok",
            "text": "hello",
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            "error": None,
        }


class TestBudget:
    def test_llm_success_charges_reported_total_tokens(self):
        catalog = register_llm_probe()
        ledger = BudgetLedger({"tokens": 7, "steps": 1, "depth": 1, "tool_calls": 0})
        provider = CallableProvider(
            lambda prompt: ModelTextResult("hello", Usage(2, 3))
        )
        run_step(
            {"prompt": "say hello"},
            kind="llm_probe",
            options=RunOptions(provider=provider, catalog=catalog, ledger=ledger),
        )
        assert [event.kind for event in ledger.events] == [
            "create_root",
            "charge_step",
            "charge_tokens",
        ]
        assert ledger.events[-1].amount == {"tokens": 5}
        assert ledger.snapshot("root").remaining.tokens == 2

    def test_multiple_llm_calls_accumulate_charges(self):
        catalog = register_llm_probe()
        ledger = BudgetLedger({"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0})
        provider = CallableProvider(
            lambda prompt: ModelTextResult("hello", Usage(1, 2))
        )
        value = assert_ok(
            run_step(
                {"prompt": "twice"},
                kind="llm_then_value",
                options=RunOptions(provider=provider, catalog=catalog, ledger=ledger),
            )
        )
        assert value == {"first": "ok", "second": "ok", "done": True}
        assert [
            event.amount for event in ledger.events if event.kind == "charge_tokens"
        ] == [{"tokens": 3}, {"tokens": 3}]
        assert ledger.snapshot("root").remaining.tokens == 4


class TestFailure:
    def test_provider_exception_is_data_and_step_can_still_succeed(self):
        catalog = register_llm_probe()
        ledger = BudgetLedger({"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0})
        value = assert_ok(
            run_step(
                {"prompt": "one two three"},
                kind="llm_probe",
                options=RunOptions(
                    provider=RaisingProvider(), catalog=catalog, ledger=ledger
                ),
            )
        )
        assert value["status"] == "error"
        assert value["text"] == ""
        assert value["usage"] == {
            "prompt_tokens": 3,
            "completion_tokens": 0,
            "total_tokens": 3,
        }
        assert value["error"]["code"] == "provider_error"
        assert ledger.events[-1].kind == "charge_tokens"
        assert ledger.events[-1].amount == {"tokens": 3}

    def test_token_exhaustion_inside_llm_is_data_not_host_error(self):
        catalog = register_llm_probe()
        provider = CallableProvider(
            lambda prompt: ModelTextResult("too much", Usage(4, 4))
        )
        value = assert_ok(
            run_step(
                {"prompt": "overspend"},
                kind="llm_probe",
                options=RunOptions(
                    budget={"tokens": 3, "steps": 1, "depth": 1, "tool_calls": 0},
                    provider=provider,
                    catalog=catalog,
                ),
            )
        )
        assert value["status"] == "error"
        assert value["error"]["code"] == "budget_exhausted"


class TestDeterminism:
    def test_provider_results_are_deterministic_for_same_provider_and_input(self):
        catalog = register_llm_probe()
        provider = CallableProvider(
            lambda prompt: ModelTextResult(prompt.upper(), Usage(1, 1))
        )
        budget = {"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0}
        first = run_step(
            {"prompt": "stable"},
            kind="llm_probe",
            options=RunOptions(budget=budget, provider=provider, catalog=catalog),
        )
        second = run_step(
            {"prompt": "stable"},
            kind="llm_probe",
            options=RunOptions(budget=budget, provider=provider, catalog=catalog),
        )
        assert first == second
