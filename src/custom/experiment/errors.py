"""Distinguish execution failures from scored Agent mistakes."""


class ExecutionFailure(RuntimeError):
    """The environment could not execute a trajectory reliably."""
    def __init__(self, message, unknown_outcome=False):
        super().__init__(message)
        self.unknown_outcome = unknown_outcome


class ToolMistake(ValueError):
    """A rejected Agent request is feedback, not an unavailable environment."""
    def __init__(self, message, raw_response=None):
        super().__init__(message)
        self.raw_response = raw_response


class Cancelled(BaseException):
    """Cooperative cancellation must bypass per-task error handlers."""


class CheckpointFailure(BaseException):
    """Never dispatch another request after losing the durable writer."""
