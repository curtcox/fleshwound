from __future__ import annotations

import re

from fleshwound.provider import ModelTextResult, Usage


class FakeProviderUnmatched(AssertionError):
    def __init__(self, prompt: str) -> None:
        super().__init__(f"FakeProvider has no match for prompt:\n{prompt}")
        self.prompt = prompt


class FakeProvider:
    def __init__(self, patterns: dict[str, ModelTextResult | str]) -> None:
        self.patterns = patterns
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, tools=None) -> ModelTextResult:
        self.prompts.append(prompt)
        for pattern, result in self.patterns.items():
            if re.search(pattern, prompt, re.S):
                if isinstance(result, ModelTextResult):
                    return result
                return ModelTextResult(str(result), Usage(prompt_tokens=len(prompt.split())))
        raise FakeProviderUnmatched(prompt)


def text_result(text: str, prompt_tokens: int = 1, completion_tokens: int = 1) -> ModelTextResult:
    return ModelTextResult(text, Usage(prompt_tokens, completion_tokens))
