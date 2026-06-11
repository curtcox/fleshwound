"""End-to-end test: Fleshwound must be able to write a working doctor script.

The test fails unless:
  1. The Fleshwound runner produces a step output dict via Monty.
  2. The dict's `program` is a runnable bash script.
  3. That script, executed against an environment where Monty is importable
     and an LLM provider env var is set, exits 0 and reports both checks.
  4. The same script, executed without an LLM provider env var, exits non-zero.
"""

from __future__ import annotations
import os
import stat
import subprocess
import sys
from pathlib import Path
import pytest
from fleshwound.fake_llm import fake_llm
from fleshwound.provider import CallableProvider
from fleshwound.runner import RunOptions, run_step

TASK = "Write a doctor script for fleshwound (a bash script) that verifies the two pieces required to run fleshwound are available: Monty (the pydantic_monty Python package) and an LLM provider (an API key env var). Exit 0 if both are present, non-zero otherwise."


@pytest.fixture(scope="module")
def doctor_script(tmp_path_factory) -> Path:
    result = run_step(
        {"task": TASK, "context": None, "output_schema": None},
        kind="program_writer",
        options=RunOptions(provider=CallableProvider(fake_llm)),
    )
    assert isinstance(result, dict), (
        f"runner did not return an envelope dict: {result!r}"
    )
    assert result.get("outcome") == "ok", f"step host failed: {result!r}"
    value = result.get("value")
    assert isinstance(value, dict), f"step value is not a dict: {result!r}"
    assert value.get("status") == "complete", f"step did not complete: {result!r}"
    program = value.get("program") or ""
    assert program.strip(), "step produced an empty program"
    assert program.lstrip().startswith("#!"), "program is not a script with a shebang"
    assert "pydantic_monty" in program, "doctor must check pydantic_monty"
    assert (
        "ANTHROPIC_API_KEY" in program
        or "OPENAI_API_KEY" in program
        or "FLESHWOUND_FAKE_LLM" in program
    ), "doctor must check for an LLM provider env var"
    path = tmp_path_factory.mktemp("doctor") / "doctor.sh"
    path.write_text(program)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


_LLM_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FLESHWOUND_FAKE_LLM")


def _base_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_KEYS}
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    return env


def _run_doctor(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=30
    )


def test_doctor_passes_when_environment_is_healthy(doctor_script: Path) -> None:
    env = _base_env()
    env["FLESHWOUND_FAKE_LLM"] = "1"
    proc = _run_doctor(doctor_script, env)
    assert proc.returncode == 0, (
        f"doctor failed in a healthy env\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "pydantic_monty" in proc.stdout
    assert "LLM provider configured" in proc.stdout


def test_doctor_fails_when_llm_provider_missing(doctor_script: Path) -> None:
    env = _base_env()
    proc = _run_doctor(doctor_script, env)
    assert proc.returncode != 0, (
        f"doctor should fail without an LLM env var\nstdout:\n{proc.stdout}"
    )
    assert "no LLM provider" in proc.stdout
