from __future__ import annotations

import json

from fleshwound.budget import BudgetLedger
from fleshwound.catalog import catalog
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import HOST_ERROR_CODES, run_step

from conftest import assert_ok
from tests._golden import assert_deterministic


def _minimal_input(name: str):
    from fleshwound.kinds._minimal_input import minimal_input

    return minimal_input(name)


def test_every_registered_kind_has_json_serializable_minimal_result():
    for name in sorted(catalog.entries):
        ledger = BudgetLedger({"tokens": 1_000_000, "steps": 300, "depth": 8, "tool_calls": 100})

        result = run_step(_minimal_input(name), kind=name, ledger=ledger)

        json.dumps(result, sort_keys=True)


def test_every_registered_kind_charges_host_step_on_entry():
    for name in sorted(catalog.entries):
        ledger = BudgetLedger({"tokens": 1_000_000, "steps": 300, "depth": 8, "tool_calls": 100})

        run_step(_minimal_input(name), kind=name, ledger=ledger)

        assert any(event.kind == "charge_step" and event.budget_id == "root" for event in ledger.events), name


def test_every_host_error_code_is_reachable_from_catalog_fixture():
    observed = set()
    for code in HOST_ERROR_CODES:
        result = run_step({"code": code}, kind="always_host_error")
        if result["outcome"] == "host_error":
            observed.add(result["host_error"]["code"])

    assert observed == HOST_ERROR_CODES


def test_catalog_self_test_runs_full_catalog_without_unexpected_host_errors():
    value = assert_ok(
        run_step(
            {"kinds_to_exercise": None},
            kind="catalog_self_test",
            budget={"tokens": 1_000_000, "steps": 600, "depth": 8, "tool_calls": 200},
        )
    )

    exercised = {row["kind"] for row in value["results"]}
    assert exercised == set(catalog.entries) - {"catalog_self_test"}
    assert value["unexpected_host_errors"] == []


def test_every_registered_kind_has_regression_canary_golden():
    provider = CallableProvider(lambda prompt: ModelTextResult("{}", Usage(1, 1)))

    for name in sorted(catalog.entries):
        digest = assert_deterministic(
            name,
            _minimal_input(name),
            provider=provider,
            budget={"tokens": 1_000_000, "steps": 600, "depth": 8, "tool_calls": 200},
        )

        assert len(digest) == 64
