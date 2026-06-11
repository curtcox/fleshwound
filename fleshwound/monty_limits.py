"""Map Fleshwound compute budget to pydantic-monty resource limits."""

from __future__ import annotations

COMPUTE_MS_PER_UNIT = 0.001


def monty_limits_from_compute(compute_remaining: int) -> dict[str, float | int]:
    if compute_remaining <= 0:
        return {"max_duration_secs": 0.0, "max_recursion_depth": 1}
    return {
        "max_duration_secs": compute_remaining * COMPUTE_MS_PER_UNIT,
        "max_recursion_depth": max(2, min(compute_remaining, 1000)),
    }


def is_monty_limit_error(exc: BaseException) -> bool:
    if type(exc).__name__ != "MontyRuntimeError":
        return False
    message = str(exc)
    markers = (
        "TimeoutError",
        "RecursionError",
        "MemoryError",
        "time limit exceeded",
        "maximum recursion depth exceeded",
        "memory limit",
    )
    return any(marker in message for marker in markers)


def limit_error_message(exc: BaseException) -> str:
    return str(exc).strip() or "Compute budget exhausted."
