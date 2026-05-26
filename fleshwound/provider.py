"""Model provider protocol and small adapters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int | None = None

    def to_dict(self) -> dict[str, int]:
        total = (
            self.total_tokens
            if self.total_tokens is not None
            else self.prompt_tokens + self.completion_tokens
        )
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": total,
        }


@dataclass(frozen=True)
class ModelTextResult:
    text: str
    usage: Usage = Usage()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    content: Any


class ModelProvider(Protocol):
    def generate(self, prompt: str, *, tools: list[ToolSpec] | None = None) -> ModelTextResult:
        ...


class CallableProvider:
    def __init__(self, fn: Callable[[str], str | ModelTextResult]) -> None:
        self._fn = fn

    def generate(self, prompt: str, *, tools: list[ToolSpec] | None = None) -> ModelTextResult:
        result = self._fn(prompt)
        if isinstance(result, ModelTextResult):
            return result
        return ModelTextResult(text=str(result), usage=Usage(prompt_tokens=len(prompt.split())))

