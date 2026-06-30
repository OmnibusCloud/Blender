from __future__ import annotations

import json
import os
import subprocess
import sys

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from .bridge_async import AsyncCall, JobMonitor, TERMINAL_STATUSES
from .bridge_client import BridgeClient, BridgeClientError
from .bridge_context import load_latest_context, try_load_latest_context
from .bridge_dependency_policy import (
    get_dependency_portability_blocking_issue,
    get_non_simulation_validation_issue,
    get_simulation_cache_blocking_issue,
    resolve_bake_plan,
)
from .bridge_engine_routing import (
    detect_scene_engine_family,
    get_scene_engine_token,
    recommended_render_mode,
    scene_frame_count,
    SceneEngineRoutingError,
)
from .bridge_launcher import (
    acquire_bridge_lease,
    apply_launched_state,
    cleanup_bridge_on_unregister,
    ensure_bridge_running,
    get_effective_context_directory,
    is_process_running,
    launch_bridge,
    panel_was_seen,
    ping_bridge_lease,
    refresh_bridge_process_state,
    release_bridge_lease,
    resolve_launch_target,
    spawn_bridge_process,
    stop_bridge,
)
from .bridge_render_settings import (
    compose_remember_payload,
    compose_sticky_payload,
    group_name_for,
    resolve_target_seed,
    seed_prop_values,
)
from .bridge_scene_attachments import collect_scene_attachment_metadata, summarize_scene_attachment_metadata
from .bridge_scene_packaging import create_packed_upload_copy, scene_output_signature, ScenePackagingError
from .bridge_state import ALL_CLIENTS_GROUP_ID, NO_GROUP_ID, apply_render_mode_to_axes

FORMAT_PNG = 0
FORMAT_EXR = 1
FORMAT_JPEG = 2
FORMAT_TIFF = 3
FORMAT_WEBP = 4

# VideoFormat wire enum (OutWit.Controller.Render.Model.VideoFormat): 0 = Default (legacy MP4/H.264).
VIDEO_FORMAT_MP4_H264 = 1
VIDEO_FORMAT_MP4_H265 = 2
VIDEO_FORMAT_WEBM_VP9 = 3
VIDEO_FORMAT_MOV_PRORES_422HQ = 4
VIDEO_FORMAT_MOV_PRORES_4444 = 5

# RenderColorMode / RenderFilmTransparency / RenderColorDepth — int values mirror the C# enum
# declaration order in OutWit.Controller.Render.Model. 0 = Default (controller reproduces legacy
# behaviour), so an old server that ignores these keys is unaffected.
COLOR_MODE_DEFAULT = 0
COLOR_MODE_RGB = 1
COLOR_MODE_RGBA = 2

FILM_TRANSPARENCY_DEFAULT = 0
FILM_TRANSPARENCY_OPAQUE = 1
FILM_TRANSPARENCY_TRANSPARENT = 2

COLOR_DEPTH_DEFAULT = 0
COLOR_DEPTH_8 = 1
COLOR_DEPTH_16 = 2
COLOR_DEPTH_32 = 3

BLEND_MODE_CENTER_PRIORITY_CROP = 0


def _map_render_format(file_format: str) -> int:
    """Maps Blender's image_settings.file_format to the controller's RenderFormat. Unsupported formats
    fall back to PNG (compute_status blocks them in the UI before a launch can reach this)."""
    return {
        "PNG": FORMAT_PNG,
        "OPEN_EXR": FORMAT_EXR,
        "OPEN_EXR_MULTILAYER": FORMAT_EXR,
        "JPEG": FORMAT_JPEG,
        "TIFF": FORMAT_TIFF,
        "WEBP": FORMAT_WEBP,
    }.get(file_format or "", FORMAT_PNG)


def _map_video_format(video_format: str) -> int:
    """Maps the addon's video preset identifier to the controller's VideoFormat wire enum."""
    return {
        "MP4_H264": VIDEO_FORMAT_MP4_H264,
        "MP4_H265": VIDEO_FORMAT_MP4_H265,
        "WEBM_VP9": VIDEO_FORMAT_WEBM_VP9,
        "MOV_PRORES_422HQ": VIDEO_FORMAT_MOV_PRORES_422HQ,
        "MOV_PRORES_4444": VIDEO_FORMAT_MOV_PRORES_4444,
    }.get(video_format or "", VIDEO_FORMAT_MP4_H264)


def _map_color_mode(color_mode: str) -> int:
    if color_mode == "RGBA":
        return COLOR_MODE_RGBA
    if color_mode == "RGB":
        return COLOR_MODE_RGB
    return COLOR_MODE_DEFAULT


def _map_color_depth(color_depth: str) -> int:
    return {
        "8": COLOR_DEPTH_8,
        "16": COLOR_DEPTH_16,
        "32": COLOR_DEPTH_32,
    }.get(color_depth or "", COLOR_DEPTH_DEFAULT)


# Background monitor for the active job (polls GetJob off the UI thread). Owned by the auto-refresh
# timer, which (re)starts it from (auto_refresh_active_job, active_job_id) and stops it on terminal/reset.
_active_job_monitor: "JobMonitor | None" = None

# Guards against a second Launch while one is mid-flight (the modal upload is non-blocking, so the UI
# stays clickable). Set in the launch operator's execute, cleared when it finishes/cancels.
_launch_in_progress = False

# How often the monitor polls GetJob while a job runs (seconds). Off the UI thread, so it can be brisk.
_JOB_MONITOR_INTERVAL_SECONDS = 1.5


def _tag_job_areas_redraw() -> None:
    window_manager = getattr(bpy.context, "window_manager", None)
    if window_manager is None:
        return
    for window in window_manager.windows:
        screen = getattr(window, "screen", None)
        if screen is None:
            continue
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def _stop_job_monitor() -> None:
    global _active_job_monitor
    if _active_job_monitor is not None:
        _active_job_monitor.stop()
        _active_job_monitor = None


def _get_context_directory(context) -> str:
    return get_effective_context_directory(context)


def _get_selected_client_group_id(state) -> str:
    """Resolves the render target to a group id, or '' for the unscoped 'all nodes' option.
    'All nodes' is now the run_on_all_nodes checkbox (only honoured when the account allows it); the
    Target dropdown carries groups only."""
    if getattr(state, "run_on_all_nodes", False) and getattr(state, "can_run_on_all_clients", False):
        return ""
    selected = getattr(state, "selected_client_group", "") or ""
    if not selected or selected in (ALL_CLIENTS_GROUP_ID, NO_GROUP_ID):
        return ""
    return selected


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
    image_settings = render.image_settings

    # Faithful snapshot of the scene's output settings so the cloud render matches the artist's setup:
    # real output format (PNG/EXR/JPEG, not hardcoded PNG), colour mode (alpha/RGBA), film transparency
    # and bit depth. The controller honours these; older servers ignore the new keys (legacy behaviour).
    return {
        "Format": _map_render_format(getattr(image_settings, "file_format", "") or ""),
        "Engine": engine_enum,
        "Samples": _get_scene_samples(scene, engine_family),
        "ResolutionX": resolution_x,
        "ResolutionY": resolution_y,
        "Denoise": _get_scene_denoise(scene, engine_family),
        "ColorMode": _map_color_mode(getattr(image_settings, "color_mode", "") or ""),
        "FilmTransparent": FILM_TRANSPARENCY_TRANSPARENT
            if bool(getattr(render, "film_transparent", False))
            else FILM_TRANSPARENCY_OPAQUE,
        "ColorDepth": _map_color_depth(getattr(image_settings, "color_depth", "") or ""),
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
        "Format": _map_video_format(getattr(state, "video_format", "")),
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


def _launch_bake_plan(state):
    """The bake plan for the current scene, keyed on the cloud validator's verdict.

    The authoritative "is there an unbaked simulation?" signal at launch is the validator's
    simulation-cache block — it is what the farm would refuse — not the local scene scan (which
    drives the panel's instant preview and should agree). Returns a ``BakePlan`` (see
    ``bridge_dependency_policy.resolve_bake_plan``): how the artist's ``bake_strategy`` resolves
    (or fails to resolve) that block.
    """
    from .bridge_dependency_policy import LOCAL_BAKE_AVAILABLE

    simulation_issue = get_simulation_cache_blocking_issue(state.validate_issue_summary)
    return resolve_bake_plan(
        bool(simulation_issue),
        getattr(state, "bake_strategy", "DELEGATED"),
        LOCAL_BAKE_AVAILABLE,
    )


def _validation_policy_message(state) -> str:
    portability_issue = get_dependency_portability_blocking_issue(state.validate_warning_summary)
    if portability_issue:
        return portability_issue

    simulation_issue = get_simulation_cache_blocking_issue(state.validate_issue_summary)
    if simulation_issue:
        plan = _launch_bake_plan(state)
        if plan.block:
            return plan.block

        if plan.should_delegate or plan.should_local:
            # A bake plan covers the simulation block — surface any OTHER hard validation issue a
            # bake will NOT fix, otherwise report what the bake will do.
            other_issue = get_non_simulation_validation_issue(state.validate_issue_summary)
            if other_issue:
                return _compose_policy_message("Scene blocked by validation.", other_issue)

            where = "render farm" if plan.should_delegate else "this computer"
            return f"Simulation will be baked on the {where} before rendering."

        return simulation_issue

    if state.validate_issue_summary:
        return _compose_policy_message("Scene blocked by validation.", state.validate_issue_summary)

    if state.validate_warning_summary:
        return _compose_policy_message("Scene validated with warnings.", state.validate_warning_summary)

    return "Scene validated."


def _validation_is_blocked(state) -> bool:
    """True when validation has a hard block the artist must resolve (after accounting for the bake
    plan). A simulation covered by the chosen bake strategy is NOT a block; a strategy that cannot
    bake (LOCAL before its driver ships), a dependency-portability issue, or any non-simulation
    validation issue IS."""
    if get_dependency_portability_blocking_issue(state.validate_warning_summary):
        return True

    plan = _launch_bake_plan(state)
    if plan.block or get_non_simulation_validation_issue(state.validate_issue_summary):
        return True

    return bool(state.validate_issue_summary) and not (plan.should_delegate or plan.should_local)


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


def _blend_file_mtime(blend_path: str) -> str:
    """The source .blend's last-modified time as a stable string, for the upload-cache key. Empty when
    the path is missing/unreadable (the path/signature checks still apply then)."""
    try:
        return repr(os.path.getmtime(blend_path))
    except OSError:
        return ""


def _scene_requires_upload(state, blend_path: str, output_signature: str) -> bool:
    # The path alone is NOT enough: output settings that travel inside the .blend (format family,
    # color mode/depth, transparency, video container/codec) make the cached blob stale when changed —
    # and so does ANY other edit saved into the .blend (a camera added, materials tweaked, the sim
    # re-baked). The file's modification time covers all of those: re-saving always re-uploads.
    return (
        not state.uploaded_blob_id
        or state.uploaded_source_path != blend_path
        or state.uploaded_output_signature != output_signature
        or getattr(state, "uploaded_source_mtime", "") != _blend_file_mtime(blend_path)
    )


def _upload_current_blend(context):
    state = _get_runtime_state(context)
    client = _get_bridge_client(context)
    blend_path = _get_current_blend_path()
    output_signature = scene_output_signature(context.scene)
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
    state.uploaded_output_signature = output_signature
    state.uploaded_source_mtime = _blend_file_mtime(blend_path)
    state.uploaded_file_name = response.file_name
    state.uploaded_file_size = response.file_size
    state.uploaded_attachment_manifest_json = json.dumps(attachments, ensure_ascii=False)
    state.upload_message = upload_message or response.message or ("Upload completed." if response.uploaded else "Upload did not complete.")
    return response


def _ensure_current_scene_uploaded(context):
    state = _get_runtime_state(context)
    blend_path = _get_current_blend_path()
    if _scene_requires_upload(state, blend_path, scene_output_signature(context.scene)):
        return _upload_current_blend(context)

    state.current_blend_path = blend_path
    return None


def _upload_worker(context_directory: str, blend_path: str, planned_attachments: list) -> dict:
    """Runs the SLOW part of a launch off the UI thread: attachment uploads + scene pack + .blend
    upload. No bpy access (Blender is not thread-safe) — the caller gathers all scene data first."""
    client = BridgeClient(context_directory)
    attachments = _upload_scene_attachments(client, planned_attachments)
    try:
        with create_packed_upload_copy(blend_path) as (upload_path, packed_message):
            response = client.upload_blend(upload_path)
            upload_message = packed_message
    except ScenePackagingError:
        response = client.upload_blend(blend_path)
        upload_message = ""
    return {"response": response, "attachments": attachments, "upload_message": upload_message}


def _apply_upload_result(state, blend_path: str, output_signature: str, result: dict) -> None:
    response = result["response"]
    state.current_blend_path = blend_path
    state.uploaded_blob_id = response.blob_id
    state.uploaded_source_path = blend_path
    state.uploaded_output_signature = output_signature
    state.uploaded_source_mtime = _blend_file_mtime(blend_path)
    state.uploaded_file_name = response.file_name
    state.uploaded_file_size = response.file_size
    state.uploaded_attachment_manifest_json = json.dumps(result["attachments"], ensure_ascii=False)
    state.upload_message = result["upload_message"] or response.message or (
        "Upload completed." if response.uploaded else "Upload did not complete."
    )


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
    state.active_job_cancel_requested = False
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
    elif response.status == "Completed":
        # Compute finished; the server marks Completed before the result blob is materialised. Show a
        # full bar with a "finalizing" note instead of a stuck 99% (the old finalize-race "hang").
        progress_text = "Finalizing result..."
    elif progress_value <= 0.0:
        progress_text = "Starting..."
    else:
        progress_text = f"{min(progress_value, 99.0):.1f}%"

    # Snap the bar to full on any terminal status (Completed-finalizing, Failed, Cancelled).
    overall_factor = 1.0 if (is_completed or is_terminal_status) else max(0.0, min(progress_value / 100.0, 1.0))

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
    global _active_job_monitor
    context = getattr(bpy, "context", None)
    window_manager = getattr(context, "window_manager", None)
    state = getattr(window_manager, "outwit_bridge_state", None)
    if state is None:
        return 5.0

    idle_interval = float(max(1, int(state.auto_refresh_interval_seconds)))
    if not state.auto_refresh_active_job or not state.active_job_id:
        _stop_job_monitor()
        return idle_interval

    # Ensure a background monitor for the current job. It polls GetJob OFF the UI thread, so progress
    # no longer stalls on a slow main-thread poll, and the loop below only applies cheap snapshots.
    monitor = _active_job_monitor
    if monitor is None or monitor.job_id != state.active_job_id or monitor.stopped:
        _stop_job_monitor()
        try:
            _active_job_monitor = JobMonitor(
                _get_context_directory(context), state.active_job_id, _JOB_MONITOR_INTERVAL_SECONDS
            ).start()
            monitor = _active_job_monitor
        except Exception as ex:
            state.last_error = str(ex)
            return idle_interval

    snapshot, error, terminal = monitor.snapshot()
    if snapshot is not None:
        try:
            _apply_get_job_response(state, snapshot)
            _tag_job_areas_redraw()
        except Exception as ex:
            state.last_error = str(ex)
    elif error is not None:
        state.last_error = str(error)

    if terminal or state.active_job_is_completed:
        _stop_job_monitor()
        state.auto_refresh_active_job = False
        status = state.active_job_status or "finished"
        state.status_message = "Job completed." if status == "Completed" else f"Job {status.lower()}."
        _tag_job_areas_redraw()
        return idle_interval

    # While a job runs, tick the UI quickly to surface progress (the monitor itself polls at its own rate).
    return 0.5


# Lazy-first-start orchestration. The spawn is slow (Popen + wait-for-context up to 15 s) so it runs
# on a worker thread; this state lives on the main thread and is pumped by the persistent heartbeat
# timer. _lazy_launch_call is the in-flight spawn; _lazy_launch_failed latches after a failure (e.g.
# binary not found) to stop a respawn storm until something re-arms it (manual Connect / Phase-4
# auto-reconnect on a recoverable cause).
_lazy_launch_call: AsyncCall | None = None
_lazy_launch_failed = False

# Bridge PID whose cloud/session state we already pulled. The bridge RESTORES the persisted login
# by itself at startup, but is_signed_in was only ever written by operator-driven
# _refresh_bridge_state — so after every Blender restart the panel showed "Not signed in" over a
# perfectly restored session and users re-logged-in for nothing (live-debugged 2026-06-11: the log
# showed "Bridge session restored successfully" and ZERO state queries from the addon). The
# heartbeat now pulls the state once per bridge process as soon as it is reachable.
_session_state_synced_pid = 0

# Phase 5 persisted render preferences — session latches. The bridge OWNS the storage; we seed the
# transient props once per Blender session when the bridge becomes reachable (_pump_render_settings),
# seed the remembered TARGET once when the execution scope is known (_refresh_bridge_state), and
# sticky-write the used values after a successful submit. _applying_settings_seed suppresses the
# prefs-toggle update callback while the seed itself writes the toggle (echo guard);
# _remember_push_pending keeps a toggle flip alive until the bridge is reachable again.
_render_settings_seeded = False
_render_settings_target_seeded = False
_remember_push_pending = False
_applying_settings_seed = False
# A bucket-1 value changed in the UI → the heartbeat pump pushes it to the bridge store. This is what
# makes preferences survive a Blender restart WITHOUT requiring a submit (live finding 2026-06-12:
# sticky-on-submit alone read as "my settings are not saved").
_render_settings_values_pending = False
# Suppress change-marking while values are written PROGRAMMATICALLY (.blend-open recommendation) —
# only user edits should persist, or opening a still scene would erase a remembered split=on.
_suppress_settings_marking = False

# Last connection-relevant state shown in the panel. The heartbeat timer changes this state off the
# draw cycle, but Blender does not repaint the N-panel until a UI event (the "stuck on Connecting…
# until you hover" symptom). When the signature changes we tag the 3D areas for redraw so the panel
# reflects the new phase immediately — this is what lets us drop the manual Refresh button.
_last_conn_signature: tuple | None = None


def _connection_signature(state) -> tuple:
    return (
        bool(getattr(state, "bridge_is_running", False)),
        bool(getattr(state, "is_signed_in", False)),
        bool(getattr(state, "bridge_lease_acquired", False)),
        getattr(state, "bridge_launch_message", ""),
        getattr(state, "last_error", ""),
        getattr(state, "active_job_status", ""),
        # The Save-scene button is gated on the LIVE dirty flag — repaint when it flips so the
        # button appears/disappears without waiting for a mouse-over.
        bool(getattr(bpy.data, "is_dirty", False)),
    )


def _redraw_on_connection_change(state) -> None:
    global _last_conn_signature
    signature = _connection_signature(state)
    if signature != _last_conn_signature:
        _last_conn_signature = signature
        _tag_job_areas_redraw()


def _addon_auto_start_enabled(context) -> bool:
    try:
        return bool(context.preferences.addons[__package__].preferences.auto_start_bridge)
    except Exception:
        return False


def rearm_lazy_first_start() -> None:
    """Clear the failure latch so the heartbeat timer will attempt a lazy launch again. Called by the
    manual Connect path and (Phase 4) by auto-reconnect on a recoverable cause."""
    global _lazy_launch_failed
    _lazy_launch_failed = False


def _try_adopt_running_bridge(context) -> bool:
    """Re-attach to a bridge that is ALREADY running instead of spawning a second one. Opening
    another .blend replaces the WindowManager — and with it our runtime state (bridge PID, lease
    id) — while the bridge process is alive and holding the port: a blind spawn then crashes on
    the busy port, latches the failure, and the orphaned bridge kills itself when its un-pinged
    lease expires (live finding 2026-06-12). Re-discover it through the connection-context file."""
    state = _get_runtime_state(context)
    try:
        executable_path, session_directory = resolve_launch_target(context)
        bridge_context, context_path = try_load_latest_context(str(session_directory))
    except Exception:
        return False

    if bridge_context is None or context_path is None:
        return False
    if not is_process_running(int(bridge_context.bridge_process_id or 0)):
        return False

    state.bridge_process_id = bridge_context.bridge_process_id
    state.bridge_is_running = True
    state.bridge_started_by_addon = True
    state.bridge_executable_path = str(executable_path)
    state.bridge_session_directory = os.path.dirname(context_path)
    state.bridge_launch_message = "Reconnected to the running bridge."
    try:
        # A fresh lease replaces the stale one well before its timeout, so the watchdog stands down.
        acquire_bridge_lease(context)
    except Exception as ex:  # noqa: BLE001 - surfaced in state; retried by the heartbeat
        state.last_error = str(ex)
    return True


def _pump_lazy_first_start(context) -> None:
    """Drive the one-time lazy bridge launch from the persistent heartbeat timer (main thread). The
    slow spawn runs on a worker; this only marshals its result back and writes state. No-op once the
    bridge is running, before the panel has been shown, or while the failure latch is set."""
    global _lazy_launch_call, _lazy_launch_failed
    state = context.window_manager.outwit_bridge_state

    # Marshal an in-flight spawn.
    if _lazy_launch_call is not None:
        if not _lazy_launch_call.done:
            return
        call, _lazy_launch_call = _lazy_launch_call, None
        if call.error is not None:
            _lazy_launch_failed = True
            state.last_error = str(call.error)
            state.bridge_launch_message = "Bridge auto-start failed."
            return
        process_id, executable_path, session_directory = call.result
        apply_launched_state(state, process_id, executable_path, session_directory)
        try:
            acquire_bridge_lease(context)
        except Exception as ex:  # noqa: BLE001 - surfaced in state, watchdog still protects
            state.last_error = str(ex)
        return

    # Decide whether to begin one: lazy-first-start fires only after the panel has been shown.
    if state.bridge_is_running or _lazy_launch_failed:
        return
    if not panel_was_seen() or not _addon_auto_start_enabled(context):
        return

    # A bridge may already be running (state was reset by a .blend load) — adopt it, never spawn
    # a duplicate onto the same port.
    if _try_adopt_running_bridge(context):
        return

    try:
        executable_path, session_directory = resolve_launch_target(context)
    except BridgeClientError as ex:
        # Binary not found → BridgeMissing. Latch so we don't respawn-storm; manual Locate re-arms.
        _lazy_launch_failed = True
        state.last_error = str(ex)
        state.bridge_launch_message = "Bridge executable not found."
        return

    state.bridge_launch_message = "Starting bridge…"
    _lazy_launch_call = AsyncCall(
        lambda e=executable_path, s=session_directory: (spawn_bridge_process(e, s), e, s)
    ).start()


def _get_addon_preferences(context):
    try:
        return context.preferences.addons[__package__].preferences
    except Exception:
        return None


def _remember_render_settings_enabled(context) -> bool:
    return bool(getattr(_get_addon_preferences(context), "remember_render_settings", True))


def _apply_render_settings_seed(context, settings) -> None:
    """Write the persisted preferences into the transient UI props (main thread). The master flag
    lands on the addon preferences toggle under the echo guard so its update callback does not
    push the value straight back to the bridge."""
    global _applying_settings_seed
    state = _get_runtime_state(context)
    _applying_settings_seed = True
    try:
        prefs = _get_addon_preferences(context)
        if prefs is not None:
            prefs.remember_render_settings = settings.remember_render_settings
        for prop, value in seed_prop_values(settings).items():
            setattr(state, prop, value)
    finally:
        _applying_settings_seed = False


def _pump_session_state_sync(context) -> None:
    """One-shot per bridge process: pull bridge/session/scope state as soon as the bridge is
    reachable, so a session the bridge restored at startup (persisted token) becomes visible in
    the panel without any manual click. Retries every heartbeat until the first success; re-arms
    automatically when the bridge process changes (relaunch)."""
    global _session_state_synced_pid
    state = _get_runtime_state(context)
    if not state.bridge_is_running or not state.bridge_lease_acquired:
        return

    pid = int(state.bridge_process_id or 0)
    if pid <= 0 or pid == _session_state_synced_pid:
        return

    try:
        _refresh_bridge_state(context)
    except Exception:
        return  # bridge REST still warming up (or no scene in this timer tick) — retry next beat

    _session_state_synced_pid = pid


def mark_render_settings_changed() -> None:
    """A bucket-1 preference changed in the UI → queue a push to the bridge store (the heartbeat
    pump performs the REST write, so prop update callbacks never block the UI on I/O). Suppressed
    while values are being APPLIED rather than edited (seed, .blend-open recommendation)."""
    global _render_settings_values_pending
    if _applying_settings_seed or _suppress_settings_marking:
        return
    _render_settings_values_pending = True


def flush_render_settings_on_unregister() -> None:
    """Best-effort final push of a pending preference change on addon disable / Blender quit —
    the heartbeat may not get another tick after the last edit."""
    if not _render_settings_values_pending:
        return

    context = getattr(bpy, "context", None)
    if context is None:
        return

    try:
        _push_render_settings(context)
    except Exception:
        pass


def _pump_render_settings(context) -> None:
    """Seed the UI from the bridge's persisted render preferences (once per Blender session) and
    push pending changes (master toggle / bucket-1 values). Quiet best-effort off the heartbeat:
    the bridge REST may still be warming up — we simply try again next tick."""
    global _render_settings_seeded, _render_settings_values_pending
    state = _get_runtime_state(context)
    if not state.bridge_is_running or not state.bridge_lease_acquired:
        return

    if not _render_settings_seeded:
        try:
            settings = _get_bridge_client(context).get_render_settings()
        except Exception:
            return
        _apply_render_settings_seed(context, settings)
        _render_settings_seeded = True
        return

    if _remember_push_pending:
        try:
            _push_remember_render_settings(context)
        except Exception:
            pass

    if _render_settings_values_pending and _remember_render_settings_enabled(context):
        try:
            _push_render_settings(context)
            _render_settings_values_pending = False
        except Exception:
            pass


def _push_remember_render_settings(context) -> None:
    """Persist the master toggle: read-modify-write so only the flag changes on the bridge."""
    global _remember_push_pending
    client = _get_bridge_client(context)
    current = client.get_render_settings()
    client.set_render_settings(
        compose_remember_payload(current, _remember_render_settings_enabled(context)))
    _remember_push_pending = False


def on_remember_render_settings_changed(context) -> None:
    """Update-callback target for the preferences master toggle (a transient binding — the bridge
    owns the value). Push now when reachable; otherwise leave it pending for the heartbeat pump."""
    global _remember_push_pending
    if _applying_settings_seed:
        return
    _remember_push_pending = True
    try:
        _push_remember_render_settings(context)
    except Exception:
        pass


def _seed_remembered_target(context, client) -> None:
    """Restore the remembered render target once the execution scope (groups) is known — the group
    dropdown can only be set to ids that exist in the freshly written groups_json. One attempt per
    Blender session; a vanished group simply leaves the default selection (the agreed fallback)."""
    global _render_settings_target_seeded
    state = _get_runtime_state(context)
    if _render_settings_target_seeded:
        return
    _render_settings_target_seeded = True

    try:
        settings = client.get_render_settings()
        groups = json.loads(state.groups_json) if state.groups_json else []
        target = resolve_target_seed(settings, groups, state.can_run_on_all_clients)
    except Exception:
        return

    if target is None:
        return

    global _applying_settings_seed
    _applying_settings_seed = True
    try:
        group_id, run_on_all = target
        state.run_on_all_nodes = run_on_all
        if group_id:
            state.selected_client_group = group_id
    finally:
        _applying_settings_seed = False


def _push_render_settings(context) -> None:
    """Read-modify-write the bucket-1 values currently in the UI into the bridge store."""
    state = _get_runtime_state(context)
    client = _get_bridge_client(context)
    current = client.get_render_settings()
    group_id = _get_selected_client_group_id(state)
    groups = json.loads(state.groups_json) if state.groups_json else []
    client.set_render_settings(compose_sticky_payload(
        current,
        remember=True,
        split_frame=state.split_frame,
        tiles_x=int(state.tiles_x),
        tiles_y=int(state.tiles_y),
        tile_overlap=int(state.tile_overlap_px),
        anim_result=state.anim_result,
        video_format=getattr(state, "video_format", ""),
        video_crf=int(state.video_constant_rate_factor),
        group_id=group_id,
        group_name=group_name_for(groups, group_id),
        bake_strategy=getattr(state, "bake_strategy", "DELEGATED"),
    ))


def _sticky_render_settings_after_submit(context) -> None:
    """Persist the values the submit actually used (under the master toggle). Best-effort: a
    settings-persistence failure must never fail a successful launch."""
    global _render_settings_values_pending
    try:
        if not _remember_render_settings_enabled(context):
            return
        _push_render_settings(context)
        _render_settings_values_pending = False
    except Exception:
        pass


def _bridge_lease_timer() -> float:
    context = getattr(bpy, "context", None)
    window_manager = getattr(context, "window_manager", None)
    state = getattr(window_manager, "outwit_bridge_state", None)
    if state is None:
        return 5.0

    refresh_bridge_process_state(context)
    _pump_lazy_first_start(context)
    _pump_session_state_sync(context)
    _pump_render_settings(context)
    # Repaint the panel when the connection phase changes (heartbeat-driven; replaces manual Refresh).
    _redraw_on_connection_change(state)
    interval = float(max(1, int(state.bridge_heartbeat_interval_seconds or 5)))

    # While a lazy launch is spawning, tick fast so its result is marshalled back promptly.
    if _lazy_launch_call is not None:
        return 0.5

    if not state.bridge_is_running or not state.bridge_lease_id:
        return interval

    try:
        ping_bridge_lease(context)
    except Exception as ex:
        state.bridge_lease_acquired = False
        state.last_error = str(ex)
        state.status_message = "Bridge lease heartbeat failed."

    return interval


@bpy.app.handlers.persistent
def _on_blend_load(_unused) -> None:
    # Opening a .blend replaces the WindowManager — our runtime state resets to defaults. Re-arm
    # the one-shot session/seed latches so the heartbeat re-pulls sign-in/scope state and re-seeds
    # the remembered preferences into the fresh state (the bridge itself keeps running and is
    # re-adopted by _try_adopt_running_bridge).
    global _session_state_synced_pid, _render_settings_seeded, _render_settings_target_seeded
    _session_state_synced_pid = 0
    _render_settings_seeded = False
    _render_settings_target_seeded = False

    # Default the render mode to the one that fits the scene's output settings, so a still
    # scene doesn't sit on Video (and vice versa). The user can still change it. The axes writes here
    # are PROGRAMMATIC — suppress preference persistence, or opening a still scene would erase a
    # remembered split=on from the bridge store.
    global _suppress_settings_marking
    try:
        window_manager = getattr(bpy.context, "window_manager", None)
        state = getattr(window_manager, "outwit_bridge_state", None)
        scene = getattr(bpy.context, "scene", None)
        if state is not None and scene is not None:
            _suppress_settings_marking = True
            try:
                state.render_mode = recommended_render_mode(scene)
                apply_render_mode_to_axes(state)
            finally:
                _suppress_settings_marking = False
    except Exception:
        _suppress_settings_marking = False


def register_timers() -> None:
    if not bpy.app.timers.is_registered(_auto_refresh_job_timer):
        bpy.app.timers.register(_auto_refresh_job_timer, first_interval=5.0, persistent=True)

    if not bpy.app.timers.is_registered(_bridge_lease_timer):
        bpy.app.timers.register(_bridge_lease_timer, first_interval=5.0, persistent=True)

    if _on_blend_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_blend_load)


def unregister_timers() -> None:
    if bpy.app.timers.is_registered(_auto_refresh_job_timer):
        bpy.app.timers.unregister(_auto_refresh_job_timer)

    # The lease heartbeat timer is registered in register_timers but was previously
    # leaked here — on addon reload it stayed alive referencing stale state. Snap it
    # down with its sibling.
    if bpy.app.timers.is_registered(_bridge_lease_timer):
        bpy.app.timers.unregister(_bridge_lease_timer)

    if _on_blend_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_blend_load)


def _run_selected_launch(context, *, bake: bool = False):
    """Submit the selected render mode. When ``bake`` is set, route to the controller's
    BakeAndRender* scripts (delegated simulation bake, then distributed render of the baked scene)
    instead of the plain Render* scripts — the only safe path for an unbaked simulation."""
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
    group_id = _get_selected_client_group_id(state)
    attachments = _get_uploaded_attachment_manifest(state)

    if state.render_mode == "Still":
        run = client.run_bake_and_render_still if bake else client.run_render_still
        response = run(blob_id, still_frame, render_options, attachments, group_id)
        _apply_job_response(state, response, "BakeAndRenderStill" if bake else "RenderStill")
        return response

    if state.render_mode == "StillTiled":
        run = client.run_bake_and_render_still_tiled if bake else client.run_render_still_tiled
        response = run(
            blob_id,
            still_frame,
            int(state.tiles_x),
            int(state.tiles_y),
            render_options,
            _collect_tile_options(state),
            attachments,
            group_id,
        )
        _apply_job_response(state, response, "BakeAndRenderStillTiled" if bake else "RenderStillTiled")
        return response

    if state.render_mode == "Frames":
        run = client.run_bake_and_render_frames if bake else client.run_render_frames
        response = run(
            blob_id,
            int(scene.frame_start),
            int(scene.frame_end),
            render_options,
            attachments,
            group_id,
        )
        _apply_job_response(state, response, "BakeAndRenderFrames" if bake else "RenderFrames")
        return response

    run = client.run_bake_and_render_video if bake else client.run_render_video
    response = run(
        blob_id,
        int(scene.frame_start),
        int(scene.frame_end),
        render_options,
        _collect_video_options(state),
        attachments,
        group_id,
    )
    _apply_job_response(state, response, "BakeAndRenderVideo" if bake else "RenderVideo")
    return response


def _point_cache_baked(point_cache) -> bool:
    """True when a (cloth/soft-body/particle/rigid-body) point cache is baked. None-safe."""
    return bool(getattr(point_cache, "is_baked", False)) if point_cache is not None else False


def _dynamic_paint_baked(modifier) -> bool:
    """True when any Dynamic Paint canvas surface is baked (its cache lives per-surface, not on the
    modifier)."""
    canvas = getattr(modifier, "canvas_settings", None)
    surfaces = getattr(canvas, "canvas_surfaces", []) if canvas is not None else []
    return any(_point_cache_baked(getattr(surface, "point_cache", None)) for surface in surfaces)


def _has_geometry_nodes_simulation(modifier) -> bool:
    """True when a Geometry Nodes modifier exposes bake targets (a simulation/bake zone)."""
    bakes = getattr(modifier, "bakes", None)
    return bool(bakes) and len(bakes) > 0


def _scan_scene_simulations(scene):
    """Walk the active scene for bakeable simulations and classify them (see bridge_simulation).

    Mirrors the controller's taxonomy: Mantaflow fluid domains, cloth / soft body / dynamic paint
    modifiers, dynamic particle systems (static hair regenerates deterministically and is excluded),
    rigid body, and Geometry-Nodes simulation zones. Geometry-Nodes bake state has no simple flag, so
    GN is reported unbaked — that only refines the panel wording; the gate keys on presence and a farm
    rebake is harmless. Fully defensive: a partially-defined modifier must never raise inside a UI
    refresh.
    """
    from .bridge_simulation import (
        SimulationDescriptor,
        summarize_simulations,
        SIM_FLUID,
        SIM_CLOTH,
        SIM_SOFT_BODY,
        SIM_DYNAMIC_PAINT,
        SIM_PARTICLES,
        SIM_RIGID_BODY,
        SIM_GEOMETRY_NODES,
    )

    descriptors = []
    for obj in getattr(scene, "objects", []):
        for modifier in getattr(obj, "modifiers", []):
            try:
                modifier_type = getattr(modifier, "type", "")
                if modifier_type == "FLUID" and getattr(modifier, "fluid_type", "") == "DOMAIN":
                    domain = getattr(modifier, "domain_settings", None)
                    baked = bool(getattr(domain, "has_cache_baked_data",
                                         getattr(domain, "is_cache_baked_data", False))) if domain else False
                    descriptors.append(SimulationDescriptor(SIM_FLUID, baked))
                elif modifier_type == "CLOTH":
                    descriptors.append(SimulationDescriptor(SIM_CLOTH, _point_cache_baked(getattr(modifier, "point_cache", None))))
                elif modifier_type == "SOFT_BODY":
                    descriptors.append(SimulationDescriptor(SIM_SOFT_BODY, _point_cache_baked(getattr(modifier, "point_cache", None))))
                elif modifier_type == "DYNAMIC_PAINT":
                    descriptors.append(SimulationDescriptor(SIM_DYNAMIC_PAINT, _dynamic_paint_baked(modifier)))
                elif modifier_type == "NODES" and _has_geometry_nodes_simulation(modifier):
                    descriptors.append(SimulationDescriptor(SIM_GEOMETRY_NODES, False))
            except Exception:
                continue

        for particle_system in getattr(obj, "particle_systems", []):
            try:
                settings = getattr(particle_system, "settings", None)
                if settings is None:
                    continue
                # Static hair (no hair dynamics) regenerates deterministically per frame — not a sim.
                # NB: use_hair_dynamics lives on the ParticleSystem, not ParticleSettings.
                if getattr(settings, "type", "") == "HAIR" and not getattr(particle_system, "use_hair_dynamics", False):
                    continue
                descriptors.append(SimulationDescriptor(SIM_PARTICLES, _point_cache_baked(getattr(particle_system, "point_cache", None))))
            except Exception:
                continue

    rigidbody_world = getattr(scene, "rigidbody_world", None)
    if rigidbody_world is not None:
        collection = getattr(rigidbody_world, "collection", None) or getattr(rigidbody_world, "group", None)
        if collection is not None and len(getattr(collection, "objects", [])) > 0:
            descriptors.append(SimulationDescriptor(SIM_RIGID_BODY, _point_cache_baked(getattr(rigidbody_world, "point_cache", None))))

    return summarize_simulations(descriptors)


# region Local bake ("On this computer" strategy)
#
# Bake the scene's simulations in the artist's running Blender, then upload the BAKED scene + collected
# fluid caches and render through the PLAIN Render* path (no delegated bake). Replicates the controller's
# Render.BakeSimulation recipe EXACTLY (free-before-bake, OpenVDB + cache_type='ALL' for fluid, memory for
# point caches, PACKED for Geometry-Nodes zones) so a locally-baked scene slices the same way on the farm.
# Bakes in place and saves the .blend (the meaning of "bake locally"; delegated is the no-touch path).


def _save_mainfile() -> None:
    bpy.ops.wm.save_mainfile()


def _local_fluid_domains(scene):
    """(object, domain_settings, is_liquid) for every Mantaflow fluid DOMAIN in the scene."""
    domains = []
    for obj in getattr(scene, "objects", []):
        for modifier in getattr(obj, "modifiers", []):
            if getattr(modifier, "type", "") == "FLUID" and getattr(modifier, "fluid_type", "") == "DOMAIN":
                domain = getattr(modifier, "domain_settings", None)
                if domain is not None:
                    domains.append((obj, domain, getattr(domain, "domain_type", "") == "LIQUID"))
    return domains


def _configure_fluid_domain(obj, domain, index: int, start_frame: int, end_frame: int) -> None:
    # Unique in-blend-dir cache per domain (avoids name collisions / escaping paths); OpenVDB density grid
    # + cache_type='ALL' so every frame is written; bake from the sim's natural start (a liquid mesh only
    # displays from a cache contiguous from the start) up to the render end.
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", obj.name)
    domain.cache_directory = "//cache_%d_%s" % (index, sanitized)
    domain.cache_data_format = "OPENVDB"
    domain.cache_type = "ALL"
    existing_start = int(getattr(domain, "cache_frame_start", 1) or 1)
    domain.cache_frame_start = max(1, min(existing_start, start_frame))
    domain.cache_frame_end = max(domain.cache_frame_start, end_frame)
    if hasattr(domain, "cache_noise_format"):
        try:
            domain.cache_noise_format = "OPENVDB"
        except Exception:
            pass


def _bake_fluid_domain(obj) -> None:
    # Free any stale/existing bake first — fluid.bake_all on an already-baked domain ships the OLD cache
    # (the same frozen-stale failure fixed for point caches); free_all forces a clean re-bake.
    with bpy.context.temp_override(active_object=obj, selected_objects=[obj], object=obj):
        try:
            bpy.ops.fluid.free_all()
        except Exception:
            pass
        bpy.ops.fluid.bake_all()


def _bake_point_caches() -> None:
    # Cloth / soft body / dynamic paint / particles / rigid body → bake to MEMORY (embedded in the .blend
    # on save → self-contained, no per-frame attachments). Free first so a stale/flagged cache re-bakes
    # instead of staying frozen.
    for obj in bpy.data.objects:
        for modifier in getattr(obj, "modifiers", []):
            point_cache = getattr(modifier, "point_cache", None)
            if point_cache is not None:
                try:
                    point_cache.use_disk_cache = False
                except Exception:
                    pass
    try:
        bpy.ops.ptcache.free_bake_all()
    except Exception:
        pass
    bpy.ops.ptcache.bake_all(bake=True)


def _geometry_nodes_bake_objects(scene):
    """Objects with a Geometry-Nodes simulation zone, configured to bake PACKED over the animation."""
    objects = []
    for obj in getattr(scene, "objects", []):
        for modifier in getattr(obj, "modifiers", []):
            if getattr(modifier, "type", "") == "NODES" and _has_geometry_nodes_simulation(modifier):
                try:
                    modifier.bake_target = "PACKED"
                    for bake in modifier.bakes:
                        bake.bake_mode = "ANIMATION"
                    if obj not in objects:
                        objects.append(obj)
                except Exception:
                    continue
    return objects


def _bake_geometry_nodes(obj) -> None:
    # Delete any existing GN bake first — simulation_nodes_cache_bake skips already-baked zones (ships the
    # stale PACKED bake), so a pre-baked scene would otherwise stay frozen.
    with bpy.context.temp_override(active_object=obj, selected_objects=[obj], object=obj):
        try:
            bpy.ops.object.simulation_nodes_cache_delete(selected=True)
        except Exception:
            pass
        bpy.ops.object.simulation_nodes_cache_bake(selected=True)


def _scene_has_point_cache_sim(scene) -> bool:
    from .bridge_simulation import SIM_CLOTH, SIM_DYNAMIC_PAINT, SIM_PARTICLES, SIM_RIGID_BODY, SIM_SOFT_BODY

    point_cache_kinds = {SIM_CLOTH, SIM_SOFT_BODY, SIM_DYNAMIC_PAINT, SIM_PARTICLES, SIM_RIGID_BODY}
    return any(kind in point_cache_kinds for kind in _scan_scene_simulations(scene).kinds)


def _local_bake_step_plan(scene, start_frame: int, end_frame: int):
    """Ordered (label, action) bake steps. The modal operator runs one per timer tick so the panel shows
    progress and Esc can cancel between steps (each individual bake is blocking)."""
    steps = []

    domains = _local_fluid_domains(scene)
    if domains:
        def _configure_all_domains():
            for index, (obj, domain, _is_liquid) in enumerate(domains):
                _configure_fluid_domain(obj, domain, index, start_frame, end_frame)
            _save_mainfile()

        steps.append(("Configuring fluid domains", _configure_all_domains))
        for obj, _domain, _is_liquid in domains:
            steps.append((f"Baking fluid: {obj.name}", (lambda captured=obj: _bake_fluid_domain(captured))))

    if _scene_has_point_cache_sim(scene):
        steps.append(("Baking point-cache simulations (cloth/particles/soft body/…)", _bake_point_caches))

    for obj in _geometry_nodes_bake_objects(scene):
        steps.append((f"Baking geometry nodes: {obj.name}", (lambda captured=obj: _bake_geometry_nodes(captured))))

    steps.append(("Saving baked scene", _save_mainfile))
    return steps


def _collect_local_fluid_cache_attachments(scene, client) -> list[dict[str, object]]:
    """Upload every baked fluid cache file and build its FluidCache attachment entry (frame-tagged exactly
    like the controller — gas density per-frame, liquid/noise/config whole). Point-cache + GN bakes are
    self-contained in the saved .blend and need no attachments."""
    from .bridge_local_bake import build_fluid_cache_attachment

    blend_dir = os.path.dirname(bpy.data.filepath or "")
    if not blend_dir:
        return []

    attachments: list[dict[str, object]] = []
    seen: set[str] = set()
    for _obj, domain, is_liquid in _local_fluid_domains(scene):
        cache_dir = str(getattr(domain, "cache_directory", "") or "")
        if cache_dir.startswith("//"):
            cache_dir = os.path.join(blend_dir, cache_dir[2:])
        cache_dir = bpy.path.abspath(cache_dir) if cache_dir else ""
        if not cache_dir or not os.path.isdir(cache_dir):
            continue

        for root, _dirs, files in os.walk(cache_dir):
            for filename in files:
                full = os.path.join(root, filename)
                rel = os.path.relpath(full, blend_dir).replace("\\", "/")
                if rel in seen:
                    continue
                seen.add(rel)
                response = client.upload_file(full)
                attachments.append(build_fluid_cache_attachment(rel, is_liquid, response.blob_id))

    return attachments


class OUTWIT_OT_bridge_bake_local(Operator):
    bl_idname = "outwit.bridge_bake_local"
    bl_label = "Bake Simulation Locally"
    bl_description = ("Bake this scene's simulations in Blender and save the .blend, so the baked scene "
                      "renders distributed without a farm bake")

    _timer = None
    _steps: list = []
    _index = 0
    _announced = -1

    def invoke(self, context, event):
        if not (bpy.data.filepath or ""):
            self.report({"ERROR"}, "Save the .blend before baking locally.")
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Bake the scene's simulations into this .blend?", icon="PHYSICS")
        layout.label(text="This replaces the current baked state and SAVES the file.")
        layout.label(text="(Choose 'On render farm' instead to bake without touching this file.)")

    def execute(self, context):
        state = _get_runtime_state(context)
        scene = context.scene

        self._steps = _local_bake_step_plan(scene, int(scene.frame_start), int(scene.frame_end))
        self._index = 0
        self._announced = -1
        state.local_bake_in_progress = True
        state.last_error = ""
        state.status_message = "Baking locally…"
        self._timer = context.window_manager.event_timer_add(0.15, window=context.window)
        context.window_manager.modal_handler_add(self)
        _tag_job_areas_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self._cancel(context, "Local bake cancelled.")

        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        state = _get_runtime_state(context)

        if self._index >= len(self._steps):
            return self._finish(context)

        label, action = self._steps[self._index]

        # Announce the step (and let the panel repaint) one tick BEFORE running the blocking bake.
        if self._announced != self._index:
            state.status_message = f"Baking… {label} ({self._index + 1}/{len(self._steps)})"
            self._announced = self._index
            _tag_job_areas_redraw()
            return {"RUNNING_MODAL"}

        try:
            action()
        except Exception as ex:
            state.last_error = str(ex)
            return self._cancel(context, f"Local bake failed: {ex}", level="ERROR")

        self._index += 1
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        state = _get_runtime_state(context)
        self._cleanup(context)

        fluid_attachments: list[dict[str, object]] = []
        try:
            client = _get_bridge_client(context)
            fluid_attachments = _collect_local_fluid_cache_attachments(context.scene, client)
        except Exception as ex:
            state.local_bake_in_progress = False
            state.last_error = str(ex)
            state.status_message = f"Baked, but collecting fluid caches failed: {ex}"
            self.report({"ERROR"}, state.status_message)
            _tag_job_areas_redraw()
            return {"CANCELLED"}

        state.local_bake_fluid_manifest_json = json.dumps(fluid_attachments, ensure_ascii=False)
        state.local_bake_in_progress = False
        _refresh_bridge_state(context)  # re-scan: the simulation now reads as baked
        state.status_message = (f"Local bake complete ({len(fluid_attachments)} fluid cache file(s) collected)."
                                if fluid_attachments else "Local bake complete.")
        self.report({"INFO"}, state.status_message)
        _tag_job_areas_redraw()
        return {"FINISHED"}

    def _cancel(self, context, message: str, level: str = "WARNING"):
        state = _get_runtime_state(context)
        self._cleanup(context)
        state.local_bake_in_progress = False
        state.status_message = message
        self.report({level}, message)
        _tag_job_areas_redraw()
        return {"CANCELLED"}

    def _cleanup(self, context) -> None:
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


# endregion


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
    simulation_summary = _scan_scene_simulations(scene)
    state.scene_has_simulation = simulation_summary.has_simulation
    state.scene_simulation_summary = simulation_summary.summary_text()
    state.scene_unbaked_simulation_summary = simulation_summary.unbaked_summary_text()
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
    state.groups_json = (
        json.dumps([{"id": group.group_id, "name": group.name} for group in scope_options.groups])
        if scope_options else ""
    )
    # Default the target: with all-nodes permission but NO groups, "Run on all nodes" is the only valid
    # choice → pre-check it. When groups exist, leave the choice alone (the Target dropdown defaults to
    # a group); never auto-clobber a user who has groups and deliberately picked all-nodes. Programmatic
    # write → must not queue a preference push.
    if state.can_run_on_all_clients and state.group_count == 0 and not state.run_on_all_nodes:
        global _suppress_settings_marking
        _suppress_settings_marking = True
        try:
            state.run_on_all_nodes = True
        finally:
            _suppress_settings_marking = False
    if scope_options is not None:
        _seed_remembered_target(context, client)
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

        # An explicit Connect clears the lazy-start failure latch so the heartbeat timer resumes
        # auto-managing the bridge after this manual attempt.
        rearm_lazy_first_start()
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
                {"ERROR" if _validation_is_blocked(state) else "INFO"},
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
            bake_plan = _launch_bake_plan(state)
            bake = bake_plan.should_delegate or bake_plan.should_local
            other_issue = get_non_simulation_validation_issue(state.validate_issue_summary)

            # A simulation covered by a bake plan is NOT preflighted on the unbaked scene — it is baked
            # first and the BAKED scene is validated at render time. Report informationally and leave the
            # per-mode verdicts unset (Not checked), as long as nothing else blocks.
            if not validation_response.is_valid and bake and not other_issue and not portability_issue:
                _reset_preflight_state(state)
                where = "the render farm" if bake_plan.should_delegate else "this computer"
                message = f"Simulation will be baked on {where}; preflight runs on the baked scene at render time."
                state.preflight_message = message
                state.status_message = message
                self.report({"INFO"}, message)
                return {"FINISHED"}

            if not validation_response.is_valid:
                state.preflight_status = validation_response.status
                blocking_issue = bake_plan.block or other_issue or simulation_issue \
                    or validation_response.message or _validation_policy_message(state)
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


class OUTWIT_OT_bridge_use_recommended_mode(Operator):
    bl_idname = "outwit.bridge_use_recommended_mode"
    bl_label = "Use Recommended Mode"
    bl_description = "Switch the render mode to the one that matches the scene's output settings"

    @classmethod
    def description(cls, context, properties):
        # Dynamic tooltip: the hint label above may wrap/truncate — hovering the button shows the
        # full recommendation.
        try:
            recommended = recommended_render_mode(context.scene)
            return f"Switch the output selection to the recommended mode: {recommended}"
        except Exception:
            return cls.bl_description

    def execute(self, context):
        state = _get_runtime_state(context)
        state.render_mode = recommended_render_mode(context.scene)
        apply_render_mode_to_axes(state)
        self.report({"INFO"}, f"Render mode set to {state.render_mode}.")
        return {"FINISHED"}


# Above this many frames, a Frames/Video launch asks for confirmation (a wide default .blend range can
# otherwise kick off thousands of frames across the crowd by accident).
# Picking Video/Frames already implies "many frames" — the dialog is NOT for normal animations
# (a 200-frame shot was getting nagged at the old threshold of 50). It exists for one accident:
# an untouched default range (e.g. 1-10000) silently burning the crowd's compute. Cancel exists,
# but a cancelled batch still costs other people's machines real work.
_LARGE_FRAME_CONFIRM_THRESHOLD = 500


class OUTWIT_OT_bridge_launch_render(Operator):
    bl_idname = "outwit.bridge_launch_render"
    bl_label = "Launch Render"
    bl_description = "Launch the selected render mode through the local bridge"

    _task = None
    _timer = None
    _blend_path = ""
    _output_signature = ""
    _pending_frame_count = 0
    _pending_tail = False

    def invoke(self, context, event):
        state = _get_runtime_state(context)
        if state.render_mode in {"Frames", "Video"}:
            count = scene_frame_count(context.scene)
            if count > _LARGE_FRAME_CONFIRM_THRESHOLD:
                self._pending_frame_count = count
                return context.window_manager.invoke_props_dialog(self, width=340)
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.label(text=f"This will render {self._pending_frame_count} frames on the cloud.", icon="ERROR")
        layout.label(text="That can take a long time and a lot of compute.")
        layout.label(text="Continue?")

    def execute(self, context):
        global _launch_in_progress
        state = _get_runtime_state(context)

        if _launch_in_progress:
            self.report({"WARNING"}, "A launch is already in progress.")
            return {"CANCELLED"}

        # Main-thread: validate the scene is saved and gather all bpy-derived data up front, so the
        # worker thread only does network/subprocess work (Blender's API is not thread-safe).
        try:
            self._blend_path = _get_current_blend_path()
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = str(ex)
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        self._output_signature = scene_output_signature(context.scene)
        if not _scene_requires_upload(state, self._blend_path, self._output_signature):
            # Scene already uploaded — run the fast tail (validate -> preflight -> submit), but
            # DEFERRED by one modal tick: the tail's cloud round-trips block the UI thread for a
            # second or two, and running them inside execute() froze the panel with zero feedback
            # ("did my click do anything?"). One tick lets Blender repaint the status line first.
            state.current_blend_path = self._blend_path
            return self._begin_deferred_tail(context, ensure_modal=True)

        try:
            planned_attachments = collect_scene_attachment_metadata()
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = "Failed to collect scene attachments."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        _apply_dependency_plan(state, planned_attachments)
        context_directory = _get_context_directory(context)

        _launch_in_progress = True
        state.launch_in_progress = True
        state.last_error = ""
        state.status_message = "Uploading scene..."
        self._task = AsyncCall(
            lambda: _upload_worker(context_directory, self._blend_path, planned_attachments)
        ).start()
        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        _tag_job_areas_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        global _launch_in_progress
        state = _get_runtime_state(context)

        # The deferred fast tail: queued by _begin_deferred_tail so Blender repaints the status
        # line before the blocking cloud round-trips run.
        if self._pending_tail:
            self._pending_tail = False
            self._cleanup(context)
            return self._finish_launch(context)

        if self._task is None or not self._task.done:
            return {"PASS_THROUGH"}

        task = self._task
        self._task = None  # consumed; the timer stays alive for the deferred-tail tick

        if task.error is not None:
            self._cleanup(context)
            _launch_in_progress = False
            state.launch_in_progress = False
            message = str(task.error)
            state.last_error = message
            state.status_message = f"Upload failed: {message}"
            self.report({"ERROR"}, message)
            _tag_job_areas_redraw()
            return {"CANCELLED"}

        try:
            _apply_upload_result(state, self._blend_path, self._output_signature, task.result)
        except Exception as ex:
            self._cleanup(context)
            _launch_in_progress = False
            state.launch_in_progress = False
            state.last_error = str(ex)
            state.status_message = "Upload post-processing failed."
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        # Repaint between "upload finished" and the blocking tail, for the same reason as above.
        return self._begin_deferred_tail(context, ensure_modal=False)

    def _begin_deferred_tail(self, context, ensure_modal):
        """Queue the fast tail for the NEXT modal tick. ensure_modal=True when called from
        execute() (no timer/handler yet); False when already inside our modal loop."""
        global _launch_in_progress
        _launch_in_progress = True
        state = _get_runtime_state(context)
        state.launch_in_progress = True
        state.last_error = ""
        state.status_message = "Validating & submitting..."
        self._pending_tail = True
        if ensure_modal:
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
            context.window_manager.modal_handler_add(self)
        _tag_job_areas_redraw()
        return {"RUNNING_MODAL"}

    def _cleanup(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        self._task = None

    def _finish_launch(self, context):
        # Fast tail on the main thread: validate -> preflight -> submit (small, quick calls). The slow
        # upload already ran off-thread, so the UI is not frozen on it.
        global _launch_in_progress
        state = _get_runtime_state(context)
        try:
            validation_response = _run_validate_blend(context)

            # A missing external dependency is never fixed by a bake — block first, unconditionally.
            portability_issue = get_dependency_portability_blocking_issue(state.validate_warning_summary)
            if portability_issue:
                raise BridgeClientError(portability_issue)

            # Decide how an unbaked simulation is handled. The validator flags one as a hard block; the
            # artist's bake strategy may resolve it (delegated bake) — but never silently: a strategy
            # that cannot bake (LOCAL before its driver ships) keeps the block.
            bake_plan = _launch_bake_plan(state)
            if bake_plan.block:
                raise BridgeClientError(bake_plan.block)

            bake = bake_plan.should_delegate or bake_plan.should_local

            if not validation_response.is_valid:
                # The ONLY validation failure a bake may bypass is the simulation-cache block, and only
                # when a bake plan covers it. Any other hard issue still blocks.
                other_issue = get_non_simulation_validation_issue(state.validate_issue_summary)
                if other_issue or not bake:
                    raise BridgeClientError(
                        other_issue
                        or validation_response.message
                        or _validation_policy_message(state)
                        or state.validate_issue_summary
                        or "Blend validation reported blocking issues."
                    )

            if bake:
                # Bake path: the BakeAndRender* script bakes the simulation on the delegated node, then
                # validates and renders the BAKED scene. The plain-scene preflight is skipped by design
                # — it would re-flag the very simulation we are about to bake.
                response = _run_selected_launch(context, bake=True)
            else:
                _run_preflight(context)
                if not _selected_mode_is_ready(state):
                    raise BridgeClientError(_selected_mode_policy_message(state))
                response = _run_selected_launch(context)

            _sticky_render_settings_after_submit(context)
            state.status_message = _selected_mode_launched_message(state)
            self.report({"INFO"}, response.message or response.status or "Render launched.")
            _tag_job_areas_redraw()
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
        finally:
            _launch_in_progress = False
            state.launch_in_progress = False


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


def invalidate_preflight_results() -> None:
    """Clears the STORED preflight verdicts (called from bridge_state prop update callbacks via
    late import). Verdicts are valid only for the inputs they were computed with — a stale
    'Blocked' would otherwise gate Render with no way to recompute, because only a launch re-runs
    the checks and the gate prevents launching."""
    context = getattr(bpy, "context", None)
    state = getattr(getattr(context, "window_manager", None), "outwit_bridge_state", None)
    if state is None:
        return
    _reset_preflight_state(state)


def _reset_preflight_state(state) -> None:
    state.preflight_status = ""
    state.preflight_message = ""
    state.preflight_can_render_all = False
    state.preflight_still_ready = False
    state.preflight_frames_ready = False
    state.preflight_still_tiled_ready = False
    state.preflight_video_ready = False
    for field in (
        "preflight_still_issue_summary", "preflight_still_warning_summary",
        "preflight_frames_issue_summary", "preflight_frames_warning_summary",
        "preflight_still_tiled_issue_summary", "preflight_still_tiled_warning_summary",
        "preflight_video_issue_summary", "preflight_video_warning_summary",
        "preflight_issue_summary", "preflight_warning_summary",
    ):
        setattr(state, field, "")


class OUTWIT_OT_bridge_cancel_job(Operator):
    bl_idname = "outwit.bridge_cancel_job"
    bl_label = "Cancel"
    bl_description = "Request cancellation of the running cloud job"

    def execute(self, context):
        state = _get_runtime_state(context)
        if not state.active_job_id:
            self.report({"WARNING"}, "No active job to cancel.")
            return {"CANCELLED"}

        try:
            client = _get_bridge_client(context)
            client.cancel_job(state.active_job_id)
        except Exception as ex:
            state.last_error = str(ex)
            state.status_message = f"Cancel failed: {ex}"
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}

        # Optimistic transitional state: cancel is asynchronous (server signals nodes, the current task
        # still finishes). compute_status reads this to show the Cancelling phase until the server reports
        # a terminal status; the background monitor then observes Cancelled, snaps the bar and stops.
        state.active_job_cancel_requested = True
        state.status_message = "Cancellation requested."
        self.report({"INFO"}, "Cancellation requested.")
        _tag_job_areas_redraw()
        return {"FINISHED"}


class OUTWIT_OT_bridge_reset_job(Operator):
    bl_idname = "outwit.bridge_reset_job"
    bl_label = "Reset"
    bl_description = "Clear the current job, preflight result and last error to start over (keeps the uploaded scene)"

    def execute(self, context):
        state = _get_runtime_state(context)
        _stop_job_monitor()

        state.auto_refresh_active_job = False
        state.active_job_id = ""
        state.active_job_script_name = ""
        state.active_job_status = ""
        state.active_job_progress = ""
        state.active_job_progress_factor = 0.0
        state.active_job_distributed_progress = ""
        state.active_job_distributed_progress_factor = 0.0
        state.active_job_error = ""
        state.active_job_result_blob_id = ""
        state.active_job_result_blob_count = 0
        state.active_job_is_completed = False
        state.active_job_cancel_requested = False

        state.download_status = ""
        state.download_message = ""
        state.download_primary_path = ""
        state.download_primary_file_name = ""
        state.download_item_count = 0

        _reset_preflight_state(state)
        state.last_error = ""
        state.status_message = "Ready."
        _tag_job_areas_redraw()
        self.report({"INFO"}, "Reset. Ready to render again.")
        return {"FINISHED"}


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


class OUTWIT_OT_bridge_switch_format_to_png(Operator):
    bl_idname = "outwit.bridge_switch_format_to_png"
    bl_label = "Switch to PNG"
    bl_description = "Set the scene's output format (Output Properties > File Format) to PNG"
    # UNDO pushes an undo step on success — that is also what flags the file as modified, so the
    # Save-scene button appears after the fix is applied.
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        render = getattr(context.scene, "render", None)
        image_settings = getattr(render, "image_settings", None)
        if image_settings is None:
            self.report({"ERROR"}, "No render image settings are available on this scene.")
            return {"CANCELLED"}

        image_settings.file_format = "PNG"
        # The format is a preflight input — drop verdicts computed for the old format.
        invalidate_preflight_results()
        self.report({"INFO"}, "Output format set to PNG.")
        return {"FINISHED"}


class OUTWIT_OT_bridge_copy_text(Operator):
    bl_idname = "outwit.bridge_copy_text"
    bl_label = "Copy"
    bl_description = "Copy the full message to the clipboard"

    text: StringProperty(default="", options={"SKIP_SAVE"})

    def execute(self, context):
        context.window_manager.clipboard = self.text or ""
        self.report({"INFO"}, "Message copied to clipboard.")
        return {"FINISHED"}


CLASSES = (
    OUTWIT_OT_bridge_refresh_status,
    OUTWIT_OT_bridge_start,
    OUTWIT_OT_bridge_stop,
    OUTWIT_OT_bridge_sign_in,
    OUTWIT_OT_bridge_sign_out,
    OUTWIT_OT_bridge_upload_blend,
    OUTWIT_OT_bridge_validate_blend,
    OUTWIT_OT_bridge_run_preflight,
    OUTWIT_OT_bridge_use_recommended_mode,
    OUTWIT_OT_bridge_bake_local,
    OUTWIT_OT_bridge_launch_render,
    OUTWIT_OT_bridge_refresh_job,
    OUTWIT_OT_bridge_cancel_job,
    OUTWIT_OT_bridge_reset_job,
    OUTWIT_OT_bridge_download_result,
    OUTWIT_OT_bridge_open_result,
    OUTWIT_OT_bridge_open_result_folder,
    OUTWIT_OT_bridge_load_result_image,
    OUTWIT_OT_bridge_switch_format_to_png,
    OUTWIT_OT_bridge_copy_text,
)
