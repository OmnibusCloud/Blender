from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any


def _ensure_mapping(data: Any) -> dict[str, Any]:
    current = data

    for _ in range(4):
        if isinstance(current, dict):
            return current

        if isinstance(current, str):
            if current == "":
                return {}

            try:
                current = json.loads(current)
                continue
            except json.JSONDecodeError:
                try:
                    decoded = base64.b64decode(current, validate=True).decode("utf-8")
                    current = json.loads(decoded)
                    continue
                except Exception:
                    return {}

        return {}

    return current if isinstance(current, dict) else {}


def _get_value(data: dict[str, Any], name: str, default: Any = None) -> Any:
    if name in data:
        return data[name]

    if name:
        camel_name = name[0].lower() + name[1:]
        if camel_name in data:
            return data[camel_name]

    return default


def _get_int(data: dict[str, Any], name: str, default: int) -> int:
    """Int field where 0 is a legitimate stored value (so `int(x or default)` would clobber it)."""
    value = _get_value(data, name, None)
    if value is None or value == "":
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class BridgeLocalConnectionContext:
    local_rest_url: str
    is_secret_required: bool
    session_secret: str | None
    bridge_process_id: int
    created_utc: str

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "BridgeLocalConnectionContext":
        data = _ensure_mapping(data)
        return BridgeLocalConnectionContext(
            local_rest_url=str(_get_value(data, "LocalRestUrl") or ""),
            is_secret_required=bool(_get_value(data, "IsSecretRequired")),
            session_secret=_get_value(data, "SessionSecret"),
            bridge_process_id=int(_get_value(data, "BridgeProcessId") or 0),
            created_utc=str(_get_value(data, "CreatedUtc") or ""),
        )


@dataclass(slots=True)
class BridgeStatusResponse:
    bridge_version: str = ""
    is_signed_in: bool = False
    is_connected_to_cloud: bool = False
    current_user_display_name: str | None = None
    current_user_id: str | None = None
    last_error: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "BridgeStatusResponse":
        data = _ensure_mapping(data)
        return BridgeStatusResponse(
            bridge_version=str(_get_value(data, "BridgeVersion") or ""),
            is_signed_in=bool(_get_value(data, "IsSignedIn")),
            is_connected_to_cloud=bool(_get_value(data, "IsConnectedToCloud")),
            current_user_display_name=_get_value(data, "CurrentUserDisplayName"),
            current_user_id=_get_value(data, "CurrentUserId"),
            last_error=_get_value(data, "LastError"),
        )


@dataclass(slots=True)
class SessionStateResponse:
    is_signed_in: bool = False
    display_name: str | None = None
    user_id: str | None = None
    can_launch: bool = False
    needs_interactive_login: bool = False
    last_error: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "SessionStateResponse":
        data = _ensure_mapping(data)
        return SessionStateResponse(
            is_signed_in=bool(_get_value(data, "IsSignedIn")),
            display_name=_get_value(data, "DisplayName"),
            user_id=_get_value(data, "UserId"),
            can_launch=bool(_get_value(data, "CanLaunch")),
            needs_interactive_login=bool(_get_value(data, "NeedsInteractiveLogin")),
            last_error=_get_value(data, "LastError"),
        )


@dataclass(slots=True)
class BeginSignInResponse:
    started: bool = False
    requires_browser: bool = False
    message: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "BeginSignInResponse":
        data = _ensure_mapping(data)
        return BeginSignInResponse(
            started=bool(_get_value(data, "Started")),
            requires_browser=bool(_get_value(data, "RequiresBrowser")),
            message=_get_value(data, "Message"),
        )


@dataclass(slots=True)
class AcquireLeaseResponse:
    lease_accepted: bool = False
    lease_id: str = ""
    heartbeat_interval_seconds: int = 0
    lease_timeout_seconds: int = 0
    message: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "AcquireLeaseResponse":
        data = _ensure_mapping(data)
        return AcquireLeaseResponse(
            lease_accepted=bool(_get_value(data, "LeaseAccepted")),
            lease_id=str(_get_value(data, "LeaseId") or ""),
            heartbeat_interval_seconds=int(_get_value(data, "HeartbeatIntervalSeconds") or 0),
            lease_timeout_seconds=int(_get_value(data, "LeaseTimeoutSeconds") or 0),
            message=_get_value(data, "Message"),
        )


@dataclass(slots=True)
class ExecutionGroupOptionResponse:
    group_id: str = ""
    name: str = ""
    description: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "ExecutionGroupOptionResponse":
        data = _ensure_mapping(data)
        return ExecutionGroupOptionResponse(
            group_id=str(_get_value(data, "GroupId") or ""),
            name=str(_get_value(data, "Name") or ""),
            description=_get_value(data, "Description"),
        )


@dataclass(slots=True)
class ExecutionProjectOptionResponse:
    project_id: str = ""
    name: str = ""
    description: str | None = None
    assigned_group_id: str | None = None
    assigned_group_name: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "ExecutionProjectOptionResponse":
        data = _ensure_mapping(data)
        return ExecutionProjectOptionResponse(
            project_id=str(_get_value(data, "ProjectId") or ""),
            name=str(_get_value(data, "Name") or ""),
            description=_get_value(data, "Description"),
            assigned_group_id=_get_value(data, "AssignedGroupId"),
            assigned_group_name=_get_value(data, "AssignedGroupName"),
        )


@dataclass(slots=True)
class ExecutionScopeOptionsResponse:
    can_run_on_all_clients: bool = False
    groups: list[ExecutionGroupOptionResponse] = field(default_factory=list)
    projects: list[ExecutionProjectOptionResponse] = field(default_factory=list)

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "ExecutionScopeOptionsResponse":
        data = _ensure_mapping(data)
        return ExecutionScopeOptionsResponse(
            can_run_on_all_clients=bool(_get_value(data, "CanRunOnAllClients")),
            groups=[ExecutionGroupOptionResponse.from_json(me) for me in _get_value(data, "Groups") or []],
            projects=[ExecutionProjectOptionResponse.from_json(me) for me in _get_value(data, "Projects") or []],
        )


@dataclass(slots=True)
class RenderSettingsResponse:
    """Persisted per-user render preferences (Phase 5 bucket 1) — the BRIDGE owns the storage;
    this is the wire snapshot travelling both directions (seed on connect, sticky-write on submit)."""

    remember_render_settings: bool = True
    split_frame: bool = False
    tiles_x: int = 2
    tiles_y: int = 2
    tile_overlap: int = 8
    anim_result: str = "Sequence"
    video_container: str = ""
    video_codec: str = ""
    last_group_id: str = ""
    last_group_name: str = ""

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RenderSettingsResponse":
        data = _ensure_mapping(data)
        return RenderSettingsResponse(
            remember_render_settings=bool(_get_value(data, "RememberRenderSettings", True)),
            split_frame=bool(_get_value(data, "SplitFrame")),
            tiles_x=_get_int(data, "TilesX", 2),
            tiles_y=_get_int(data, "TilesY", 2),
            tile_overlap=_get_int(data, "TileOverlap", 8),
            anim_result=str(_get_value(data, "AnimResult") or "Sequence"),
            video_container=str(_get_value(data, "VideoContainer") or ""),
            video_codec=str(_get_value(data, "VideoCodec") or ""),
            last_group_id=str(_get_value(data, "LastGroupId") or ""),
            last_group_name=str(_get_value(data, "LastGroupName") or ""),
        )

    def to_payload(self) -> dict[str, Any]:
        """The SetRenderSettingsAsync body shape (PascalCase keys, mirrors the C# contract)."""
        return {
            "RememberRenderSettings": bool(self.remember_render_settings),
            "SplitFrame": bool(self.split_frame),
            "TilesX": int(self.tiles_x),
            "TilesY": int(self.tiles_y),
            "TileOverlap": int(self.tile_overlap),
            "AnimResult": self.anim_result or "",
            "VideoContainer": self.video_container or "",
            "VideoCodec": self.video_codec or "",
            "LastGroupId": self.last_group_id or "",
            "LastGroupName": self.last_group_name or "",
        }


@dataclass(slots=True)
class UploadBlendResponse:
    uploaded: bool = False
    blob_id: str = ""
    file_name: str = ""
    file_size: int = 0
    message: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "UploadBlendResponse":
        data = _ensure_mapping(data)
        return UploadBlendResponse(
            uploaded=bool(_get_value(data, "Uploaded")),
            blob_id=str(_get_value(data, "BlobId") or ""),
            file_name=str(_get_value(data, "FileName") or ""),
            file_size=int(_get_value(data, "FileSize") or 0),
            message=_get_value(data, "Message"),
        )


@dataclass(slots=True)
class RenderValidateBlendResponse:
    job_id: str = ""
    completed: bool = False
    is_valid: bool = False
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = ""
    message: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RenderValidateBlendResponse":
        data = _ensure_mapping(data)
        return RenderValidateBlendResponse(
            job_id=str(_get_value(data, "JobId") or ""),
            completed=bool(_get_value(data, "Completed")),
            is_valid=bool(_get_value(data, "IsValid")),
            issues=[str(item) for item in (_get_value(data, "Issues") or [])],
            warnings=[str(item) for item in (_get_value(data, "Warnings") or [])],
            status=str(_get_value(data, "Status") or ""),
            message=_get_value(data, "Message"),
        )


@dataclass(slots=True)
class RenderPreflightFramesData:
    can_render: bool = False
    runtime_target: str | None = None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RenderPreflightFramesData":
        data = _ensure_mapping(data)
        return RenderPreflightFramesData(
            can_render=bool(_get_value(data, "CanRender")),
            runtime_target=_get_value(data, "RuntimeTarget"),
            issues=[str(me) for me in _get_value(data, "Issues") or []],
            warnings=[str(me) for me in _get_value(data, "Warnings") or []],
        )


@dataclass(slots=True)
class RenderPreflightStillTiledData:
    can_render: bool = False
    runtime_target: str | None = None
    requested_blend_mode: int = 0
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RenderPreflightStillTiledData":
        data = _ensure_mapping(data)
        return RenderPreflightStillTiledData(
            can_render=bool(_get_value(data, "CanRender")),
            runtime_target=_get_value(data, "RuntimeTarget"),
            requested_blend_mode=int(_get_value(data, "RequestedBlendMode") or 0),
            issues=[str(me) for me in _get_value(data, "Issues") or []],
            warnings=[str(me) for me in _get_value(data, "Warnings") or []],
        )


@dataclass(slots=True)
class RenderPreflightVideoData:
    can_render: bool = False
    runtime_target: str | None = None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RenderPreflightVideoData":
        data = _ensure_mapping(data)
        return RenderPreflightVideoData(
            can_render=bool(_get_value(data, "CanRender")),
            runtime_target=_get_value(data, "RuntimeTarget"),
            issues=[str(me) for me in _get_value(data, "Issues") or []],
            warnings=[str(me) for me in _get_value(data, "Warnings") or []],
        )


@dataclass(slots=True)
class RenderPreflightData:
    can_render_all: bool = False
    still: RenderPreflightFramesData | None = None
    frames: RenderPreflightFramesData | None = None
    still_tiled: RenderPreflightStillTiledData | None = None
    video: RenderPreflightVideoData | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RenderPreflightData":
        data = _ensure_mapping(data)
        still = _get_value(data, "Still")
        frames = _get_value(data, "Frames")
        still_tiled = _get_value(data, "StillTiled")
        video = _get_value(data, "Video")

        return RenderPreflightData(
            can_render_all=bool(_get_value(data, "CanRenderAll")),
            still=RenderPreflightFramesData.from_json(still) if still is not None else None,
            frames=RenderPreflightFramesData.from_json(frames) if frames is not None else None,
            still_tiled=RenderPreflightStillTiledData.from_json(still_tiled) if still_tiled is not None else None,
            video=RenderPreflightVideoData.from_json(video) if video is not None else None,
        )


@dataclass(slots=True)
class RenderPreflightResponse:
    completed: bool = False
    status: str = ""
    message: str | None = None
    result: RenderPreflightData | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RenderPreflightResponse":
        data = _ensure_mapping(data)
        result = _get_value(data, "Result")
        return RenderPreflightResponse(
            completed=bool(_get_value(data, "Completed")),
            status=str(_get_value(data, "Status") or ""),
            message=_get_value(data, "Message"),
            result=RenderPreflightData.from_json(result) if result is not None else None,
        )


@dataclass(slots=True)
class RunRenderResponse:
    job_id: str = ""
    status: str = ""
    message: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "RunRenderResponse":
        data = _ensure_mapping(data)
        return RunRenderResponse(
            job_id=str(_get_value(data, "JobId") or ""),
            status=str(_get_value(data, "Status") or ""),
            message=_get_value(data, "Message"),
        )


@dataclass(slots=True)
class GetJobResponse:
    job_id: str = ""
    script_name: str = ""
    status: str = ""
    overall_progress: float = 0.0
    distributed_progress: float = 0.0
    is_completed: bool = False
    result_blob_id: str | None = None
    result_blob_ids: list[str | None] = field(default_factory=list)
    error_message: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "GetJobResponse":
        data = _ensure_mapping(data)
        return GetJobResponse(
            job_id=str(_get_value(data, "JobId") or ""),
            script_name=str(_get_value(data, "ScriptName") or ""),
            status=str(_get_value(data, "Status") or ""),
            overall_progress=float(_get_value(data, "OverallProgress") or 0.0),
            distributed_progress=float(_get_value(data, "DistributedProgress") or 0.0),
            is_completed=bool(_get_value(data, "IsCompleted")),
            result_blob_id=str(_get_value(data, "ResultBlobId")) if _get_value(data, "ResultBlobId") is not None else None,
            result_blob_ids=[str(me) if me is not None else None for me in _get_value(data, "ResultBlobIds") or []],
            error_message=_get_value(data, "ErrorMessage"),
        )


@dataclass(slots=True)
class DownloadedResultItemResponse:
    blob_id: str = ""
    file_name: str = ""
    local_path: str = ""
    file_size: int = 0

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "DownloadedResultItemResponse":
        data = _ensure_mapping(data)
        return DownloadedResultItemResponse(
            blob_id=str(_get_value(data, "BlobId") or ""),
            file_name=str(_get_value(data, "FileName") or ""),
            local_path=str(_get_value(data, "LocalPath") or ""),
            file_size=int(_get_value(data, "FileSize") or 0),
        )


@dataclass(slots=True)
class DownloadResultResponse:
    downloaded: bool = False
    job_id: str = ""
    blob_id: str = ""
    file_name: str = ""
    local_path: str = ""
    file_size: int = 0
    items: list[DownloadedResultItemResponse] = field(default_factory=list)
    message: str | None = None

    @staticmethod
    def from_json(data: dict[str, Any] | str) -> "DownloadResultResponse":
        data = _ensure_mapping(data)
        return DownloadResultResponse(
            downloaded=bool(_get_value(data, "Downloaded")),
            job_id=str(_get_value(data, "JobId") or ""),
            blob_id=str(_get_value(data, "BlobId") or ""),
            file_name=str(_get_value(data, "FileName") or ""),
            local_path=str(_get_value(data, "LocalPath") or ""),
            file_size=int(_get_value(data, "FileSize") or 0),
            items=[DownloadedResultItemResponse.from_json(me) for me in _get_value(data, "Items") or []],
            message=_get_value(data, "Message"),
        )
