"""Typed errors used by the router and CLI."""

from __future__ import annotations


class AEEPError(Exception):
    """Base error for expected AEEP failures."""


class ConfigurationError(AEEPError):
    """The manifest or runtime configuration is invalid."""


class InputValidationError(AEEPError):
    """Action input does not satisfy the capability schema."""


class NoRouteError(AEEPError):
    """No executor satisfies the action constraints."""


class ApprovalRequired(AEEPError):
    """The selected action has side effects beyond the approved level."""

    def __init__(self, message: str, *, executor_id: str, required_level: str) -> None:
        super().__init__(message)
        self.executor_id = executor_id
        self.required_level = required_level


class ExecutionFailed(AEEPError):
    """All safe execution attempts failed."""


class ExecutorError(AEEPError):
    """An executor failed before producing a successful result."""


class ProtocolError(AEEPError):
    """An MCP or other wire-protocol operation failed."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        status_code: int | None = None,
        data: object | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.data = data
