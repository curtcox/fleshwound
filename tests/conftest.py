from __future__ import annotations

import pytest

from fleshwound.budget import BudgetLedger
from fleshwound.runner import DEFAULT_BUDGET


def pytest_addoption(parser):
    parser.addoption("--record", action="store_true", default=False)


@pytest.fixture
def record_mode(request) -> bool:
    return bool(request.config.getoption("--record"))


def make_ledger(limit=None) -> BudgetLedger:
    return BudgetLedger(limit or DEFAULT_BUDGET)


def assert_ok(result):
    assert result["outcome"] == "ok", result
    return result["value"]


def assert_host_error(result, code=None):
    assert result["outcome"] == "host_error", result
    if code is not None:
        assert result["host_error"]["code"] == code, result
    return result["host_error"]

