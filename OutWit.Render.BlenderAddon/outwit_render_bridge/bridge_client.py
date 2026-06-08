from __future__ import annotations

import json
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
    ExecutionScopeOptionsResponse,
    GetJobResponse,
    RenderPreflightResponse,
    RenderValidateBlendResponse,
    RunRenderResponse,
    SessionStateResponse,
    UploadBlendResponse,
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

    def upload_blend(self, file_path: str) -> UploadBlendResponse:
        return self._post("UploadBlendAsync", UploadBlendResponse.from_json, file_path)

    def upload_file(self, file_path: str) -> UploadBlendResponse:
        return self._post("UploadFileAsync", UploadBlendResponse.from_json, file_path)

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

    def get_job(self, job_id: str) -> GetJobResponse:
        return self._post("GetJobAsync", GetJobResponse.from_json, job_id)

    def cancel_job(self, job_id: str) -> bool:
        return self._post("CancelJobAsync", lambda data: bool(data), job_id)

    def download_result(self, job_id: str) -> DownloadResultResponse:
        return self._post("DownloadResultAsync", DownloadResultResponse.from_json, job_id)

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
