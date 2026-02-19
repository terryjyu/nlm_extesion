from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_ARGUMENT = 2
    INPUT_NOT_FOUND = 3
    PHASE_FAILED = 10
    UNEXPECTED_ERROR = 99


@dataclass
class PipelineError(Exception):
    code: ExitCode
    message: str
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {
                "code": self.code.name,
                "exit_code": int(self.code),
                "message": self.message,
            },
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload
