from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fleshwound.runner import DEFAULT_BUDGET, run_step


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def assert_deterministic(
    kind: str,
    input: Any,
    *,
    provider,
    budget=DEFAULT_BUDGET,
    seed: int = 0,
    golden_path: Path | None = None,
    record: bool = False,
) -> str:
    first = run_step(input, budget, provider, kind=kind, seed=seed)
    second = run_step(input, budget, provider, kind=kind, seed=seed)
    assert first == second
    digest = _hash(first["value"] if first["outcome"] == "ok" else first)
    if golden_path is not None:
        if record:
            golden_path.parent.mkdir(parents=True, exist_ok=True)
            golden_path.write_text(json.dumps({"hash": digest, "input": input, "value_sample": first.get("value")}, indent=2, sort_keys=True))
        else:
            assert json.loads(golden_path.read_text())["hash"] == digest
    return digest

