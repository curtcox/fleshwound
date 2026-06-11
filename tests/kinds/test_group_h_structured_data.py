from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


PROGRAM_RESPONSE = (
    '```python\n{"program": "def generated():\\n    return 1", "notes": "ok"}\n```'
)


class TestConvention:
    def test_function_map_writer_returns_sources_keyed_by_signature_names(self):
        value = assert_ok(
            run_step(
                {
                    "signatures": {
                        "alpha": {
                            "signature": "alpha() -> int",
                            "docstring": "Return one.",
                        },
                        "beta": {
                            "signature": "beta() -> int",
                            "docstring": "Return one.",
                        },
                    },
                    "context": {"module": "demo"},
                },
                kind="function_map_writer",
                options=RunOptions(
                    provider=provider(PROGRAM_RESPONSE),
                    budget={"tokens": 1000, "steps": 8, "depth": 4, "tool_calls": 0},
                ),
            )
        )
        assert sorted(value["functions"]) == ["alpha", "beta"]
        assert value["functions"]["alpha"]["source"].startswith("def generated")
        assert value["missing"] == []

    def test_function_map_editor_tracks_added_removed_and_updated_entries(self):
        value = assert_ok(
            run_step(
                {
                    "current": {
                        "old": {"source": "keep"},
                        "gone": {"source": "remove"},
                    },
                    "edits": [
                        {"name": "gone", "instruction": "remove"},
                        {"name": "old", "instruction": "updated"},
                        {"name": "new", "instruction": "added"},
                    ],
                },
                kind="function_map_editor",
                options=RunOptions(provider=provider()),
            )
        )
        assert value["updated"] == {
            "old": {"source": "updated"},
            "new": {"source": "added"},
        }
        assert value["removed"] == ["gone"]
        assert value["added"] == ["new"]

    def test_schema_diff_and_patch_set_parse_structured_model_json(self):
        schema = assert_ok(
            run_step(
                {"domain": "todo", "examples": [{"title": "x"}]},
                kind="schema_designer",
                options=RunOptions(
                    provider=provider(
                        '{"schema": {"type": "object"}, "rationale": "small"}'
                    )
                ),
            )
        )
        diff = assert_ok(
            run_step(
                {"file": "a.txt", "content": "old", "change": "new"},
                kind="diff_writer",
                options=RunOptions(
                    provider=provider('{"diff": "--- a\\n+++ b", "format": "unified"}')
                ),
            )
        )
        patch_set = assert_ok(
            run_step(
                {"files": {"a.txt": "old"}, "task": "change"},
                kind="patch_set_writer",
                options=RunOptions(
                    provider=provider('{"patches": [{"path": "a.txt", "diff": "@@"}]}')
                ),
            )
        )
        assert schema == {"schema": {"type": "object"}, "rationale": "small"}
        assert diff == {"diff": "--- a\n+++ b", "format": "unified"}
        assert patch_set == {"patches": [{"path": "a.txt", "diff": "@@"}]}

    def test_ast_transform_round_trips_nested_ast_data(self):
        ast = {
            "type": "Module",
            "body": [{"type": "Expr", "value": {"type": "Name", "id": "x"}}],
        }
        value = assert_ok(
            run_step(
                {"ast": ast, "transform": "leave unchanged"},
                kind="ast_transform",
                options=RunOptions(provider=provider()),
            )
        )
        assert value == {"ast": ast, "changes": ["leave unchanged"]}


class TestBudget:
    def test_function_map_writer_fans_out_once_per_signature_and_refunds_children(self):
        ledger = BudgetLedger({"tokens": 1000, "steps": 8, "depth": 4, "tool_calls": 0})
        assert_ok(
            run_step(
                {
                    "signatures": {
                        "alpha": {"signature": "alpha() -> int"},
                        "beta": {"signature": "beta() -> int"},
                    }
                },
                kind="function_map_writer",
                options=RunOptions(
                    provider=provider(PROGRAM_RESPONSE, Usage(4, 4)), ledger=ledger
                ),
            )
        )
        close_ids = [
            event.budget_id for event in ledger.events if event.kind == "close_child"
        ]
        resolved = [
            event.resolved_kind
            for event in ledger.events
            if event.kind == "allocate_child"
        ]
        assert close_ids == ["root.1", "root.2"]
        assert resolved == ["program_writer", "program_writer"]
        assert sum((1 for event in ledger.events if event.kind == "refund_child")) == 2

    def test_schema_designer_charges_model_usage(self):
        ledger = BudgetLedger({"tokens": 20, "steps": 2, "depth": 1, "tool_calls": 0})
        assert_ok(
            run_step(
                {"domain": "todo"},
                kind="schema_designer",
                options=RunOptions(
                    provider=provider('{"schema": {}}', Usage(3, 4)), ledger=ledger
                ),
            )
        )
        assert any(
            (
                event.kind == "charge_tokens" and event.amount == {"tokens": 7}
                for event in ledger.events
            )
        )


class TestFailure:
    def test_function_map_writer_marks_failed_child_as_missing(self):
        value = assert_ok(
            run_step(
                {"signatures": {"bad": {"signature": "bad()"}}},
                kind="function_map_writer",
                options=RunOptions(
                    provider=provider("raise Exception('bad program')"),
                    budget={"tokens": 1000, "steps": 4, "depth": 3, "tool_calls": 0},
                ),
            )
        )
        assert value == {"functions": {}, "missing": ["bad"]}

    def test_schema_designer_falls_back_when_model_returns_non_json(self):
        value = assert_ok(
            run_step(
                {"domain": "todo"},
                kind="schema_designer",
                options=RunOptions(provider=provider("plain rationale")),
            )
        )
        assert value == {"schema": {}, "rationale": "plain rationale"}

    def test_patch_set_writer_falls_back_to_empty_patch_list_on_non_json(self):
        value = assert_ok(
            run_step(
                {"files": {"a.txt": "old"}, "task": "change"},
                kind="patch_set_writer",
                options=RunOptions(provider=provider("not json")),
            )
        )
        assert value == {"patches": []}


class TestDeterminism:
    def test_function_map_editor_is_deterministic(self):
        digest = assert_deterministic(
            "function_map_editor",
            {
                "current": {"a": {"source": "old"}},
                "edits": [{"name": "a", "instruction": "new"}],
            },
            provider=provider(),
        )
        assert len(digest) == 64

    def test_patch_set_writer_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "patch_set_writer",
            {"files": {"a.txt": "old"}, "task": "change"},
            provider=provider('{"patches": [{"path": "a.txt", "diff": "@@"}]}'),
        )
        assert len(digest) == 64
