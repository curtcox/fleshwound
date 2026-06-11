from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._fake_provider import FakeProvider, text_result
from tests._fake_user import FakeAskUser
from tests._golden import assert_deterministic


def provider(text: str, usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


class RaisingProvider:
    def generate(self, prompt: str, *, tools=None):
        raise RuntimeError("offline")


class TestConvention:
    def test_prose_writer_returns_text_and_empty_notes_on_model_success(self):
        fake = FakeProvider(
            {"Write prose for task: greet": text_result("Hello there.")}
        )
        value = assert_ok(
            run_step(
                {"task": "greet", "context": {"tone": "warm"}},
                kind="prose_writer",
                options=RunOptions(provider=fake),
            )
        )
        assert value == {"text": "Hello there.", "notes": ""}
        assert "Context: {'tone': 'warm'}" in fake.prompts[0]

    def test_classifier_selects_matching_label_from_model_text(self):
        value = assert_ok(
            run_step(
                {"text": "ship it", "labels": ["approve", "reject"]},
                kind="classifier",
                options=RunOptions(provider=provider("I would approve this.")),
            )
        )
        assert value == {
            "label": "approve",
            "confidence": None,
            "rationale": "I would approve this.",
        }

    def test_ask_user_only_returns_queued_answer(self):
        ask_user = FakeAskUser(["blue"])
        value = assert_ok(
            run_step(
                {"question": "Favorite color?"},
                kind="ask_user_only",
                options=RunOptions(provider=provider("unused"), ask_user=ask_user),
            )
        )
        assert value == {"answer": "blue"}
        assert ask_user.questions == ["Favorite color?"]


class TestBudget:
    def test_prose_writer_charges_step_and_model_usage(self):
        ledger = BudgetLedger({"tokens": 6, "steps": 1, "depth": 1, "tool_calls": 0})
        value = assert_ok(
            run_step(
                {"task": "greet", "context": None},
                kind="prose_writer",
                options=RunOptions(provider=provider("Hi", Usage(2, 2)), ledger=ledger),
            )
        )
        assert value["text"] == "Hi"
        assert [event.kind for event in ledger.events] == [
            "create_root",
            "charge_step",
            "charge_tokens",
        ]
        assert ledger.snapshot("root").remaining.tokens == 2

    def test_ask_user_only_does_not_charge_tokens(self):
        ledger = BudgetLedger({"tokens": 0, "steps": 1, "depth": 1, "tool_calls": 0})
        assert_ok(
            run_step(
                {"question": "Continue?"},
                kind="ask_user_only",
                options=RunOptions(
                    provider=provider("unused"),
                    ask_user=FakeAskUser(["yes"]),
                    ledger=ledger,
                ),
            )
        )
        assert [event.kind for event in ledger.events] == ["create_root", "charge_step"]


class TestFailure:
    def test_prose_writer_surfaces_provider_error_as_model_error_note(self):
        value = assert_ok(
            run_step(
                {"task": "greet", "context": None},
                kind="prose_writer",
                options=RunOptions(provider=RaisingProvider()),
            )
        )
        assert value == {"text": "", "notes": "model_error"}

    def test_classifier_falls_back_to_first_label_when_no_match(self):
        value = assert_ok(
            run_step(
                {"text": "unknown", "labels": ["a", "b"]},
                kind="classifier",
                options=RunOptions(provider=provider("neither")),
            )
        )
        assert value["label"] == "a"
        assert value["rationale"] == "neither"

    def test_ask_user_unavailable_is_a_normal_value(self):
        value = assert_ok(
            run_step(
                {"question": "Continue?"},
                kind="ask_user_only",
                options=RunOptions(provider=provider("unused")),
            )
        )
        assert value == {"answer": None, "notes": "ask_user unavailable"}


class TestDeterminism:
    def test_prose_writer_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "prose_writer",
            {"task": "greet", "context": None},
            provider=provider("Hello", Usage(1, 1)),
            budget={"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0},
        )
        assert len(digest) == 64

    def test_classifier_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "classifier",
            {"text": "ship it", "labels": ["approve", "reject"]},
            provider=provider("approve", Usage(1, 1)),
            budget={"tokens": 10, "steps": 1, "depth": 1, "tool_calls": 0},
        )
        assert len(digest) == 64
