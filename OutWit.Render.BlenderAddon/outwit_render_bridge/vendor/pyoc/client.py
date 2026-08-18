"""The client handle: every ``oc_*`` operation as a Python method, plus the
event pump and a synchronous ``wait`` for scripts and tests.

Method names follow the C entry points without the ``oc_`` prefix and the
``_async`` suffix: asynchronous entry points return the operation id and the
outcome arrives as events from :meth:`Client.poll_event`; hosts with a UI
loop (Blender's ``bpy.app.timers``) drain events on their own cadence and
never block. Every non-OK status raises the typed :mod:`pyoc.errors` class.
"""
from __future__ import annotations

import ctypes
import json
import os
import time
from ctypes import byref, c_size_t, c_uint8
from typing import Any, Callable, Iterator

from . import _abi, events as _events
from .documents import JobRequest
from .errors import OperationFailed, Timeout, raise_for
from .library import Library, make_view, require


class Client:
    """One ``oc_client_handle``. Use as a context manager to release deterministically."""

    def __init__(self, endpoint: str, identity_url: str | None = None, *, library: Library | None = None):
        """Creates a client (``oc_client_create``).

        :param endpoint: server BASE URL, e.g. ``https://engine.omnibuscloud.com``.
        :param identity_url: WitIdentity base URL; required later by browser sign-in and credential persistence.
        :param library: an explicitly loaded :class:`Library`; defaults to the process-wide one.
        """
        self._library = library or require()
        self._handle = _abi.OC_INVALID_CLIENT
        self._endpoint = endpoint
        self._identity_url = identity_url
        self._released = False

        endpoint_view, endpoint_buffer = make_view(endpoint.encode("utf-8"))
        identity_view, identity_buffer = make_view((identity_url or "").encode("utf-8"))

        options = _abi.oc_client_options_v1()
        options.struct_size = ctypes.sizeof(_abi.oc_client_options_v1)
        options.struct_version = 1
        options.endpoint = endpoint_view
        options.identity_url = identity_view

        handle = _abi.oc_client_handle(0)
        raise_for(self._fn("oc_client_create")(byref(options), byref(handle)), "oc_client_create")
        del endpoint_buffer, identity_buffer

        self._handle = handle.value

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def release(self) -> None:
        """``oc_client_release`` — legal only when not connected (close first)."""
        if self._released:
            return
        raise_for(self._fn("oc_client_release")(self._handle), "oc_client_release")
        self._released = True

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *_exc) -> None:
        if not self._released:
            try:
                self.release()
            except Exception:
                # A still-connected client cannot be released; the caller decides how to close.
                pass

    def connect(self) -> int:
        return self._op("oc_client_connect_async")

    def close(self) -> int:
        return self._op("oc_client_close_async")

    # ------------------------------------------------------------------ #
    # Authentication and credentials
    # ------------------------------------------------------------------ #

    def login_browser(self) -> int:
        """SDK-owned browser sign-in; the host never sees the token."""
        return self._op("oc_auth_login_browser_async")

    def logout(self) -> int:
        return self._op("oc_auth_logout_async")

    def set_access_token(self, token: str) -> None:
        view, buffer = make_view(token.encode("utf-8"))
        raise_for(self._fn("oc_client_set_access_token")(self._handle, view), "oc_client_set_access_token")
        del buffer

    def credentials_attach(self, store_path: str, max_age_days: int = 0) -> None:
        """Opts into SDK-owned persistent sign-in over the shared secure store (ABI 1.6)."""
        view, buffer = make_view(os.path.abspath(store_path).encode("utf-8"))
        options = _abi.oc_credentials_options_v1()
        options.struct_size = ctypes.sizeof(_abi.oc_credentials_options_v1)
        options.struct_version = 1
        options.store_path = view
        options.max_age_days = int(max_age_days)
        raise_for(self._fn("oc_credentials_attach")(self._handle, byref(options)), "oc_credentials_attach")
        del buffer

    def credentials_detach(self, clear_persisted: bool = True) -> None:
        raise_for(self._fn("oc_credentials_detach")(self._handle, 1 if clear_persisted else 0), "oc_credentials_detach")

    def credentials_restore(self) -> int:
        return self._op("oc_credentials_restore_async")

    # ------------------------------------------------------------------ #
    # Scopes, assets, jobs
    # ------------------------------------------------------------------ #

    def scopes_list(self) -> int:
        return self._op("oc_scopes_list_async")

    def asset_upload_file(self, file_path: str) -> int:
        return self._op_view("oc_asset_upload_file_async", os.path.abspath(file_path))

    def asset_download_file(self, asset_id: str, target_path: str) -> int:
        return self._op_view_view("oc_asset_download_file_async", str(asset_id), os.path.abspath(target_path))

    def asset_query(self, asset_id: str) -> int:
        return self._op_view("oc_asset_query_async", str(asset_id))

    def job_submit(self, request: "JobRequest | dict[str, Any] | str") -> int:
        """Submits a job request document (a :class:`JobRequest`, a dict, or JSON text).
        Structure is linted locally (``InvalidArgument``); the vocabulary is the server's."""
        if isinstance(request, JobRequest):
            text = request.to_json()
        elif isinstance(request, dict):
            text = json.dumps(request, ensure_ascii=False, separators=(",", ":"))
        else:
            text = str(request)
        return self._op_view("oc_job_submit_async", text)

    def job_get(self, job_id: str) -> int:
        return self._op_view("oc_job_get_async", str(job_id))

    def job_cancel(self, job_id: str) -> int:
        return self._op_view("oc_job_cancel_async", str(job_id))

    def job_download_result(self, job_id: str, target_path: str) -> int:
        return self._op_view_view("oc_job_download_result_async", str(job_id), os.path.abspath(target_path))

    def job_get_variable(self, job_id: str, variable: str) -> int:
        return self._op_view_view("oc_job_get_variable_async", str(job_id), variable)

    # ------------------------------------------------------------------ #
    # Operations and events
    # ------------------------------------------------------------------ #

    def operation_cancel(self, operation: int) -> None:
        raise_for(self._fn("oc_operation_cancel")(self._handle, int(operation)), "oc_operation_cancel")

    def poll_event(self) -> _events.Event | None:
        """One pending event or ``None`` (``OC_BUFFER_TOO_SMALL`` retried with the required size)."""
        poll = self._fn("oc_event_poll")
        capacity = 4096
        buffer = (c_uint8 * capacity)()
        written = c_size_t(0)

        while True:
            status = poll(self._handle, buffer, capacity, byref(written))
            if status == _abi.OC_NO_EVENT:
                return None
            if status == _abi.OC_BUFFER_TOO_SMALL:
                capacity = max(written.value, capacity * 2)
                buffer = (c_uint8 * capacity)()
                continue
            raise_for(status, "oc_event_poll")
            raw = bytes(buffer[: max(0, written.value - 1)]).decode("utf-8", errors="replace")
            return _events.Event.parse(raw)

    def drain_events(self) -> Iterator[_events.Event]:
        """Yields every pending event without blocking."""
        while True:
            event = self.poll_event()
            if event is None:
                return
            yield event

    def wait(
        self,
        operation: int,
        timeout: float | None = 300.0,
        *,
        on_event: Callable[[_events.Event], None] | None = None,
        interval: float = 0.05,
    ) -> dict[str, Any]:
        """Blocks until ``operation`` reaches a terminal event; returns the completion
        payload or raises :class:`OperationFailed`. Other events seen meanwhile go to
        ``on_event`` (progress, connection state, other operations' outcomes).
        For scripts and tests — UI hosts pump :meth:`poll_event` instead."""
        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            event = self.poll_event()
            if event is None:
                if deadline is not None and time.monotonic() > deadline:
                    raise Timeout(f"operation {operation} did not finish within {timeout} s", entry_point="wait")
                time.sleep(interval)
                continue

            if event.operation == operation and event.is_terminal:
                if event.is_completed:
                    return event.payload
                raise OperationFailed(event.status or _abi.OC_INTERNAL_ERROR, event.message, operation, json.loads(event.raw))

            if on_event is not None:
                on_event(event)

    # ------------------------------------------------------------------ #
    # Tools
    # ------------------------------------------------------------------ #

    def _fn(self, name: str):
        return self._library.fn(name)

    def _op(self, name: str) -> int:
        operation = _abi.oc_operation_id(0)
        raise_for(self._fn(name)(self._handle, byref(operation)), name)
        return operation.value

    def _op_view(self, name: str, text: str) -> int:
        view, buffer = make_view(text.encode("utf-8"))
        operation = _abi.oc_operation_id(0)
        raise_for(self._fn(name)(self._handle, view, byref(operation)), name)
        del buffer
        return operation.value

    def _op_view_view(self, name: str, first: str, second: str) -> int:
        first_view, first_buffer = make_view(first.encode("utf-8"))
        second_view, second_buffer = make_view(second.encode("utf-8"))
        operation = _abi.oc_operation_id(0)
        raise_for(self._fn(name)(self._handle, first_view, second_view, byref(operation)), name)
        del first_buffer, second_buffer
        return operation.value

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def handle(self) -> int:
        return self._handle

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def identity_url(self) -> str | None:
        return self._identity_url

    @property
    def released(self) -> bool:
        return self._released
