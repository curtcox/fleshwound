from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_rlm_loop_kind_and_protocol_docs_exist():
    kind_doc = (ROOT / "docs/specs/rlm-loop-kind.md").read_text()
    protocol_doc = (ROOT / "docs/specs/rlm-action-protocol.md").read_text()

    assert "rlm_loop" in kind_doc
    assert "max_iterations" in kind_doc
    assert "strict_protocol" in kind_doc
    assert "trace" in kind_doc

    assert "fleshwound-rlm-action/1" in protocol_doc
    for action in ["answer", "step", "llm", "think", "fail"]:
        assert f"`{action}`" in protocol_doc
    assert "assign" in protocol_doc
    assert "over-budget" in protocol_doc
