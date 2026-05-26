"""Internal host exceptions used to preserve contract-shaped failures."""

from __future__ import annotations


class HostError(Exception):
    """Request that the runner return a specific host_error envelope."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
