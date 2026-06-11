from __future__ import annotations


class FakeAskUser:
    def __init__(self, answers):
        self.answers = list(answers)
        self.questions: list[str] = []

    def __call__(self, question: str) -> str:
        self.questions.append(question)
        if not self.answers:
            raise AssertionError(f"No fake answer queued for: {question}")
        return self.answers.pop(0)
