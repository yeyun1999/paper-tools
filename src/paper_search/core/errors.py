"""Exception hierarchy mapped to CLI exit codes and structured error codes."""

from __future__ import annotations

from typing import Any, ClassVar


class PaperSearchError(Exception):
    """Base error carrying a machine-readable code, exit code, and details."""

    code: ClassVar[str] = "INTERNAL"
    exit_code: ClassVar[int] = 1

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details


class UsageError(PaperSearchError):
    code: ClassVar[str] = "USAGE"
    exit_code: ClassVar[int] = 2


class UpstreamError(PaperSearchError):
    code: ClassVar[str] = "UPSTREAM"
    exit_code: ClassVar[int] = 3


class NotFoundError(PaperSearchError):
    code: ClassVar[str] = "NOT_FOUND"
    exit_code: ClassVar[int] = 3


class FullTextUnavailableError(PaperSearchError):
    code: ClassVar[str] = "FULLTEXT_UNAVAILABLE"
    exit_code: ClassVar[int] = 4


class ConfigError(PaperSearchError):
    code: ClassVar[str] = "CONFIG"
    exit_code: ClassVar[int] = 5


class PluginError(PaperSearchError):
    code: ClassVar[str] = "PLUGIN"
    exit_code: ClassVar[int] = 1
