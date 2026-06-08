"""Threading helpers so the addon never blocks Blender's UI thread on bridge I/O.

Blender's Python API is NOT thread-safe: worker threads here do ONLY network / subprocess /
pure-Python work and must never touch `bpy`. Results are read back on the main thread (from a
modal operator timer or a `bpy.app.timers` callback) and only there written into addon state.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from .bridge_client import BridgeClient

# Job statuses that mean "no more progress will come".
TERMINAL_STATUSES = {"Completed", "Failed", "Cancelled"}


class AsyncCall:
    """Runs a 0-arg callable on a daemon thread.

    The callable MUST NOT touch the bpy API — only HTTP (BridgeClient), subprocess, or pure
    Python. Poll :pyattr:`done` from a timer/modal on the main thread, then read
    :pyattr:`result` / :pyattr:`error`.
    """

    def __init__(self, fn: Callable[[], Any]):
        self._fn = fn
        self._result: Any = None
        self._error: Optional[BaseException] = None
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "AsyncCall":
        self._thread.start()
        return self

    def _run(self) -> None:
        try:
            self._result = self._fn()
        except BaseException as ex:  # noqa: BLE001 - marshalled back to the main thread
            self._error = ex
        finally:
            self._done.set()

    @property
    def done(self) -> bool:
        return self._done.is_set()

    @property
    def result(self) -> Any:
        return self._result

    @property
    def error(self) -> Optional[BaseException]:
        return self._error


class JobMonitor:
    """Background poller for a single job.

    Polls ``GetJob`` off the main thread at an adaptive interval and keeps the latest response in
    a thread-safe slot. The UI timer reads :pymeth:`snapshot` and applies it on the main thread
    (cheap, no I/O), so progress no longer lags behind a fixed main-thread poll. Stops itself once
    the job reaches a terminal status.
    """

    def __init__(self, context_directory: str, job_id: str, interval_seconds: float):
        self._client = BridgeClient(context_directory)
        self._job_id = job_id
        self._interval = max(0.5, float(interval_seconds))
        self._lock = threading.Lock()
        self._latest: Any = None
        self._error: Optional[BaseException] = None
        self._terminal = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "JobMonitor":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                response = self._client.get_job(self._job_id)
                with self._lock:
                    self._latest = response
                    self._error = None
                status = str(getattr(response, "status", ""))
                if status in ("Failed", "Cancelled"):
                    with self._lock:
                        self._terminal = True
                    break
                if status == "Completed":
                    # Keep polling through the finalize race: the server marks Completed before the
                    # result blob is materialised; stop only once the blob is actually available so the
                    # addon can enable download.
                    has_result = bool(getattr(response, "result_blob_id", "")) or any(
                        getattr(response, "result_blob_ids", []) or []
                    )
                    if has_result:
                        with self._lock:
                            self._terminal = True
                        break
            except BaseException as ex:  # noqa: BLE001 - surfaced via snapshot()
                with self._lock:
                    self._error = ex
            self._stop.wait(self._interval)

    def snapshot(self) -> tuple[Any, Optional[BaseException], bool]:
        """Returns (latest GetJobResponse|None, last error|None, reached_terminal)."""
        with self._lock:
            return self._latest, self._error, self._terminal

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def stop(self) -> None:
        self._stop.set()
