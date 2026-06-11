from __future__ import annotations
from fleshwound.budget import BudgetLedger
from fleshwound.provider import CallableProvider, ModelTextResult, Usage
from fleshwound.runner import RunOptions, run_step
from conftest import assert_ok
from tests._golden import assert_deterministic


def provider(text: str = "unused", usage: Usage | None = None) -> CallableProvider:
    return CallableProvider(lambda prompt: ModelTextResult(text, usage or Usage(1, 1)))


PROGRAM_RESPONSE = '```python\n{"program": "virtual tree summary", "notes": "ok"}\n```'


class TestConvention:
    def test_directory_input_delegates_virtual_tree_as_program_context(self):
        value = assert_ok(
            run_step(
                {
                    "tree": {"src/app.py": {"content": "print(1)", "mode": "0644"}},
                    "task": "Summarize this tree",
                },
                kind="directory_input",
                options=RunOptions(
                    provider=provider(PROGRAM_RESPONSE),
                    budget={"tokens": 1000, "steps": 4, "depth": 3, "tool_calls": 0},
                ),
            )
        )
        assert value["outcome"] == "ok"
        assert value["value"] == {"program": "virtual tree summary", "notes": "ok"}

    def test_directory_writer_returns_tree_and_notes_from_model_json(self):
        value = assert_ok(
            run_step(
                {"task": "Create a small package", "shape": "tree"},
                kind="directory_writer",
                options=RunOptions(
                    provider=provider(
                        '{"tree": {"README.md": {"content": "# Demo", "mode": "0644"}}, "notes": "one file"}'
                    )
                ),
            )
        )
        assert value == {
            "tree": {"README.md": {"content": "# Demo", "mode": "0644"}},
            "notes": "one file",
        }

    def test_repo_walker_runs_only_matching_virtual_files(self):
        value = assert_ok(
            run_step(
                {
                    "tree": {
                        "src/app.py": {"content": "print(1)", "mode": "0644"},
                        "README.md": {"content": "# Demo", "mode": "0644"},
                    },
                    "per_file_kind": "echo",
                    "predicate": "input['path'].endswith('.py')",
                },
                kind="repo_walker",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 4, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        assert sorted(value["per_file"]) == ["src/app.py"]
        assert value["per_file"]["src/app.py"]["value"]["path"] == "src/app.py"

    def test_patch_applier_proxy_splits_applied_and_rejected_patches(self):
        value = assert_ok(
            run_step(
                {
                    "patches": [
                        {"path": "src/app.py", "diff": "@@ -1 +1"},
                        {"path": "", "diff": "@@"},
                        {"path": "README.md", "diff": ""},
                    ]
                },
                kind="patch_applier_proxy",
            )
        )
        assert value == {
            "applied": ["src/app.py"],
            "rejected": [
                {"path": "", "reason": "missing path"},
                {"path": "README.md", "reason": "missing diff"},
            ],
        }


class TestBudget:
    def test_repo_walker_fans_out_once_per_matching_path_and_refunds_children(self):
        ledger = BudgetLedger({"tokens": 0, "steps": 6, "depth": 3, "tool_calls": 0})
        assert_ok(
            run_step(
                {
                    "tree": {
                        "a.py": {"content": "a"},
                        "b.py": {"content": "b"},
                        "notes.txt": {"content": "skip"},
                    },
                    "per_file_kind": "echo",
                    "predicate": "input['path'].endswith('.py')",
                },
                kind="repo_walker",
                options=RunOptions(ledger=ledger),
            )
        )
        assert [
            event.resolved_kind
            for event in ledger.events
            if event.kind == "allocate_child"
        ] == ["echo", "echo"]
        assert [
            event.budget_id for event in ledger.events if event.kind == "close_child"
        ] == ["root.1", "root.2"]
        assert sum((1 for event in ledger.events if event.kind == "refund_child")) == 2

    def test_repo_walker_surfaces_budget_denied_for_large_fan_out(self):
        value = assert_ok(
            run_step(
                {
                    "tree": {f"{idx}.py": {"content": str(idx)} for idx in range(3)},
                    "per_file_kind": "echo",
                    "predicate": "True",
                },
                kind="repo_walker",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 1, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        assert [result["outcome"] for result in value["per_file"].values()] == [
            "host_error",
            "host_error",
            "host_error",
        ]
        assert {
            result["host_error"]["code"] for result in value["per_file"].values()
        } == {"budget_denied"}


class TestFailure:
    def test_directory_writer_falls_back_on_non_json_model_text(self):
        value = assert_ok(
            run_step(
                {"task": "Create files", "shape": "tree"},
                kind="directory_writer",
                options=RunOptions(provider=provider("plain notes")),
            )
        )
        assert value == {"tree": {}, "notes": "plain notes"}

    def test_repo_walker_records_predicate_errors_as_rejections(self):
        value = assert_ok(
            run_step(
                {
                    "tree": {"a.py": {"content": "a"}},
                    "per_file_kind": "echo",
                    "predicate": "input['missing']",
                },
                kind="repo_walker",
                options=RunOptions(
                    budget={"tokens": 0, "steps": 4, "depth": 2, "tool_calls": 0}
                ),
            )
        )
        assert value == {
            "per_file": {},
            "skipped": [{"path": "a.py", "reason": "predicate_error"}],
        }


class TestDeterminism:
    def test_directory_writer_is_deterministic_with_frozen_provider(self):
        digest = assert_deterministic(
            "directory_writer",
            {"task": "Create a small package", "shape": "tree"},
            provider=provider(
                '{"tree": {"README.md": {"content": "# Demo", "mode": "0644"}}, "notes": "one file"}'
            ),
        )
        assert len(digest) == 64

    def test_repo_walker_is_deterministic(self):
        digest = assert_deterministic(
            "repo_walker",
            {
                "tree": {"a.py": {"content": "a"}, "b.txt": {"content": "b"}},
                "per_file_kind": "echo",
                "predicate": "input['path'].endswith('.py')",
            },
            provider=provider(),
            budget={"tokens": 0, "steps": 4, "depth": 2, "tool_calls": 0},
        )
        assert len(digest) == 64
