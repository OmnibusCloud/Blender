"""The in-process client: the ``BridgeClient`` surface over the OmnibusCloud native SDK.

Same function names, same signatures, same ``bridge_models`` return shapes as
``bridge_client.BridgeClient`` — the operators, panels and their tests do not
know which one they hold (05-blender-sdk-migration.md, section 7). Underneath
there is no companion process, no loopback REST, no lease: ``pyoc`` (the
SDK's Python face, vendored under ``vendor/``) drives ``omnibuscloud_native``
in this process, and every launch is one job request document (section 4).

Blender-free by construction: no ``bpy`` here. The Blender-specific event
pump lives with the operators; this module keeps a small state machine that
folds SDK events whenever a status call comes in, so the snapshot-shaped
status model the panel already consumes keeps working unchanged.

Behaviour worth stating:

- The lease trio (``acquire_lease`` / ``ping_lease`` / ``release_lease``) and
  ``get_bridge_status`` answer from process-local state; the companion-process
  machinery has no in-process counterpart and these calls exist for the
  transition only.
- Uploads keep the blocking signature the workers use; the background
  variants map onto SDK operations keyed by ``transfer_id``.
- Validate and preflight keep the bridge's submit-and-wait shape (five
  submits for preflight); the results come back through the document door as
  value documents of the published render vocabulary.
- Render settings persist in a small JSON file next to the session store —
  the same per-user location the bridge used — until they move to addon
  preferences (05, section 7.4).
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .bridge_models import (
    AcquireLeaseResponse,
    BeginSignInResponse,
    BridgeStatusResponse,
    DownloadedResultItemResponse,
    DownloadResultResponse,
    DownloadStatusResponse,
    ExecutionGroupOptionResponse,
    ExecutionProjectOptionResponse,
    ExecutionScopeOptionsResponse,
    GetJobResponse,
    RenderPreflightData,
    RenderPreflightFramesData,
    RenderPreflightResponse,
    RenderPreflightStillTiledData,
    RenderPreflightVideoData,
    RenderSettingsResponse,
    RenderValidateBlendResponse,
    RunRenderResponse,
    SessionStateResponse,
    UploadBlendResponse,
    UploadStatusResponse,
)
from .vendor import pyoc
from .vendor import render_documents as render

# Job scripts (the Render controller family; names are the wire contract).
SCRIPT_VALIDATE_BLEND = "RenderValidateBlend"
SCRIPT_RUNTIME_DIAGNOSTICS = "RenderRuntimeDiagnostics"
SCRIPT_PREFLIGHT_STILL = "RenderPreflightStill"
SCRIPT_PREFLIGHT_FRAMES = "RenderPreflightFrames"
SCRIPT_PREFLIGHT_STILL_TILED = "RenderPreflightStillTiled"
SCRIPT_PREFLIGHT_VIDEO = "RenderPreflightVideo"
SCRIPT_RENDER_STILL = "RenderStill"
SCRIPT_RENDER_STILL_TILED = "RenderStillTiled"
SCRIPT_RENDER_FRAMES = "RenderFrames"
SCRIPT_RENDER_VIDEO = "RenderVideo"
SCRIPT_BAKE_STILL = "BakeAndRenderStill"
SCRIPT_BAKE_STILL_TILED = "BakeAndRenderStillTiled"
SCRIPT_BAKE_FRAMES = "BakeAndRenderFrames"
SCRIPT_BAKE_VIDEO = "BakeAndRenderVideo"

RESULT_VARIABLE = "result"

# The engine suffix the bake scripts carry (there is no engine-agnostic BakeAndRender*).
_ENGINE_SUFFIX = {0: "Cycles", 1: "Eevee", 2: "GreasePencil"}

_TERMINAL_JOB_STATES = ("Completed", "Failed", "Cancelled", "Canceled")


class EmbeddedClientError(Exception):
    """Same role as ``BridgeClientError``: the message an operator shows."""


@dataclass
class _Transfer:
    """A background upload or download tracked by operation id."""

    operation: int
    kind: str
    file_name: str
    total_bytes: int = 0
    completed_bytes: int = 0
    status: str = "InProgress"
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    target_path: str = ""


class EmbeddedBridgeClient:
    """``BridgeClient`` over ``pyoc`` — one native client per addon process.

    Construct once and keep (the native library is process-lifetime); the
    factory in ``bridge_operators`` owns the singleton.
    """

    def __init__(
        self,
        server_url: str,
        identity_url: str,
        *,
        library_path: str | None = None,
        session_store_path: str | None = None,
        settings_path: str | None = None,
        download_directory: str | None = None,
        remember_sign_in: bool = True,
        client_factory: Callable[..., Any] | None = None,
        addon_version: str = "",
    ):
        self._lock = threading.RLock()
        self._server_url = server_url
        self._identity_url = identity_url
        self._session_store_path = session_store_path
        self._settings_path = settings_path
        self._download_directory = download_directory or os.path.join(os.path.expanduser("~"), "OmnibusCloud", "Renders")
        self._remember_sign_in = remember_sign_in
        self._addon_version = addon_version

        self._library = pyoc.load(library_path) if client_factory is None else None
        self._client = (client_factory or pyoc.Client)(server_url, identity_url)

        self._signed_in = False
        self._connected = False
        self._connecting = False
        self._last_error: str | None = None
        self._pending_login: int | None = None
        self._pending_connect: int | None = None
        self._transfers: dict[int, _Transfer] = {}
        self._downloads_by_job: dict[str, int] = {}
        self._session_restored_tried = False

        if self._session_store_path and self._remember_sign_in:
            try:
                self._client.credentials_attach(self._session_store_path)
            except pyoc.OcError as ex:
                self._last_error = str(ex)

    # ------------------------------------------------------------------ #
    # Process / session (the transition surface)
    # ------------------------------------------------------------------ #

    def get_bridge_status(self) -> BridgeStatusResponse:
        with self._lock:
            self._pump()
            version = self._library.sdk_version if self._library is not None else "embedded"
            return BridgeStatusResponse(
                bridge_version=f"embedded {version}",
                is_signed_in=self._signed_in,
                is_connected_to_cloud=self._connected,
                current_user_display_name=None,
                current_user_id=None,
                last_error=self._last_error,
            )

    def begin_sign_in(self) -> BeginSignInResponse:
        with self._lock:
            self._pump()
            if self._signed_in:
                return BeginSignInResponse(started=False, requires_browser=False, message="Already signed in.")
            if self._pending_login is not None:
                return BeginSignInResponse(started=True, requires_browser=True, message="Sign-in already in progress.")
            try:
                if self._session_store_path and self._remember_sign_in and not self._session_restored_tried:
                    self._session_restored_tried = True
                    try:
                        self._client.wait(self._client.credentials_restore(), timeout=60)
                        self._signed_in = True
                        self._start_connect()
                        return BeginSignInResponse(started=True, requires_browser=False, message="Session restored.")
                    except pyoc.OperationFailed:
                        pass
                self._pending_login = self._client.login_browser()
            except pyoc.OcError as ex:
                self._last_error = str(ex)
                raise EmbeddedClientError(str(ex)) from ex
            return BeginSignInResponse(started=True, requires_browser=True, message="Complete the sign-in in your browser.")

    def sign_out(self) -> bool:
        with self._lock:
            self._pump()
            try:
                if self._connected or self._connecting:
                    self._client.wait(self._client.close(), timeout=30)
                self._client.wait(self._client.logout(), timeout=30)
            except pyoc.OcError as ex:
                self._last_error = str(ex)
            self._signed_in = False
            self._connected = False
            self._connecting = False
            self._pending_login = None
            self._pending_connect = None
            return True

    def get_session_state(self) -> SessionStateResponse:
        with self._lock:
            self._pump()
            return SessionStateResponse(
                is_signed_in=self._signed_in,
                display_name=None,
                user_id=None,
                can_launch=self._signed_in and self._connected,
                needs_interactive_login=not self._signed_in and self._pending_login is None,
                last_error=self._last_error,
            )

    def get_execution_scope_options(self) -> ExecutionScopeOptionsResponse:
        with self._lock:
            self._ensure_connected()
            scopes = self._wait(self._client.scopes_list(), "scopes")["scopes"]
            return ExecutionScopeOptionsResponse(
                can_run_on_all_clients=bool(scopes.get("canRunOnAllClients")),
                groups=[
                    ExecutionGroupOptionResponse(group_id=str(g.get("groupId") or ""), name=str(g.get("name") or ""), description=g.get("description"))
                    for g in scopes.get("groups") or []
                ],
                projects=[
                    ExecutionProjectOptionResponse(
                        project_id=str(p.get("projectId") or ""), name=str(p.get("name") or ""), description=p.get("description"),
                        assigned_group_id=p.get("assignedGroupId"), assigned_group_name=p.get("assignedGroupName"))
                    for p in scopes.get("projects") or []
                ],
            )

    def acquire_lease(self, owner_process_id: int, lease_id: str, addon_version: str | None = None) -> AcquireLeaseResponse:
        return AcquireLeaseResponse(lease_accepted=True, lease_id=lease_id, heartbeat_interval_seconds=5, lease_timeout_seconds=0, message="embedded")

    def ping_lease(self, lease_id: str) -> bool:
        return True

    def release_lease(self, lease_id: str) -> bool:
        return True

    # ------------------------------------------------------------------ #
    # Uploads
    # ------------------------------------------------------------------ #

    def upload_blend(self, file_path: str) -> UploadBlendResponse:
        return self._upload_blocking(file_path)

    def upload_file(self, file_path: str) -> UploadBlendResponse:
        return self._upload_blocking(file_path)

    def start_upload_blend(self, file_path: str) -> UploadStatusResponse:
        return self._start_upload(file_path)

    def start_upload_file(self, file_path: str) -> UploadStatusResponse:
        return self._start_upload(file_path)

    def get_upload_status(self, transfer_id: str) -> UploadStatusResponse:
        with self._lock:
            self._pump()
            transfer = self._transfer(transfer_id)
            return self._upload_status(transfer)

    def cancel_upload(self, transfer_id: str) -> bool:
        with self._lock:
            transfer = self._transfer(transfer_id)
            try:
                self._client.operation_cancel(transfer.operation)
            except pyoc.OcError:
                return False
            return True

    # ------------------------------------------------------------------ #
    # Validate / preflight (submit-and-wait, as the bridge did)
    # ------------------------------------------------------------------ #

    def run_render_validate_blend(
        self,
        scene_blob_id: str,
        attached_files: list[dict[str, Any]] | None = None,
        selected_client_group_id: str = "",
        selected_project_id: str = "",
    ) -> RenderValidateBlendResponse:
        request = pyoc.JobRequest(SCRIPT_VALIDATE_BLEND).param(_scene_ref(scene_blob_id, attached_files))
        _scope(request, selected_client_group_id, selected_project_id)
        job = self._submit_and_wait(request)
        if job.get("status") != "Completed":
            return RenderValidateBlendResponse(job_id=job["jobId"], completed=False, status=str(job.get("status") or ""), message=job.get("errorMessage"))
        value = self._read_variable(job["jobId"], RESULT_VARIABLE)
        data = json.loads(value) if isinstance(value, str) else (value or {})
        return RenderValidateBlendResponse(
            job_id=job["jobId"],
            completed=True,
            is_valid=bool(_ci(data, "isValid")),
            issues=[str(x) for x in _ci(data, "issues") or []],
            warnings=[str(x) for x in _ci(data, "warnings") or []],
            status="Completed",
        )

    def run_render_preflight(
        self,
        frame: int,
        start_frame: int,
        end_frame: int,
        tiles_x: int,
        tiles_y: int,
        options: dict[str, Any],
        tile_options: dict[str, Any],
        video: dict[str, Any],
        selected_client_group_id: str = "",
        selected_project_id: str = "",
    ) -> RenderPreflightResponse:
        render_options = _render_options(options)
        tile = _tile_options(tile_options)
        video_options = _video_options(video)

        def run(script: str, *params: Any) -> Any:
            request = pyoc.JobRequest(script).params(*params)
            _scope(request, selected_client_group_id, selected_project_id)
            job = self._submit_and_wait(request)
            if job.get("status") != "Completed":
                raise EmbeddedClientError(job.get("errorMessage") or f"{script} ended in {job.get('status')}")
            return self._read_variable(job["jobId"], RESULT_VARIABLE)

        try:
            run(SCRIPT_RUNTIME_DIAGNOSTICS)
            still = run(SCRIPT_PREFLIGHT_STILL, int(frame), render_options)
            frames = run(SCRIPT_PREFLIGHT_FRAMES, int(start_frame), int(end_frame), render_options)
            tiled = run(SCRIPT_PREFLIGHT_STILL_TILED, int(tiles_x), int(tiles_y), render_options, tile)
            video_result = run(SCRIPT_PREFLIGHT_VIDEO, render_options, video_options)
        except EmbeddedClientError as ex:
            return RenderPreflightResponse(completed=False, status="Failed", message=str(ex))

        result = RenderPreflightData(
            still=_frames_data(still),
            frames=_frames_data(frames),
            still_tiled=_tiled_data(tiled),
            video=_video_data(video_result),
        )
        result.can_render_all = all(part is not None and part.can_render for part in (result.still, result.frames, result.still_tiled, result.video))
        return RenderPreflightResponse(completed=True, status="Completed", result=result)

    # ------------------------------------------------------------------ #
    # Launches: one job request document each
    # ------------------------------------------------------------------ #

    def run_render_still(self, scene_blob_id, frame, options, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(SCRIPT_RENDER_STILL, selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(frame), _render_options(options))

    def run_render_still_tiled(self, scene_blob_id, frame, tiles_x, tiles_y, options, tile_options, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(SCRIPT_RENDER_STILL_TILED, selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(frame), int(tiles_x), int(tiles_y), _render_options(options), _tile_options(tile_options))

    def run_render_frames(self, scene_blob_id, start_frame, end_frame, options, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(SCRIPT_RENDER_FRAMES, selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(start_frame), int(end_frame), _render_options(options))

    def run_render_video(self, scene_blob_id, start_frame, end_frame, options, video, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(SCRIPT_RENDER_VIDEO, selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(start_frame), int(end_frame), _render_options(options), _video_options(video))

    # Bake-and-render: engine-specific script names; the bake options are the addon's
    # defaults (the bridge passed the model defaults too) and sit BEFORE tile/video.
    def run_bake_and_render_still(self, scene_blob_id, frame, options, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(_bake_script(SCRIPT_BAKE_STILL, options), selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(frame), _render_options(options), _bake_options())

    def run_bake_and_render_still_tiled(self, scene_blob_id, frame, tiles_x, tiles_y, options, tile_options, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(_bake_script(SCRIPT_BAKE_STILL_TILED, options), selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(frame), int(tiles_x), int(tiles_y), _render_options(options), _bake_options(), _tile_options(tile_options))

    def run_bake_and_render_frames(self, scene_blob_id, start_frame, end_frame, options, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(_bake_script(SCRIPT_BAKE_FRAMES, options), selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(start_frame), int(end_frame), _render_options(options), _bake_options())

    def run_bake_and_render_video(self, scene_blob_id, start_frame, end_frame, options, video, attached_files=None, selected_client_group_id="", selected_project_id=""):
        return self._launch(_bake_script(SCRIPT_BAKE_VIDEO, options), selected_client_group_id, selected_project_id,
                            _scene_ref(scene_blob_id, attached_files), int(start_frame), int(end_frame), _render_options(options), _bake_options(), _video_options(video))

    # ------------------------------------------------------------------ #
    # Jobs and results
    # ------------------------------------------------------------------ #

    def get_job(self, job_id: str) -> GetJobResponse:
        with self._lock:
            self._ensure_connected()
            job = self._wait(self._client.job_get(job_id), "job status")["job"]
            status = str(job.get("status") or "")
            return GetJobResponse(
                job_id=str(job.get("jobId") or job_id),
                script_name=str(job.get("scriptName") or ""),
                status=status,
                overall_progress=float(job.get("progress") or 0.0),
                distributed_progress=float(job.get("progress") or 0.0),
                is_completed=status in _TERMINAL_JOB_STATES,
                error_message=job.get("errorMessage"),
            )

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            self._ensure_connected()
            try:
                self._wait(self._client.job_cancel(job_id), "job cancel")
            except EmbeddedClientError:
                return False
            return True

    def download_result(self, job_id: str) -> DownloadResultResponse:
        with self._lock:
            self.start_download_result(job_id)
            transfer = self._transfers[self._downloads_by_job[job_id]]
        while True:
            with self._lock:
                self._pump()
                if transfer.status != "InProgress":
                    break
            time.sleep(0.2)
        if transfer.status != "Completed":
            raise EmbeddedClientError(transfer.error or "Result download did not complete.")
        return self._download_response(job_id, transfer)

    def start_download_result(self, job_id: str) -> DownloadStatusResponse:
        with self._lock:
            self._ensure_connected()
            existing = self._downloads_by_job.get(job_id)
            if existing is not None and self._transfers[existing].status == "InProgress":
                return self._download_status(self._transfers[existing])
            directory = os.path.join(self._download_directory, job_id)
            os.makedirs(directory, exist_ok=True)
            target = os.path.join(directory, "result.bin")
            operation = self._client.job_download_result(job_id, target)
            transfer = _Transfer(operation=operation, kind="download", file_name=os.path.basename(target), target_path=target)
            transfer.payload["jobId"] = job_id
            self._transfers[operation] = transfer
            self._downloads_by_job[job_id] = operation
            return self._download_status(transfer)

    def get_download_result_status(self, job_id: str) -> DownloadStatusResponse:
        with self._lock:
            self._pump()
            operation = self._downloads_by_job.get(job_id)
            if operation is None:
                return DownloadStatusResponse(job_id=job_id, status="NotStarted")
            return self._download_status(self._transfers[operation])

    def cancel_download_result(self, job_id: str) -> bool:
        with self._lock:
            operation = self._downloads_by_job.get(job_id)
            if operation is None:
                return False
            try:
                self._client.operation_cancel(operation)
            except pyoc.OcError:
                return False
            return True

    # ------------------------------------------------------------------ #
    # Render settings (file-backed until they move to addon preferences)
    # ------------------------------------------------------------------ #

    def get_render_settings(self) -> RenderSettingsResponse:
        path = self._settings_path
        if not path or not os.path.isfile(path):
            return RenderSettingsResponse()
        try:
            with open(path, encoding="utf-8") as handle:
                return RenderSettingsResponse.from_json(json.load(handle))
        except (OSError, ValueError):
            return RenderSettingsResponse()

    def set_render_settings(self, settings: dict[str, Any]) -> bool:
        path = self._settings_path
        if not path:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, indent=2)
        return True

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _pump(self) -> None:
        """Folds pending SDK events into the process-local state (call under the lock)."""
        for event in self._client.drain_events():
            self._fold(event)

    def _fold(self, event: Any) -> None:
        if event.type == pyoc.events.CONNECTION_STATE:
            self._connected = event.state == "connected"
            self._connecting = event.state == "connecting"
            return
        if event.type == pyoc.events.AUTHORIZATION_REQUIRED:
            self._signed_in = False
            self._last_error = "Sign-in expired; sign in again."
            return
        if event.operation is None:
            return
        if event.operation == self._pending_login and event.is_terminal:
            self._pending_login = None
            if event.is_completed:
                self._signed_in = True
                self._last_error = None
                self._start_connect()
            else:
                self._last_error = event.message or "Sign-in failed."
            return
        if event.operation == self._pending_connect and event.is_terminal:
            self._pending_connect = None
            if event.is_completed:
                self._connected = True
                self._last_error = None
            else:
                self._connected = False
                self._last_error = event.message or "Could not connect to OmnibusCloud."
            return
        transfer = self._transfers.get(event.operation)
        if transfer is None:
            return
        if event.type == pyoc.events.OPERATION_PROGRESS:
            transfer.completed_bytes = int(event.payload.get("completedBytes") or 0)
            transfer.total_bytes = int(event.payload.get("totalBytes") or transfer.total_bytes)
        elif event.is_completed:
            transfer.status = "Completed"
            transfer.payload.update(event.payload)
        elif event.is_failed:
            transfer.status = "Cancelled" if event.status == pyoc.OC_CANCELLED else "Failed"
            transfer.error = event.message or "Transfer failed."

    def _start_connect(self) -> None:
        if self._connected or self._pending_connect is not None:
            return
        try:
            self._pending_connect = self._client.connect()
            self._connecting = True
        except pyoc.OcError as ex:
            self._last_error = str(ex)

    def _ensure_connected(self) -> None:
        self._pump()
        if self._connected:
            return
        if not self._signed_in:
            raise EmbeddedClientError("Sign in to OmnibusCloud first.")
        if self._pending_connect is None:
            self._start_connect()
        if self._pending_connect is None:
            raise EmbeddedClientError(self._last_error or "Could not connect to OmnibusCloud.")
        self._wait(self._pending_connect, "connect")
        self._pending_connect = None
        self._connected = True

    def _wait(self, operation: int, what: str, timeout: float | None = 300.0) -> dict[str, Any]:
        try:
            return self._client.wait(operation, timeout=timeout, on_event=self._fold)
        except pyoc.OperationFailed as ex:
            if ex.status == pyoc.OC_UNAUTHORIZED:
                self._signed_in = False
            raise EmbeddedClientError(f"{what} failed: {ex}") from ex
        except pyoc.OcError as ex:
            raise EmbeddedClientError(f"{what} failed: {ex}") from ex

    def _submit(self, request: Any) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            try:
                operation = self._client.job_submit(request)
            except pyoc.OcError as ex:
                raise EmbeddedClientError(str(ex)) from ex
            return self._wait(operation, "job submit")["job"]

    def _launch(self, script: str, group_id: str, project_id: str, *params: Any) -> RunRenderResponse:
        request = pyoc.JobRequest(script).params(*params)
        _scope(request, group_id, project_id)
        job = self._submit(request)
        return RunRenderResponse(job_id=job["jobId"], status="Submitted", message=f"{script} launched successfully.")

    def _submit_and_wait(self, request: Any, poll: float = 1.5, timeout: float = 900.0) -> dict[str, Any]:
        job = self._submit(request)
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                current = self._wait(self._client.job_get(job["jobId"]), "job status")["job"]
            if str(current.get("status") or "") in _TERMINAL_JOB_STATES:
                return current
            if time.monotonic() > deadline:
                raise EmbeddedClientError(f"{request.script} did not finish within {int(timeout)} s")
            time.sleep(poll)

    def _read_variable(self, job_id: str, variable: str) -> Any:
        with self._lock:
            payload = self._wait(self._client.job_get_variable(job_id, variable), f"read {variable}")
        document = payload.get("value") or {}
        if document.get("kind") == "document":
            return render.from_value_document(document)
        return document.get("value")

    def _upload_blocking(self, file_path: str) -> UploadBlendResponse:
        status = self._start_upload(file_path)
        transfer = self._transfer(status.transfer_id)
        delay = 0.05
        while True:
            with self._lock:
                self._pump()
                if transfer.status != "InProgress":
                    break
            time.sleep(delay)
            delay = min(delay * 2, 0.5)
        if transfer.status != "Completed" or transfer.payload.get("asset") is None:
            raise EmbeddedClientError(transfer.error or f"Upload did not complete (status: {transfer.status}).")
        return self._upload_result(transfer)

    def _start_upload(self, file_path: str) -> UploadStatusResponse:
        with self._lock:
            self._ensure_connected()
            try:
                operation = self._client.asset_upload_file(file_path)
            except pyoc.OcError as ex:
                raise EmbeddedClientError(str(ex)) from ex
            transfer = _Transfer(operation=operation, kind="upload", file_name=os.path.basename(file_path),
                                 total_bytes=os.path.getsize(file_path) if os.path.isfile(file_path) else 0)
            self._transfers[operation] = transfer
            return self._upload_status(transfer)

    def _transfer(self, transfer_id: str) -> _Transfer:
        try:
            return self._transfers[int(transfer_id)]
        except (KeyError, ValueError) as ex:
            raise EmbeddedClientError(f"Unknown transfer {transfer_id!r}.") from ex

    def _upload_result(self, transfer: _Transfer) -> UploadBlendResponse:
        asset = transfer.payload.get("asset") or {}
        return UploadBlendResponse(uploaded=True, blob_id=str(asset.get("assetId") or ""), file_name=transfer.file_name,
                                   file_size=int(asset.get("size") or transfer.total_bytes), message="Uploaded.")

    def _upload_status(self, transfer: _Transfer) -> UploadStatusResponse:
        return UploadStatusResponse(
            transfer_id=str(transfer.operation), status=transfer.status, file_name=transfer.file_name, total_bytes=transfer.total_bytes,
            result=self._upload_result(transfer) if transfer.status == "Completed" and transfer.payload.get("asset") else None,
            error=transfer.error,
        )

    def _download_status(self, transfer: _Transfer) -> DownloadStatusResponse:
        total = transfer.total_bytes or 0
        return DownloadStatusResponse(
            job_id=str(transfer.payload.get("jobId") or ""), status=transfer.status, total_bytes=total,
            downloaded_bytes=transfer.completed_bytes, progress=(transfer.completed_bytes / total) if total else (1.0 if transfer.status == "Completed" else 0.0),
            item_count=1, items_completed=1 if transfer.status == "Completed" else 0,
        )

    def _download_response(self, job_id: str, transfer: _Transfer) -> DownloadResultResponse:
        asset = transfer.payload.get("asset") or {}
        file_name = str(asset.get("fileName") or transfer.file_name)
        final_path = transfer.target_path
        # The SDK downloads to the requested path; give the file its server-side name for the artist.
        wanted = os.path.join(os.path.dirname(final_path), file_name)
        if wanted != final_path and os.path.isfile(final_path):
            try:
                os.replace(final_path, wanted)
                final_path = wanted
            except OSError:
                pass
        size = int(asset.get("size") or (os.path.getsize(final_path) if os.path.isfile(final_path) else 0))
        item = DownloadedResultItemResponse(blob_id=str(asset.get("assetId") or ""), file_name=file_name, local_path=final_path, file_size=size)
        return DownloadResultResponse(downloaded=True, job_id=job_id, blob_id=item.blob_id, file_name=file_name, local_path=final_path,
                                      file_size=size, items=[item], message="Downloaded.")


# ---------------------------------------------------------------------- #
# Document composition (the bridge's DTO dicts → the published vocabulary)
# ---------------------------------------------------------------------- #

def _ci(data: Any, key: str, default: Any = None) -> Any:
    """Case-insensitive lookup: the addon's dicts are PascalCase, the door writes camelCase."""
    if not isinstance(data, dict):
        return default
    for candidate in (key, key[:1].upper() + key[1:], key[:1].lower() + key[1:]):
        if candidate in data:
            return data[candidate]
    lowered = key.lower()
    for name, value in data.items():
        if str(name).lower() == lowered:
            return value
    return default


def _enum(enum_type: Any, value: Any) -> Any:
    """The addon carries the controller enums as ordinals (its REST-era wire form); the vocabulary
    carries member names. Names pass through; unknown ordinals fall back to the raw value, which
    the server's converter also accepts."""
    if value is None or isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            return value
    members = list(enum_type)
    try:
        return members[int(value)]
    except (IndexError, ValueError, TypeError):
        return value


def _scene_ref(scene_blob_id: str, attached_files: list[dict[str, Any]] | None) -> Any:
    return render.RenderSceneRef(
        blend_blob_id=str(scene_blob_id),
        attached_files=[
            render.RenderSceneAttachmentRef(
                kind=str(_ci(item, "kind") or ""),
                blob_id=str(_ci(item, "blobId") or ""),
                original_path=str(_ci(item, "originalPath") or ""),
                relative_path=str(_ci(item, "relativePath") or ""),
                packaging_strategy=str(_ci(item, "packagingStrategy") or ""),
                frame=_ci(item, "frame"),
            )
            for item in attached_files or []
        ],
    )


def _render_options(options: dict[str, Any]) -> Any:
    return render.RenderOptions(
        format=_enum(render.RenderFormat, _ci(options, "format")),
        engine=_enum(render.RenderEngine, _ci(options, "engine")),
        samples=_ci(options, "samples"),
        resolution_x=_ci(options, "resolutionX"),
        resolution_y=_ci(options, "resolutionY"),
        denoise=_ci(options, "denoise"),
        batch_size=_ci(options, "batchSize"),
        color_mode=_enum(render.RenderColorMode, _ci(options, "colorMode")),
        film_transparent=_enum(render.RenderFilmTransparency, _ci(options, "filmTransparent")),
        color_depth=_enum(render.RenderColorDepth, _ci(options, "colorDepth")),
    )


def _tile_options(tile_options: dict[str, Any]) -> Any:
    return render.RenderTileOptions(
        overlap_px=_ci(tile_options, "overlapPx"),
        blend_mode=_enum(render.TileBlendMode, _ci(tile_options, "blendMode")),
    )


def _video_options(video: dict[str, Any]) -> Any:
    return render.RenderVideoOptions(
        frame_rate=_ci(video, "frameRate"),
        constant_rate_factor=_ci(video, "constantRateFactor"),
        format=_enum(render.VideoFormat, _ci(video, "format")),
    )


def _bake_options() -> Any:
    return render.RenderBakeOptions()


def _bake_script(base: str, options: dict[str, Any]) -> str:
    engine = _enum(render.RenderEngine, _ci(options, "engine"))
    if isinstance(engine, render.RenderEngine):
        return base + engine.value
    suffix = _ENGINE_SUFFIX.get(int(engine) if isinstance(engine, int) else -1)
    if suffix is None:
        raise EmbeddedClientError(f"Bake-and-render needs a known engine; got {engine!r}.")
    return base + suffix


def _scope(request: Any, group_id: str, project_id: str) -> None:
    group_id = (group_id or "").strip()
    project_id = (project_id or "").strip()
    if group_id and project_id:
        raise EmbeddedClientError("A launch may target a group or a project, not both.")
    if project_id:
        request.project(project_id)
    elif group_id:
        request.client_group(group_id)


def _frames_data(value: Any) -> RenderPreflightFramesData | None:
    if value is None:
        return None
    return RenderPreflightFramesData(can_render=bool(value.can_render), runtime_target=value.runtime_target,
                                     issues=list(value.issues or []), warnings=list(value.warnings or []))


def _tiled_data(value: Any) -> RenderPreflightStillTiledData | None:
    if value is None:
        return None
    mode = value.requested_blend_mode
    ordinal = list(render.TileBlendMode).index(mode) if isinstance(mode, render.TileBlendMode) else int(mode or 0)
    return RenderPreflightStillTiledData(can_render=bool(value.can_render), runtime_target=value.runtime_target, requested_blend_mode=ordinal,
                                         issues=list(value.issues or []), warnings=list(value.warnings or []))


def _video_data(value: Any) -> RenderPreflightVideoData | None:
    if value is None:
        return None
    return RenderPreflightVideoData(can_render=bool(value.can_render), runtime_target=value.runtime_target,
                                    issues=list(value.issues or []), warnings=list(value.warnings or []))
