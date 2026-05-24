"""Deterministic fake LLM used for testing Fleshwound end-to-end.

It inspects the prompt and returns canned Monty-subset Python (or plain
text) sufficient to exercise the runner without a real model call.

Routing is intentionally tiny — only the cases the tests need.
"""

from __future__ import annotations

DOCTOR_SCRIPT = r"""#!/usr/bin/env bash
# Fleshwound doctor: verify Monty and an LLM provider are available.
set -u

ok=0
fail=0

check() {
    if "$@" >/dev/null 2>&1; then
        echo "ok   : $*"
        ok=$((ok + 1))
    else
        echo "FAIL : $*"
        fail=$((fail + 1))
    fi
}

echo "fleshwound doctor"
echo "-----------------"

# 1. Monty must be importable.
check python3 -c "import pydantic_monty"

# 2. At least one LLM provider must be configured.
if [ -n "${ANTHROPIC_API_KEY:-}" ] \
   || [ -n "${OPENAI_API_KEY:-}" ] \
   || [ -n "${FLESHWOUND_FAKE_LLM:-}" ]; then
    echo "ok   : LLM provider configured"
    ok=$((ok + 1))
else
    echo "FAIL : no LLM provider (set ANTHROPIC_API_KEY, OPENAI_API_KEY, or FLESHWOUND_FAKE_LLM=1)"
    fail=$((fail + 1))
fi

echo "-----------------"
echo "passed: $ok  failed: $fail"
[ "$fail" -eq 0 ]
"""


def _monty_program_emitting_doctor() -> str:
    # Code Monty will execute. The trailing dict literal is the step's output.
    # Single-quoted f-string-free template; embed the script via repr().
    return (
        "doctor_script = " + repr(DOCTOR_SCRIPT) + "\n"
        "{\n"
        '    "status": "complete",\n'
        '    "program": doctor_script,\n'
        '    "notes": "bash doctor; checks pydantic_monty import and an LLM env var",\n'
        "}\n"
    )


def fake_llm(prompt: str) -> str:
    """Return a canned response based on simple prompt keywords."""
    p = prompt.lower()
    if "doctor" in p and "fleshwound" in p:
        return _monty_program_emitting_doctor()
    # Fallback: an empty completion that produces a partial result.
    return (
        '{"status": "partial", "program": "", "notes": "fake_llm has no canned reply for this prompt"}\n'
    )
