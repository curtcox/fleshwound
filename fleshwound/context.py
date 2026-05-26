"""Run context exposed to catalog executors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .budget import BudgetLedger
from .catalog import Catalog
from .provider import ModelProvider


@dataclass(frozen=True)
class RunContext:
    ledger: BudgetLedger
    budget_id: str
    kind: str
    provider: ModelProvider
    catalog_obj: Catalog
    seed: int
    default_policy: Any
    ask_user: Callable[[str], str] | None
    _step_fn: Callable[..., dict[str, Any]]
    _llm_fn: Callable[[str], dict[str, Any]]

    @property
    def catalog(self) -> Mapping[str, str]:
        return self.catalog_obj.conventions

    def budget(self) -> dict[str, Any]:
        return self.ledger.monty_snapshot(self.budget_id)

    def llm(self, prompt: str) -> dict[str, Any]:
        return self._llm_fn(prompt)

    def step(
        self,
        input: Any,
        request: dict[str, int],
        *,
        kind: str | None = None,
        default_policy: Any = None,
        provider: ModelProvider | None = None,
        ask_user: Callable[[str], str] | None = None,
    ) -> dict[str, Any]:
        return self._step_fn(
            input,
            request,
            kind=kind,
            default_policy=self.default_policy if default_policy is None else default_policy,
            provider=self.provider if provider is None else provider,
            ask_user=self.ask_user if ask_user is None else ask_user,
        )

