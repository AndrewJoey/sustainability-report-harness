"""Shared structured error contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class HarnessError(Exception):
    """A user-actionable Harness failure."""

    code: str
    message: str
    path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        location = f" [{self.path}]" if self.path else ""
        return f"{self.code}{location}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }
        if self.path is not None:
            result["error"]["path"] = self.path
        return result


def require(condition: bool, code: str, message: str, path: str | None = None) -> None:
    """Raise a structured validation error when a condition is false."""

    if not condition:
        raise HarnessError(code=code, message=message, path=path)
