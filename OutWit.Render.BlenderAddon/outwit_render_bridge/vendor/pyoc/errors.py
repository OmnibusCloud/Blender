"""Typed errors mapped from ``oc_status``.

Addon and host code never sees raw status codes: every non-OK return of an
entry point raises the subclass for that status, and a failed asynchronous
operation surfaces as :class:`OperationFailed` carrying the payload's status
and bounded diagnostic.
"""
from __future__ import annotations

from . import _abi


class OcError(Exception):
    """Base of every error raised by pyoc; ``status`` is the numeric ``oc_status``."""

    status: int = _abi.OC_INTERNAL_ERROR

    def __init__(self, message: str = "", *, status: int | None = None, entry_point: str | None = None):
        if status is not None:
            self.status = status
        self.entry_point = entry_point
        text = message or _abi.STATUS_NAMES.get(self.status, f"oc_status {self.status}")
        if entry_point:
            text = f"{entry_point}: {text}"
        super().__init__(text)

    @property
    def status_name(self) -> str:
        return _abi.STATUS_NAMES.get(self.status, f"oc_status {self.status}")


class BufferTooSmall(OcError):
    status = _abi.OC_BUFFER_TOO_SMALL


class InvalidArgument(OcError):
    status = _abi.OC_INVALID_ARGUMENT


class InvalidHandle(OcError):
    status = _abi.OC_INVALID_HANDLE


class InvalidState(OcError):
    status = _abi.OC_INVALID_STATE


class NotConnected(OcError):
    status = _abi.OC_NOT_CONNECTED


class Unauthorized(OcError):
    status = _abi.OC_UNAUTHORIZED


class NotFound(OcError):
    status = _abi.OC_NOT_FOUND


class Conflict(OcError):
    status = _abi.OC_CONFLICT


class Cancelled(OcError):
    status = _abi.OC_CANCELLED


class Timeout(OcError):
    status = _abi.OC_TIMEOUT


class NetworkError(OcError):
    status = _abi.OC_NETWORK_ERROR


class ProtocolError(OcError):
    status = _abi.OC_PROTOCOL_ERROR


class IoError(OcError):
    status = _abi.OC_IO_ERROR


class InternalError(OcError):
    status = _abi.OC_INTERNAL_ERROR


class LibraryError(OcError):
    """The native library could not be loaded, is the wrong ABI major, or lacks an entry point."""

    status = _abi.OC_IO_ERROR


_BY_STATUS: dict[int, type[OcError]] = {
    _abi.OC_BUFFER_TOO_SMALL: BufferTooSmall,
    _abi.OC_INVALID_ARGUMENT: InvalidArgument,
    _abi.OC_INVALID_HANDLE: InvalidHandle,
    _abi.OC_INVALID_STATE: InvalidState,
    _abi.OC_NOT_CONNECTED: NotConnected,
    _abi.OC_UNAUTHORIZED: Unauthorized,
    _abi.OC_NOT_FOUND: NotFound,
    _abi.OC_CONFLICT: Conflict,
    _abi.OC_CANCELLED: Cancelled,
    _abi.OC_TIMEOUT: Timeout,
    _abi.OC_NETWORK_ERROR: NetworkError,
    _abi.OC_PROTOCOL_ERROR: ProtocolError,
    _abi.OC_IO_ERROR: IoError,
    _abi.OC_INTERNAL_ERROR: InternalError,
}


def error_for(status: int, message: str = "", *, entry_point: str | None = None) -> OcError:
    """The typed error for a status (unknown values map to :class:`InternalError`)."""
    cls = _BY_STATUS.get(status, InternalError)
    error = cls(message, entry_point=entry_point)
    error.status = status
    return error


def raise_for(status: int, entry_point: str) -> None:
    """Raises the typed error unless ``status`` is ``OC_OK``."""
    if status != _abi.OC_OK:
        raise error_for(status, entry_point=entry_point)


class OperationFailed(OcError):
    """An asynchronous operation ended in ``operation-failed``.

    ``status`` is the payload's category, ``message`` its bounded diagnostic,
    ``operation`` the operation id, ``event`` the raw envelope.
    """

    def __init__(self, status: int, message: str, operation: int, event: dict):
        super().__init__(message or _abi.STATUS_NAMES.get(status, ""), status=status)
        self.operation = operation
        self.event = event

    @property
    def is_cancelled(self) -> bool:
        return self.status == _abi.OC_CANCELLED
