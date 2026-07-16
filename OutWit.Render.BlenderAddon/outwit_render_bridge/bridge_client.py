from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, TypeVar

from .bridge_context import BridgeContextError, load_latest_context
from .bridge_models import (
    AcquireLeaseResponse,
    BeginSignInResponse,
    BridgeStatusResponse,
    DownloadResultResponse,
    DownloadStatusResponse,
    ExecutionScopeOptionsResponse,
    GetJobResponse,
    RenderPreflightResponse,
    RenderSettingsResponse,
    RenderValidateBlendResponse,
    RunRenderResponse,
    SessionStateResponse,
    UploadBlendResponse,
    UploadStatusResponse,
)

TResponse = TypeVar("TResponse")


def _append_group(payload: list[Any], selected_client_group_id: str) -> None:
    """Append the client-group id as a trailing positional arg when one is selected.

    The bridge REST processor binds by exact parameter count, so adding the group id
    routes the call to the group-targeted render overload; omitting it keeps the default
    "any available client" overload. An empty / blank id means "all clients".
    """
    if selected_client_group_id and selected_client_group_id.strip():
        payload.append(selected_client_group_id.strip())


class BridgeClientError(Exception):
    pass


class BridgeClient:
    def __init__(self, context_directory: str):
        self._context_directory = context_directory

    def get_bridge_status(self) -> BridgeStatusResponse:
        return self._get("GetBridgeStatusAsync", BridgeStatusResponse.from_json)

    def begin_sign_in(self) -> BeginSignInResponse:
        return self._get("BeginSignInAsync", BeginSignInResponse.from_json)

    def sign_out(self) -> bool:
        return self._get("SignOutAsync", lambda data: bool(data))

    def get_session_state(self) -> SessionStateResponse:
        return self._get("GetSessionStateAsync", SessionStateResponse.from_json)

    def get_execution_scope_options(self) -> ExecutionScopeOptionsResponse:
        return self._get("GetExecutionScopeOptionsAsync", ExecutionScopeOptionsResponse.from_json)

    def acquire_lease(self, owner_process_id: int, lease_id: str, addon_version: str | None = None) -> AcquireLeaseResponse:
        return self._post(
            "AcquireLeaseAsync",
            AcquireLeaseResponse.from_json,
            owner_process_id,
            lease_id,
            addon_version or "",
        )

    def ping_lease(self, lease_id: str) -> bool:
        return self._post("PingLeaseAsync", lambda data: bool(data), lease_id)

    def release_lease(self, lease_id: str) -> bool:
        return self._post("ReleaseLeaseAsync", lambda data: bool(data), lease_id)

    # Uploads run as background transfers on the bridge (start once, then poll): a large packed
    # scene or cache takes minutes to push to the cloud — far past the per-request timeout — so no
    # single REST call may span the whole upload. These keep the old blocking signature (callers
    # already run them on worker threads); the polling happens inside.
    def upload_blend(self, file_path: str) -> UploadBlendResponse:
        return self._run_upload("StartUploadBlendAsync", file_path)

    def upload_file(self, file_path: str) -> UploadBlendResponse:
        return self._run_upload("StartUploadFileAsync", file_path)

    def start_upload_blend(self, file_path: str) -> UploadStatusResponse:
        return self._post("StartUploadBlendAsync", UploadStatusResponse.from_json, file_path)

    def start_upload_file(self, file_path: str) -> UploadStatusResponse:
        return self._post("StartUploadFileAsync", UploadStatusResponse.from_json, file_path)

    def get_upload_status(self, transfer_id: str) -> UploadStatusResponse:
        return self._post("GetUploadStatusAsync", UploadStatusResponse.from_json, transfer_id)

    def cancel_upload(self, transfer_id: str) -> bool:
        return self._post("CancelUploadAsync", lambda data: bool(data), transfer_id)

    def _run_upload(self, start_method: str, file_path: str) -> UploadBlendResponse:
        status = self._post(start_method, UploadStatusResponse.from_json, file_path)

        # Ramping poll: small files (cache frames upload in bulk) finish within the first quick
        # polls, while a multi-hundred-MB scene settles into a relaxed 0.5s cadence.
        delay = 0.05
        while status.status == "InProgress":
            time.sleep(delay)
            delay = min(delay * 2, 0.5)
            status = self.get_upload_status(status.transfer_id)

        if status.status == "Completed" and status.result is not None:
            return status.result

        raise BridgeClientError(status.error or f"Upload did not complete (status: {status.status or 'unknown'}).")

    def run_render_validate_blend(self, scene_blob_id: str, attached_files: list[dict[str, Any]] | None = None) -> RenderValidateBlendResponse:
        return self._post("RunRenderValidateBlendAsync", RenderValidateBlendResponse.from_json, scene_blob_id, attached_files or [])

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
    ) -> RenderPreflightResponse:
        return self._post(
            "RunRenderPreflightAsync",
            RenderPreflightResponse.from_json,
            frame,
            start_frame,
            end_frame,
            tiles_x,
            tiles_y,
            options,
            tile_options,
            video,
        )

    def run_render_still(self, scene_blob_id: str, frame: int, options: dict[str, Any], attached_files: list[dict[str, Any]] | None = None, selected_client_group_id: str = "") -> RunRenderResponse:
        payload = [scene_blob_id, frame, options, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunRenderStillAsync", RunRenderResponse.from_json, *payload)

    def run_render_still_tiled(
        self,
        scene_blob_id: str,
        frame: int,
        tiles_x: int,
        tiles_y: int,
        options: dict[str, Any],
        tile_options: dict[str, Any],
        attached_files: list[dict[str, Any]] | None = None,
        selected_client_group_id: str = "",
    ) -> RunRenderResponse:
        payload = [scene_blob_id, frame, tiles_x, tiles_y, options, tile_options, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunRenderStillTiledAsync", RunRenderResponse.from_json, *payload)

    def run_render_frames(
        self,
        scene_blob_id: str,
        start_frame: int,
        end_frame: int,
        options: dict[str, Any],
        attached_files: list[dict[str, Any]] | None = None,
        selected_client_group_id: str = "",
    ) -> RunRenderResponse:
        payload = [scene_blob_id, start_frame, end_frame, options, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunRenderFramesAsync", RunRenderResponse.from_json, *payload)

    def run_render_video(
        self,
        scene_blob_id: str,
        start_frame: int,
        end_frame: int,
        options: dict[str, Any],
        video: dict[str, Any],
        attached_files: list[dict[str, Any]] | None = None,
        selected_client_group_id: str = "",
    ) -> RunRenderResponse:
        payload = [scene_blob_id, start_frame, end_frame, options, video, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunRenderVideoAsync", RunRenderResponse.from_json, *payload)

    # Bake-and-render variants: the controller delegates a simulation bake to the fastest node, then
    # distributes the baked scene exactly like the plain run_render_* counterparts. Same arguments,
    # same response shape; only the bridge method (and the bundled script it resolves) differs. Used
    # when the scene has an unbaked simulation and the artist's bake strategy is "delegated".
    def run_bake_and_render_still(self, scene_blob_id: str, frame: int, options: dict[str, Any], attached_files: list[dict[str, Any]] | None = None, selected_client_group_id: str = "") -> RunRenderResponse:
        payload = [scene_blob_id, frame, options, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunBakeAndRenderStillAsync", RunRenderResponse.from_json, *payload)

    def run_bake_and_render_still_tiled(
        self,
        scene_blob_id: str,
        frame: int,
        tiles_x: int,
        tiles_y: int,
        options: dict[str, Any],
        tile_options: dict[str, Any],
        attached_files: list[dict[str, Any]] | None = None,
        selected_client_group_id: str = "",
    ) -> RunRenderResponse:
        payload = [scene_blob_id, frame, tiles_x, tiles_y, options, tile_options, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunBakeAndRenderStillTiledAsync", RunRenderResponse.from_json, *payload)

    def run_bake_and_render_frames(
        self,
        scene_blob_id: str,
        start_frame: int,
        end_frame: int,
        options: dict[str, Any],
        attached_files: list[dict[str, Any]] | None = None,
        selected_client_group_id: str = "",
    ) -> RunRenderResponse:
        payload = [scene_blob_id, start_frame, end_frame, options, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunBakeAndRenderFramesAsync", RunRenderResponse.from_json, *payload)

    def run_bake_and_render_video(
        self,
        scene_blob_id: str,
        start_frame: int,
        end_frame: int,
        options: dict[str, Any],
        video: dict[str, Any],
        attached_files: list[dict[str, Any]] | None = None,
        selected_client_group_id: str = "",
    ) -> RunRenderResponse:
        payload = [scene_blob_id, start_frame, end_frame, options, video, attached_files or []]
        _append_group(payload, selected_client_group_id)
        return self._post("RunBakeAndRenderVideoAsync", RunRenderResponse.from_json, *payload)

    def get_job(self, job_id: str) -> GetJobResponse:
        return self._post("GetJobAsync", GetJobResponse.from_json, job_id)

    def cancel_job(self, job_id: str) -> bool:
        return self._post("CancelJobAsync", lambda data: bool(data), job_id)

    def download_result(self, job_id: str) -> DownloadResultResponse:
        return self._post("DownloadResultAsync", DownloadResultResponse.from_json, job_id)

    # Large results (video, frame archives) take minutes to pull from the cloud — far past any sane
    # per-request timeout. The bridge downloads them in a background transfer: start once, then poll
    # the status; every REST round-trip here stays fast.
    def start_download_result(self, job_id: str) -> DownloadStatusResponse:
        return self._post("StartDownloadResultAsync", DownloadStatusResponse.from_json, job_id)

    def get_download_result_status(self, job_id: str) -> DownloadStatusResponse:
        return self._post("GetDownloadResultStatusAsync", DownloadStatusResponse.from_json, job_id)

    def cancel_download_result(self, job_id: str) -> bool:
        return self._post("CancelDownloadResultAsync", lambda data: bool(data), job_id)

    def get_render_settings(self) -> RenderSettingsResponse:
        return self._get("GetRenderSettingsAsync", RenderSettingsResponse.from_json)

    def set_render_settings(self, settings: dict[str, Any]) -> bool:
        return self._post("SetRenderSettingsAsync", lambda data: bool(data), settings)

    def _get(self, method_name: str, parser: Callable[[Any], TResponse], **parameters: Any) -> TResponse:
        context, _ = self._load_context()
        url = self._build_url(context.local_rest_url, method_name, **parameters)
        request = urllib.request.Request(url, method="GET")
        self._apply_secret(context, request)
        payload = self._send(request)
        return parser(payload)

    def _post(self, method_name: str, parser: Callable[[Any], TResponse], *payload: Any) -> TResponse:
        context, _ = self._load_context()
        url = self._build_url(context.local_rest_url, method_name)
        body = {
            f"param{index + 1}": value
            for index, value in enumerate(payload)
        }
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        self._apply_secret(context, request)
        response = self._send(request)
        return parser(response)

    def _send(self, request: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as ex:
            detail = ex.read().decode("utf-8", errors="replace")
            raise BridgeClientError(f"Bridge HTTP error {ex.code}: {detail}") from ex
        except urllib.error.URLError as ex:
            raise BridgeClientError(f"Bridge request failed: {ex.reason}") from ex

        try:
            envelope = json.loads(body)
        except json.JSONDecodeError as ex:
            raise BridgeClientError("Bridge returned invalid JSON.") from ex

        error_message = envelope.get("ErrorMessage") or envelope.get("Message")
        if error_message:
            raise BridgeClientError(str(error_message))

        data = envelope.get("Data")
        if data is None:
            raise BridgeClientError("Bridge response did not contain a Data payload.")

        return self._normalize_payload(data)

    @staticmethod
    def _normalize_payload(data: Any) -> Any:
        if isinstance(data, str):
            current = data
            for _ in range(4):
                if current == "":
                    return None

                try:
                    parsed = json.loads(current)
                except json.JSONDecodeError:
                    return current

                if not isinstance(parsed, str):
                    return parsed

                current = parsed

            return current

        return data

    def _load_context(self) -> tuple[Any, str]:
        try:
            return load_latest_context(self._context_directory)
        except BridgeContextError as ex:
            raise BridgeClientError(str(ex)) from ex

    @staticmethod
    def _apply_secret(context, request: urllib.request.Request) -> None:
        if context.is_secret_required and context.session_secret:
            request.add_header("Authorization", f"Bearer {context.session_secret}")

    @staticmethod
    def _build_url(base_url: str, method_name: str, **parameters: Any) -> str:
        url = f"{base_url.rstrip('/')}/{method_name}"
        if not parameters:
            return url

        query = urllib.parse.urlencode(parameters)
        return f"{url}?{query}"
