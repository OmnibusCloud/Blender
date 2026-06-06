from __future__ import annotations

import json
import os
import subprocess
import sys

import bpy
from bpy.types import Operator

from .bridge_client import BridgeClient, BridgeClientError
from .bridge_context import load_latest_context
from .bridge_dependency_policy import get_dependency_portability_blocking_issue, get_simulation_cache_blocking_issue
from .bridge_engine_routing import (
    detect_scene_engine_family,
    get_scene_engine_token,
    SceneEngineRoutingError,
)
from .bridge_launcher import (
    acquire_bridge_lease,
    cleanup_bridge_on_unregister,
    ensure_bridge_running,
    get_effective_context_directory,
    launch_bridge,
    ping_bridge_lease,
    refresh_bridge_process_state,
    release_bridge_lease,
    stop_bridge,
)
from .bridge_scene_attachments import collect_scene_attachment_metadata, summarize_scene_attachment_metadata
from .bridge_scene_packaging import create_packed_upload_copy, ScenePackagingError

FORMAT_PNG = 0
BLEND_MODE_CENTER_PRIORITY_CROP = 0


def _get_context_directory(context) -> str:
    return get_effective_context_directory(context)


def _get_runtime_state(context):
    return context.window_manager.outwit_bridge_state


def _get_bridge_client(context) -> BridgeClient:
    ensure_bridge_running(context)
    return BridgeClient(_get_context_directory(context))


def _apply_context(state, bridge_context, context_path: str) -> None:
    state.bridge_url = bridge_context.local_rest_url
    state.context_path = context_path
    state.bridge_process_id = bridge_context.bridge_process_id
    state.bridge_is_running = True
    state.is_secret_required = bridge_context.is_secret_required
    state.bridge_session_directory = os.path.dirname(context_path)


def _get_current_blend_path() -> str:
    blend_path = bpy.data.filepath
    if not blend_path:
        raise BridgeClientError("The current Blender scene is not saved. Save the .blend file before uploading.")

    if not os.path.isfile(blend_path):
        raise BridgeClientError(f"The current Blender scene file does not exist: {blend_path}")

    if bool(getattr(bpy.data, "is_dirty", False)):
        raise BridgeClientError("The current Blender scene has unsaved changes. Save the .blend file before launching a cloud render.")

    return blend_path


def _collect_render_options(context) -> dict[str, object]:
    scene = context.scene
    render = scene.render
    percentage = max(1, int(render.resolution_percentage))
    resolution_x = int(render.resolution_x * percentage / 100)
    resolution_y = int(render.resolution_y * percentage / 100)
    engine_family, engine_enum = detect_scene_engine_family(scene)

    return {
        "Format": FORMAT_PNG,
        "Engine": engine_enum,
        "Samples": _get_scene_samples(scene, engine_family),
        "ResolutionX": resolution_x,
        "ResolutionY": resolution_y,
        "Denoise": _get_scene_denoise(scene, engine_family),
    }


def _get_scene_samples(scene, engine_family: str) -> int:
    if engine_family == "Cycles":
        cycles = getattr(scene, "cycles", None)
        return int(getattr(cycles, "samples", 0) or 0) if cycles is not None else 0

    if engine_family in {"Eevee", "GreasePencil"}:
        eevee = getattr(scene, "eevee", None)
        if eevee is None:
            return 0

        value = getattr(eevee, "taa_render_samples", None)
        if value is None:
            value = getattr(eevee, "taa_samples", 0)

        return int(value or 0)

    return 0


def _get_scene_denoise(scene, engine_family: str) -> bool:
    if engine_family == "Cycles":
        cycles = getattr(scene, "cycles", None)
        return bool(getattr(cycles, "use_denoising", False)) if cycles is not None else False

    return False


def _collect_tile_options(state) -> dict[str, object]:
    return {
        "OverlapPx": int(state.tile_overlap_px),
        "BlendMode": BLEND_MODE_CENTER_PRIORITY_CROP,
    }


def _collect_video_options(state) -> dict[str, object]:
    return {
        "FrameRate": int(state.video_frame_rate),
        "ConstantRateFactor": int(state.video_constant_rate_factor),
    }


def _get_uploaded_attachment_manifest(state) -> list[dict[str, object]]:
    if not state.uploaded_attachment_manifest_json:
        return []

    try:
        value = json.loads(state.uploaded_attachment_manifest_json)
    except json.JSONDecodeError:
        return []

    return value if isinstance(value, list) else []


def _apply_dependency_plan(state, attachments: list[dict[str, object]]) -> None:
    summary = summarize_scene_attachment_metadata(attachments)
    state.dependency_plan_total_count = int(summary.get("TotalCount") or 0)
    state.dependency_plan_count_summary = str(summary.get("CountSummary") or "")
    state.dependency_plan_packed_count = int(summary.get("PackedCount") or 0)
    state.dependency_plan_packed_summary = str(summary.get("PackedSummary") or "")
    state.dependency_plan_attachment_count = int(summary.get("AttachmentCount") or 0)
    state.dependency_plan_attachment_summary = str(summary.get("AttachmentSummary") or "")


def _upload_scene_attachments(client: BridgeClient, attachments: list[dict[str, object]]) -> list[dict[str, object]]:
    uploaded_attachments: list[dict[str, object]] = []
    for attachment in attachments:
        current = dict(attachment)
        packaging_strategy = str(current.get("PackagingStrategy") or "")
        if packaging_strategy == "SceneAttachmentBlob":
            source_path = str(current.get("OriginalPath") or "")
            response = client.upload_file(source_path)
            current["BlobId"] = response.blob_id

        uploaded_attachments.append(current)

    return uploaded_attachments


def _collect_issue_summary(preflight) -> str:
    if preflight.result is None:
        return preflight.message or ""

    issues: list[str] = []
    for item in [preflight.result.still, preflight.result.frames, preflight.result.still_tiled, preflight.result.video]:
        if item is None:
            continue

        for issue in item.issues:
            if issue and issue not in issues:
                issues.append(issue)

    return " | ".join(issues)


def _collect_warning_summary(preflight) -> str:
    if preflight.result is None:
        return ""

    warnings: list[str] = []
    for item in [preflight.result.still, preflight.result.frames, preflight.result.still_tiled, preflight.result.video]:
        if item is None:
            continue

        for warning in getattr(item, "warnings", []):
            if warning and warning not in warnings:
                warnings.append(warning)

    return " | ".join(warnings)


def _collect_item_issue_summary(item) -> str:
    if item is None:
        return ""

    issues: list[str] = []
    for issue in getattr(item, "issues", []):
        if issue and issue not in issues:
            issues.append(issue)

    return " | ".join(issues)


def _collect_item_warning_summary(item) -> str:
    if item is None:
        return ""

    warnings: list[str] = []
    for warning in getattr(item, "warnings", []):
        if warning and warning not in warnings:
            warnings.append(warning)

    return " | ".join(warnings)


def _collect_validate_issue_summary(response) -> str:
    issues: list[str] = []
    for issue in getattr(response, "issues", []):
        if issue and issue not in issues:
            issues.append(issue)

    return " | ".join(issues)


def _collect_validate_warning_summary(response) -> str:
    warnings: list[str] = []
    for warning in getattr(response, "warnings", []):
        if warning and warning not in warnings:
            warnings.append(warning)

    return " | ".join(warnings)


def _apply_validate_response(state, response) -> None:
    state.validate_job_id = response.job_id
    state.validate_status = response.status
    state.validate_message = response.message or ""
    state.validate_is_valid = response.is_valid
    state.validate_issue_summary = _collect_validate_issue_summary(response)
    state.validate_warning_summary = _collect_validate_warning_summary(response)


def _apply_preflight_response(state, response) -> None:
    result = response.result
    state.preflight_status = response.status
    state.preflight_message = response.message or ""
    state.preflight_can_render_all = bool(result.can_render_all) if result is not None else False
    state.preflight_still_ready = bool(result.still.can_render) if result is not None and result.still is not None else False
    state.preflight_frames_ready = bool(result.frames.can_render) if result is not None and result.frames is not None else False
    state.preflight_still_tiled_ready = bool(result.still_tiled.can_render) if result is not None and result.still_tiled is not None else False
    state.preflight_video_ready = bool(result.video.can_render) if result is not None and result.video is not None else False
    state.preflight_still_issue_summary = _collect_item_issue_summary(result.still) if result is not None else ""
    state.preflight_still_warning_summary = _collect_item_warning_summary(result.still) if result is not None else ""
    state.preflight_frames_issue_summary = _collect_item_issue_summary(result.frames) if result is not None else ""
    state.preflight_frames_warning_summary = _collect_item_warning_summary(result.frames) if result is not None else ""
    state.preflight_still_tiled_issue_summary = _collect_item_issue_summary(result.still_tiled) if result is not None else ""
    state.preflight_still_tiled_warning_summary = _collect_item_warning_summary(result.still_tiled) if result is not None else ""
    state.preflight_video_issue_summary = _collect_item_issue_summary(result.video) if result is not None else ""
    state.preflight_video_warning_summary = _collect_item_warning_summary(result.video) if result is not None else ""
    state.preflight_issue_summary = _collect_issue_summary(response)
    state.preflight_warning_summary = _merge_unique_summaries(_collect_warning_summary(response), state.validate_warning_summary)


def _validation_policy_message(state) -> str:
    portability_issue = get_dependency_portability_blocking_issue(state.validate_warning_summary)
    if portability_issue:
        return portability_issue

    simulation_issue = get_simulation_cache_blocking_issue(state.validate_issue_summary)
    if simulation_issue:
        return simulation_issue

    if state.validate_issue_summary:
        return _compose_policy_message("Scene blocked by validation.", state.validate_issue_summary)

    if state.validate_warning_summary:
        return _compose_policy_message("Scene validated with warnings.", state.validate_warning_summary)

    return "Scene validated."


def _preflight_policy_message(state) -> str:
    if not state.preflight_can_render_all or state.preflight_issue_summary:
        return _compose_policy_message("Preflight found blocking issues.", state.preflight_issue_summary)

    if state.preflight_warning_summary:
        return _compose_policy_message("Preflight ready with warnings.", state.preflight_warning_summary)

    return "Preflight ready."


def _compose_policy_message(prefix: str, summary: str) -> str:
    cleaned = summary.strip()
    if not cleaned:
        return prefix

    return f"{prefix} {cleaned}"


def _merge_unique_summaries(*summaries: str) -> str:
    values: list[str] = []
    for summary in summaries:
        for me in [me.strip() for me in summary.split("|") if me.strip()]:
            if me not in values:
                values.append(me)

    return " | ".join(values)


def _run_validate_blend(context):
    state = _get_runtime_state(context)
    context_directory = _get_context_directory(context)
    client = BridgeClient(context_directory)
    response = client.run_render_validate_blend(_ensure_uploaded_blob_id(state), _get_uploaded_attachment_manifest(state))
    _apply_validate_response(state, response)
    return response


def _run_preflight(context):
    state = _get_runtime_state(context)
    scene = context.scene
    client = _get_bridge_client(context)
    response = client.run_render_preflight(
        _get_still_frame(context),
        int(scene.frame_start),
        int(scene.frame_end),
        int(state.tiles_x),
        int(state.tiles_y),
        _collect_render_options(context),
        _collect_tile_options(state),
        _collect_video_options(state),
    )
    _apply_preflight_response(state, response)
    return response


def _selected_mode_is_ready(state) -> bool:
    if state.render_mode == "Still":
        return bool(state.preflight_still_ready)

    if state.render_mode == "StillTiled":
        return bool(state.preflight_still_tiled_ready)

    if state.render_mode == "Frames":
        return bool(state.preflight_frames_ready)

    return bool(state.preflight_video_ready)


def _selected_mode_preflight_issue_summary(state) -> str:
    if state.render_mode == "Still":
        return state.preflight_still_issue_summary

    if state.render_mode == "StillTiled":
        return state.preflight_still_tiled_issue_summary

    if state.render_mode == "Frames":
        return state.preflight_frames_issue_summary

    return state.preflight_video_issue_summary


def _selected_mode_preflight_warning_summary(state) -> str:
    if state.render_mode == "Still":
        return state.preflight_still_warning_summary

    if state.render_mode == "StillTiled":
        return state.preflight_still_tiled_warning_summary

    if state.render_mode == "Frames":
        return state.preflight_frames_warning_summary

    return state.preflight_video_warning_summary


def _selected_mode_issue_summary(state) -> str:
    return _selected_mode_preflight_issue_summary(state) if not _selected_mode_is_ready(state) else ""


def _selected_mode_warning_summary(state) -> str:
    return _merge_unique_summaries(state.validate_warning_summary, _selected_mode_preflight_warning_summary(state))


def _selected_mode_label(state) -> str:
    if state.render_mode == "StillTiled":
        return "Tiled still render"

    if state.render_mode == "Frames":
        return "Frame render"

    if state.render_mode == "Video":
        return "Video render"

    return "Still render"


def _selected_mode_policy_message(state) -> str:
    mode_label = _selected_mode_label(state)
    if not _selected_mode_is_ready(state):
        return _compose_policy_message(f"{mode_label} blocked by preflight.", _selected_mode_issue_summary(state))

    warning_summary = _selected_mode_warning_summary(state)
    if warning_summary:
        return _compose_policy_message(f"{mode_label} ready with warnings.", warning_summary)

    return f"{mode_label} ready."


def _selected_mode_launched_message(state) -> str:
    return f"{_selected_mode_label(state)} launched."


def _ensure_uploaded_blob_id(state) -> str:
    if not state.uploaded_blob_id:
        raise BridgeClientError("No uploaded scene blob is available. Upload the current .blend file first.")

    return state.uploaded_blob_id


def _scene_requires_upload(state, blend_path: str) -> bool:
    return not state.uploaded_blob_id or state.uploaded_source_path != blend_path


def _upload_current_blend(context):
    state = _get_runtime_state(context)
    client = _get_bridge_client(context)
    blend_path = _get_current_blend_path()
    planned_attachments = collect_scene_attachment_metadata()
    _apply_dependency_plan(state, planned_attachments)
    attachments = _upload_scene_attachments(client, planned_attachments)
    upload_message = ""

    try:
        with create_packed_upload_copy(blend_path) as (upload_path, packed_message):
            response = client.upload_blend(upload_path)
            upload_message = packed_message
    except ScenePackagingError:
        response = client.upload_blend(blend_path)

    state.current_blend_path = blend_path
    state.uploaded_blob_id = response.blob_id
    state.uploaded_source_path = blend_path
    state.uploaded_file_name = response.file_name
    state.uploaded_file_size = response.file_size
    state.uploaded_attachment_manifest_json = json.dumps(attachments, ensure_ascii=False)
    state.upload_message = upload_message or response.message or ("Upload completed." if response.uploaded else "Upload did not complete.")
    return response


def _ensure_current_scene_uploaded(context):
    state = _get_runtime_state(context)
    blend_path = _get_current_blend_path()
    if _scene_requires_upload(state, blend_path):
        return _upload_current_blend(context)

    state.current_blend_path = blend_path
    return None


def _get_still_frame(context) -> int:
    scene = context.scene
    state = _get_runtime_state(context)
    return max(1, int(scene.frame_start), int(state.still_frame))


def _apply_job_response(state, response, script_name: str) -> None:
    state.active_job_id = response.job_id
    state.active_job_script_name = script_name
    state.active_job_status = "Submitted"
    state.active_job_progress = "Starting..."
    state.active_job_progress_factor = 0.0
    state.active_job_distributed_progress = ""
    state.active_job_distributed_progress_factor = 0.0
    state.active_job_error = response.message or ""
    state.active_job_result_blob_id = ""
    state.active_job_result_blob_count = 0
    state.active_job_is_completed = False
    state.auto_refresh_active_job = True
    state.download_status = ""
    state.download_message = ""
    state.download_primary_path = ""
    state.download_primary_file_name = ""
    state.download_item_count = 0


def _apply_get_job_response(state, response) -> None:
    progress_value = response.overall_progress
    if progress_value <= 1.0:
        progress_value *= 100.0

    is_terminal_status = response.status in {"Completed", "Failed", "Cancelled"}
    has_materialized_result = bool(response.result_blob_id) or any(me for me in response.result_blob_ids)
    is_completed = response.is_completed and (response.status != "Completed" or has_materialized_result)
    if response.status in {"Failed", "Cancelled"}:
        is_completed = True

    if is_completed:
        progress_text = "100.0%"
    elif progress_value <= 0.0:
        progress_text = "Starting..."
    else:
        progress_text = f"{min(progress_value, 99.0):.1f}%"

    overall_factor = 1.0 if is_completed else max(0.0, min(progress_value / 100.0, 1.0))

    # "Computation" bar = the distributed (render) work the engine sees as one opaque Grid.ForEach
    # stage. Empty/0 (hidden) when the job has no distributed work; the server raises it to 100% at
    # completion only for jobs that actually distributed.
    distributed_value = response.distributed_progress
    if distributed_value <= 1.0:
        distributed_value *= 100.0

    if distributed_value <= 0.0:
        distributed_text = ""
        distributed_factor = 0.0
    elif is_completed:
        distributed_text = "100.0%"
        distributed_factor = 1.0
    else:
        distributed_text = f"{min(distributed_value, 100.0):.1f}%"
        distributed_factor = max(0.0, min(distributed_value / 100.0, 1.0))

    state.active_job_id = response.job_id
    state.active_job_script_name = response.script_name
    state.active_job_status = response.status if is_terminal_status or progress_value > 0 else "Submitted"
    state.active_job_progress = progress_text
    state.active_job_progress_factor = overall_factor
    state.active_job_distributed_progress = distributed_text
    state.active_job_distributed_progress_factor = distributed_factor
    state.active_job_error = response.error_message or ""
    state.active_job_result_blob_id = response.result_blob_id or ""
    state.active_job_result_blob_count = len(response.result_blob_ids)
    state.active_job_is_completed = is_completed


def _refresh_active_job_state(context) -> None:
    state = _get_runtime_state(context)
    client = _get_bridge_client(context)

    if not state.active_job_id:
        raise BridgeClientError("No active bridge job is selected. Launch a render first.")

    response = client.get_job(state.active_job_id)
    _apply_get_job_response(state, response)


def _open_path(path: str, open_parent: bool = False) -> None:
    if not path:
        raise BridgeClientError("No local result path is available yet.")

    target = os.path.dirname(path) if open_parent else path
    if not target or not os.path.exists(target):
        raise BridgeClientError(f"The requested local path does not exist: {target}")

    if sys.platform.startswith("win"):
        os.startfile(target)
        return

    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
        return

    subprocess.Popen(["xdg-open", target])


def _load_result_image(path: str):
    if not path:
        raise BridgeClientError("No local result path is available yet.")

    if not os.path.isfile(path):
        raise BridgeClientError(f"The requested result file does not exist: {path}")

    extension = os.path.splitext(path)[1].lower()
    if extension not in {".png", ".jpg", ".jpeg", ".exr", ".bmp", ".tga", ".tif", ".tiff"}:
        raise BridgeClientError(f"The downloaded result is not a supported image file: {path}")

    existing = bpy.data.images.get(os.path.basename(path))
    if existing is not None and bpy.path.abspath(existing.filepath) == bpy.path.abspath(path):
        existing.reload()
        return existing

    return bpy.data.images.load(path, check_existing=True)


def _auto_refresh_job_timer() -> float:
    context = getattr(bpy, "context", None)
    window_manager = getattr(context, "window_manager", None)
    state = getattr(window_manager, "outwit_bridge_state", None)
    if state is None:
        return 5.0

    interval = float(max(1, int(state.auto_refresh_interval_seconds)))
    if not state.auto_refresh_active_job or not state.active_job_id:
        return interval

    try:
        _refresh_active_job_state(context)
        if state.active_job_is_completed:
            state.auto_refresh_active_job = False
            state.status_message = "Job completed. Auto-refresh stopped."
    except Exception as ex:
        state.last_error = str(ex)
        state.status_message = "Auto-refresh failed."

    return interval


def _bridge_lease_timer() -> float:
    context = getattr(bpy, "context", None)
    window_manager = getattr(context, "window_manager", None)
    state = getattr(window_manager, "outwit_bridge_state", None)
    if state is None:
        return 5.0

    refresh_bridge_process_state(context)
    interval = float(max(1, int(state.bridge_heartbeat_interval_seconds or 5)))
    if not state.bridge_is_running or not state.bridge_lease_id:
        return interval

    try:
        ping_bridge_lease(context)
    except Exception as ex:
        state.bridge_lease_acquired = False
        state.last_error = str(ex)
        state.status_message = "Bridge lease heartbeat failed."

    return interval


def register_timers() -> None:
    if not bpy.app.timers.is_registered(_auto_refresh_job_timer):
        bpy.app.timers.register(_auto_refresh_job_timer, first_interval=5.0, persistent=True)

    if not bpy.app.timers.is_registered(_bridge_lease_timer):
        bpy.app.timers.register(_bridge_lease_timer, first_interval=5.0, persistent=True)


def unregister_timers() -> None:
    if bpy.app.timers.is_registered(_auto_refresh_job_timer):
        bpy.app.timers.unregister(_auto_refresh_job_timer)


def _run_selected_launch(context):
    state = _get_runtime_state(context)
    scene = context.scene
    client = _get_bridge_client(context)
    blob_id = _ensure_uploaded_blob_id(state)
    try:
        state.scene_engine_family, _ = detect_scene_engine_family(scene)
    except SceneEngineRoutingError as ex:
        raise BridgeClientError(str(ex)) from ex

    render_options = _collect_render_options(context)
    still_frame = _get_still_frame(context)

    if state.render_mode == "Still":
        response = client.run_render_still(blob_id, still_frame, render_options, _get_uploaded_attachment_manifest(state))
        _apply_job_response(state, response, "RenderStill")
        return response

    if state.render_mode == "StillTiled":
        response = client.run_render_still_tiled(
            blob_id,
            still_frame,
            int(state.tiles_x),
            int(state.tiles_y),
            render_options,
            _collect_tile_options(state),
            _get_uploaded_attachment_manifest(state),
        )
        _apply_job_response(state, response, "RenderStillTiled")
        return response

    if state.render_mode == "Frames":
        response = client.run_render_frames(
            blob_id,
            int(scene.frame_start),
            int(scene.frame_end),
            render_options,
            _get_uploaded_attachment_manifest(state),
        )
        _apply_job_response(state, response, "RenderFrames")
        return response

    response = client.run_render_video(
        blob_id,
        int(scene.frame_start),
        int(scene.frame_end),
        render_options,
        _collect_video_options(state),
        _get_uploaded_attachment_manifest(state),
    )
    _apply_job_response(state, response, "RenderVideo")
    return response


def _refresh_bridge_state(context) -> None:
    state = _get_runtime_state(context)
    scene = context.scene
    render = scene.render
    ensure_bridge_running(context)
    context_directory = _get_context_directory(context)
    client = BridgeClient(context_directory)

    bridge_context, context_path = load_latest_context(context_directory)
    _apply_context(state, bridge_context, context_path)

    blend_path = bpy.data.filepath or ""
    state.current_blend_path = blend_path
    state.current_blend_file_exists = bool(blend_path) and os.path.isfile(blend_path)
    state.current_blend_is_dirty = bool(getattr(bpy.data, "is_dirty", False))
    _apply_dependency_plan(state, collect_scene_attachment_metadata() if state.current_blend_file_exists else [])
    state.scene_frame_current = int(scene.frame_current)
    state.scene_frame_start = int(scene.frame_start)
    state.scene_frame_end = int(scene.frame_end)
    state.scene_camera_name = scene.camera.name if scene.camera is not None else ""
    state.scene_render_engine = get_scene_engine_token(scene)
    try:
        scene_engine_family, _ = detect_scene_engine_family(scene)
        state.scene_engine_family = scene_engine_family
    except SceneEngineRoutingError as ex:
        state.scene_engine_family = "Unsupported"
        state.last_error = str(ex)
    state.scene_use_nodes = bool(getattr(scene, "use_nodes", False))
    state.render_film_transparent = bool(getattr(render, "film_transparent", False))
    state.render_file_format = getattr(render.image_settings, "file_format", "") or ""
    state.render_color_mode = getattr(render.image_settings, "color_mode", "") or ""
    state.render_alpha_mode = getattr(render, "alpha_mode", "") or ""

    bridge_status = client.get_bridge_status()
    session_state = client.get_session_state()
    scope_options = None
    scope_error = ""
    if session_state.is_signed_in:
        try:
            scope_options = client.get_execution_scope_options()
        except Exception as ex:
            scope_error = str(ex)

    state.bridge_version = bridge_status.bridge_version
    state.is_signed_in = bridge_status.is_signed_in
    state.is_connected_to_cloud = bridge_status.is_connected_to_cloud or scope_options is not None
    state.current_user_display_name = bridge_status.current_user_display_name or session_state.display_name or ""
    state.current_user_id = bridge_status.current_user_id or session_state.user_id or ""
    state.can_launch = session_state.can_launch
    state.last_error = scope_error or bridge_status.last_error or session_state.last_error or ""
    state.can_run_on_all_clients = scope_options.can_run_on_all_clients if scope_options else False
    state.group_count = len(scope_options.groups) if scope_options else 0
    state.project_count = len(scope_options.projects) if scope_options else 0
    if state.is_signed_in and scope_error:
        state.status_message = "Signed in. Execution scope unavailable."
    else:
        state.status_message = "Signed in." if state.is_signed_in else "Signed out."


class OUTWIT_OT_bridge_refresh_status(Operator):
    bl_idname = "outwit.bridge_refresh_status"
    bl_label = "Refresh Bridge Status"
    bl_description = "Refresh bridge connection, session, and execution scope state"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            _refresh_bridge_state(context)
            self.report({"INFO"}, "Bridge status refreshed.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Bridge refresh failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_start(Operator):
    bl_idname = "outwit.bridge_start"
    bl_label = "Start Bridge"
    bl_description = "Start the local OmnibusCloud bridge process if it is not already running"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            launch_bridge(context)
            _refresh_bridge_state(context)
            self.report({"INFO"}, "Bridge started.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Bridge start failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_stop(Operator):
    bl_idname = "outwit.bridge_stop"
    bl_label = "Stop Bridge"
    bl_description = "Stop the local OmnibusCloud bridge process tracked by the addon"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            stop_bridge(context)
            state.status_message = "Bridge stopped."
            self.report({"INFO"}, "Bridge stopped.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Bridge stop failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_sign_in(Operator):
    bl_idname = "outwit.bridge_sign_in"
    bl_label = "Sign In"
    bl_description = "Start browser-based sign-in through the local OutWit bridge"

    def execute(self, context):
        state = _get_runtime_state(context)
        client = _get_bridge_client(context)

        try:
            response = client.begin_sign_in()
            _refresh_bridge_state(context)
            message = response.message or "Bridge sign-in started."
            self.report({"INFO"}, message)
            return {"FINISHED" if response.started else "CANCELLED"}
        except BridgeClientError as ex:
            state.last_error = str(ex)
            state.status_message = "Sign-in failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Sign-in failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_sign_out(Operator):
    bl_idname = "outwit.bridge_sign_out"
    bl_label = "Sign Out"
    bl_description = "Sign out the current bridge session"

    def execute(self, context):
        state = _get_runtime_state(context)
        client = _get_bridge_client(context)

        try:
            client.sign_out()
            _refresh_bridge_state(context)
            self.report({"INFO"}, "Bridge session signed out.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Sign-out failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_upload_blend(Operator):
    bl_idname = "outwit.bridge_upload_blend"
    bl_label = "Upload Blend"
    bl_description = "Upload the current .blend file through the local bridge"

    def execute(self, context):
        state = _get_runtime_state(context)
        client = _get_bridge_client(context)

        try:
            response = _upload_current_blend(context)
            state.status_message = "Blend uploaded." if response.uploaded else "Blend upload failed."
            if response.message:
                self.report({"INFO"}, response.message)
            else:
                self.report({"INFO"}, f"Blend uploaded: {response.file_name}")
            return {"FINISHED" if response.uploaded else "CANCELLED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Blend upload failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_validate_blend(Operator):
    bl_idname = "outwit.bridge_validate_blend"
    bl_label = "Validate Blend"
    bl_description = "Run RenderValidateBlend for the last uploaded scene blob"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            _ensure_current_scene_uploaded(context)
            response = _run_validate_blend(context)
            portability_issue = get_dependency_portability_blocking_issue(state.validate_warning_summary)
            policy_message = _validation_policy_message(state)
            state.status_message = portability_issue or policy_message or response.message or response.status or "Blend validation completed."
            self.report(
                {"ERROR" if portability_issue or state.validate_issue_summary else "INFO"},
                state.status_message,
            )
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Blend validation failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_run_preflight(Operator):
    bl_idname = "outwit.bridge_run_preflight"
    bl_label = "Run Preflight"
    bl_description = "Run RenderPreflight using the current scene defaults and addon tile/video settings"

    def execute(self, context):
        state = _get_runtime_state(context)
        scene = context.scene
        client = _get_bridge_client(context)

        try:
            upload_response = _ensure_current_scene_uploaded(context)
            validation_response = _run_validate_blend(context)
            portability_issue = get_dependency_portability_blocking_issue(state.validate_warning_summary)
            simulation_issue = get_simulation_cache_blocking_issue(state.validate_issue_summary)
            if not validation_response.is_valid:
                state.preflight_status = validation_response.status
                blocking_issue = simulation_issue or validation_response.message or _validation_policy_message(state)
                state.preflight_message = blocking_issue
                state.preflight_can_render_all = False
                state.preflight_still_ready = False
                state.preflight_frames_ready = False
                state.preflight_still_tiled_ready = False
                state.preflight_video_ready = False
                state.preflight_still_issue_summary = blocking_issue
                state.preflight_still_warning_summary = state.validate_warning_summary
                state.preflight_frames_issue_summary = blocking_issue
                state.preflight_frames_warning_summary = state.validate_warning_summary
                state.preflight_still_tiled_issue_summary = blocking_issue
                state.preflight_still_tiled_warning_summary = state.validate_warning_summary
                state.preflight_video_issue_summary = blocking_issue
                state.preflight_video_warning_summary = state.validate_warning_summary
                state.preflight_issue_summary = blocking_issue
                state.preflight_warning_summary = state.validate_warning_summary
                state.status_message = blocking_issue
                self.report({"ERROR"}, blocking_issue)
                return {"CANCELLED"}

            if portability_issue:
                state.preflight_status = validation_response.status
                state.preflight_message = portability_issue
                state.preflight_can_render_all = False
                state.preflight_still_ready = False
                state.preflight_frames_ready = False
                state.preflight_still_tiled_ready = False
                state.preflight_video_ready = False
                state.preflight_still_issue_summary = portability_issue
                state.preflight_still_warning_summary = state.validate_warning_summary
                state.preflight_frames_issue_summary = portability_issue
                state.preflight_frames_warning_summary = state.validate_warning_summary
                state.preflight_still_tiled_issue_summary = portability_issue
                state.preflight_still_tiled_warning_summary = state.validate_warning_summary
                state.preflight_video_issue_summary = portability_issue
                state.preflight_video_warning_summary = state.validate_warning_summary
                state.preflight_issue_summary = portability_issue
                state.preflight_warning_summary = state.validate_warning_summary
                state.status_message = portability_issue
                self.report({"ERROR"}, portability_issue)
                return {"CANCELLED"}

            response = _run_preflight(context)
            selected_mode_message = _selected_mode_policy_message(state)
            state.status_message = selected_mode_message
            self.report({"INFO"}, selected_mode_message or response.message or response.status or "Render preflight completed.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Render preflight failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_launch_render(Operator):
    bl_idname = "outwit.bridge_launch_render"
    bl_label = "Launch Render"
    bl_description = "Launch the selected render mode through the local bridge"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            _ensure_current_scene_uploaded(context)
            validation_response = _run_validate_blend(context)
            if not validation_response.is_valid:
                raise BridgeClientError(
                    get_simulation_cache_blocking_issue(state.validate_issue_summary)
                    or validation_response.message
                    or _validation_policy_message(state)
                    or state.validate_issue_summary
                    or "Blend validation reported blocking issues."
                )

            portability_issue = get_dependency_portability_blocking_issue(state.validate_warning_summary)
            if portability_issue:
                raise BridgeClientError(portability_issue)

            _run_preflight(context)
            if not _selected_mode_is_ready(state):
                raise BridgeClientError(_selected_mode_policy_message(state))

            response = _run_selected_launch(context)
            state.status_message = _selected_mode_launched_message(state)
            self.report({"INFO"}, response.message or response.status or "Render launched.")
            return {"FINISHED"}
        except BridgeClientError as ex:
            state.last_error = str(ex)
            state.status_message = str(ex)
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Render launch failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_refresh_job(Operator):
    bl_idname = "outwit.bridge_refresh_job"
    bl_label = "Refresh Job"
    bl_description = "Refresh the current bridge job summary"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            _refresh_active_job_state(context)
            state.status_message = "Job refreshed."
            self.report({"INFO"}, state.active_job_status or "Job refreshed.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Job refresh failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_download_result(Operator):
    bl_idname = "outwit.bridge_download_result"
    bl_label = "Download Result"
    bl_description = "Download the final result of the current bridge job"

    def execute(self, context):
        state = _get_runtime_state(context)
        client = _get_bridge_client(context)

        try:
            if not state.active_job_id:
                raise BridgeClientError("No active bridge job is selected. Launch and refresh a job first.")

            response = client.download_result(state.active_job_id)
            state.download_status = "Downloaded" if response.downloaded else "Not downloaded"
            state.download_message = response.message or ""
            state.download_primary_path = response.local_path
            state.download_primary_file_name = response.file_name
            state.download_item_count = len(response.items)
            state.status_message = "Result downloaded." if response.downloaded else "Result download failed."
            self.report({"INFO"}, response.message or response.file_name or "Result downloaded.")
            return {"FINISHED" if response.downloaded else "CANCELLED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Result download failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_open_result(Operator):
    bl_idname = "outwit.bridge_open_result"
    bl_label = "Open Result"
    bl_description = "Open the downloaded result file with the OS default handler"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            _open_path(state.download_primary_path)
            self.report({"INFO"}, "Opened the downloaded result.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Open result failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_open_result_folder(Operator):
    bl_idname = "outwit.bridge_open_result_folder"
    bl_label = "Open Result Folder"
    bl_description = "Open the folder containing the downloaded result"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            _open_path(state.download_primary_path, open_parent=True)
            self.report({"INFO"}, "Opened the result folder.")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Open result folder failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


class OUTWIT_OT_bridge_load_result_image(Operator):
    bl_idname = "outwit.bridge_load_result_image"
    bl_label = "Load Result Image"
    bl_description = "Load the downloaded image result into Blender"

    def execute(self, context):
        state = _get_runtime_state(context)

        try:
            image = _load_result_image(state.download_primary_path)
            state.status_message = "Result image loaded into Blender."
            self.report({"INFO"}, f"Loaded image: {image.name}")
            return {"FINISHED"}
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Load result image failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}


CLASSES = (
    OUTWIT_OT_bridge_refresh_status,
    OUTWIT_OT_bridge_start,
    OUTWIT_OT_bridge_stop,
    OUTWIT_OT_bridge_sign_in,
    OUTWIT_OT_bridge_sign_out,
    OUTWIT_OT_bridge_upload_blend,
    OUTWIT_OT_bridge_validate_blend,
    OUTWIT_OT_bridge_run_preflight,
    OUTWIT_OT_bridge_launch_render,
    OUTWIT_OT_bridge_refresh_job,
    OUTWIT_OT_bridge_download_result,
    OUTWIT_OT_bridge_open_result,
    OUTWIT_OT_bridge_open_result_folder,
    OUTWIT_OT_bridge_load_result_image,
)
