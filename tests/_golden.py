from __future__ import annotations
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from fleshwound.runner import RunOptions, DEFAULT_BUDGET, run_step

GOLDEN_ROOT = Path(__file__).with_name("_goldens")


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _json_sample(value: Any) -> Any:
    try:
        json.dumps(value, sort_keys=True)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _json_sample(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_json_sample(item) for item in value]
        if isinstance(value, tuple):
            return [_json_sample(item) for item in value]
        return repr(value)


def _default_golden_path(kind: str) -> Path:
    current_test = os.environ.get("PYTEST_CURRENT_TEST", "unknown_test").split(" ", 1)[
        0
    ]
    test_name = current_test.rsplit("::", 1)[-1]
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", test_name).strip("_") or "unknown_test"
    return GOLDEN_ROOT / kind / f"{slug}.json"


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
    golden_path = golden_path or _default_golden_path(kind)
    record = record or "--record" in sys.argv
    first = run_step(
        input,
        kind=kind,
        options=RunOptions(budget=budget, provider=provider, seed=seed),
    )
    second = run_step(
        input,
        kind=kind,
        options=RunOptions(budget=budget, provider=provider, seed=seed),
    )
    assert first == second
    digest = _hash(first["value"] if first["outcome"] == "ok" else first)
    if record:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(
            json.dumps(
                {
                    "hash": digest,
                    "input": _json_sample(input),
                    "value_sample": _json_sample(first.get("value")),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    else:
        assert json.loads(golden_path.read_text())["hash"] == digest
    return digest
