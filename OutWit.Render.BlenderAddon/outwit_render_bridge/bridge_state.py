from __future__ import annotations

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup, WindowManager

from .bridge_status import axes_for_render_mode, render_mode_for_axes


# Sentinel enum identifier for the "any available client" target (no specific group). Kept for
# back-compat in the group-id resolver; "all nodes" is now a separate checkbox (run_on_all_nodes),
# not an entry in the Target dropdown.
ALL_CLIENTS_GROUP_ID = "__ALL__"

# Placeholder identifier when the user has no authorized groups — keeps the EnumProperty non-empty
# (Blender requires >= 1 item) while the control is hidden/disabled.
NO_GROUP_ID = "__NONE__"

# Blender keeps only weak references to the strings returned by a dynamic EnumProperty
# items callback; if we build them inline they get garbage-collected and the UI shows
# corrupted entries (or crashes). Hold a module-level reference to the last built list.
_GROUP_ENUM_ITEMS_CACHE: list[tuple[str, str, str]] = []


def selected_group_items(self, context):
    """Builds the Target dropdown: the authorized GROUPS only.

    'All clients / all nodes' is NOT an entry here — it is a separate checkbox (run_on_all_nodes),
    so Target always means "a specific group". Reads the groups the bridge reported for the signed-in
    user (serialized into ``groups_json``). A placeholder keeps the enum non-empty when the user has
    no groups (the control is hidden/disabled in that case).
    """
    items: list[tuple[str, str, str]] = []

    try:
        groups = json.loads(self.groups_json) if self.groups_json else []
    except (ValueError, TypeError):
        groups = []

    for group in groups:
        group_id = str(group.get("id", "")).strip()
        if not group_id:
            continue
        name = str(group.get("name", "")).strip() or group_id
        items.append((group_id, name, f"Render on group '{name}'"))

    if not items:
        items.append((NO_GROUP_ID, "No groups", "You have no authorized render groups"))

    _GROUP_ENUM_ITEMS_CACHE.clear()
    _GROUP_ENUM_ITEMS_CACHE.extend(items)
    return _GROUP_ENUM_ITEMS_CACHE


# The artist-facing output is a 2-axis model (Output: Image|Animation, with a split toggle / a
# Sequence|Video sub-axis). It maps 1:1 onto the four internal render_mode paths that the operators and
# the controller already understand, so render_mode stays the single value everything reads — these axes
# just derive it. Map: Image+split off = Still, Image+split on = StillTiled, Animation+Sequence = Frames,
# Animation+Video = Video.
def _sync_render_mode(self, context) -> None:
    self.render_mode = render_mode_for_axes(self.output_axis, self.split_frame, self.anim_result)


def _mark_render_settings_changed(self, context) -> None:
    """A bucket-1 preference changed in the UI → queue a persist to the bridge store. Late import
    (the pending flag and the push live in bridge_operators; importing it at module top would be a
    cycle). The heartbeat pump performs the actual REST write off the next tick, so a prop update
    callback never blocks the UI on I/O."""
    try:
        from . import bridge_operators

        bridge_operators.mark_render_settings_changed()
    except Exception:
        pass


def _invalidate_preflight(self, context) -> None:
    """Stored preflight verdicts are computed FOR specific inputs (mode, format, tiles, frame,
    video options) — any input change makes them stale. A stale 'Blocked' verdict otherwise keeps
    the Render gate shut with no way to recompute: only a launch re-runs the checks, and the gate
    prevents launching (live finding 2026-06-12: tiled+WebP block survived switching back to PNG).
    Design rule: never keep verdicts whose inputs changed."""
    try:
        from . import bridge_operators

        bridge_operators.invalidate_preflight_results()
    except Exception:
        pass


def _sync_render_mode_and_persist(self, context) -> None:
    _sync_render_mode(self, context)
    _mark_render_settings_changed(self, context)
    _invalidate_preflight(self, context)


def _mark_render_settings_changed_and_invalidate(self, context) -> None:
    _mark_render_settings_changed(self, context)
    _invalidate_preflight(self, context)


def _mark_scene_modified_and_invalidate(self, context) -> None:
    _mark_scene_modified(self, context)
    _invalidate_preflight(self, context)


def apply_render_mode_to_axes(state) -> None:
    """Reverse sync: reflect a render_mode set elsewhere (recommended-mode operator, .blend load) back
    into the Output axes so the segmented controls match. Setting the axes re-derives the same
    render_mode via _sync_render_mode (stable — no loop). Only the sub-control implied by the axis is
    written, so switching axes does not clobber the other sub-control's last value."""
    output_axis, split_frame, anim_result = axes_for_render_mode(state.render_mode)
    state.output_axis = output_axis
    if output_axis == "Image":
        state.split_frame = split_frame
    else:
        state.anim_result = anim_result


# Output format is a CURATED list — only the formats the render controller actually honours (PNG /
# OpenEXR / JPEG). Blender's native file_format enum lists ~15 formats; offering the unsupported ones
# led to "picked TIFF, got PNG" (a silent fallback). This control is bound to the scene's Output
# Properties via get/set, so the scene stays the single source of truth (the .blend records it, the
# render reads it live) — we just constrain the choice to what works.
_OUTPUT_FORMAT_ITEMS = [
    ("PNG", "PNG", "Lossless 8/16-bit image"),
    ("OPEN_EXR", "OpenEXR", "High-dynamic-range / linear float"),
    ("JPEG", "JPEG", "Compressed 8-bit image"),
    ("TIFF", "TIFF", "Lossless 8/16-bit image (print/archviz pipelines)"),
    ("WEBP", "WebP", "Modern web image (lossy or lossless)"),
]
# Map a scene file_format string to the curated control's index (EXR multilayer collapses to EXR).
_OUTPUT_FORMAT_TO_INDEX = {"PNG": 0, "OPEN_EXR": 1, "OPEN_EXR_MULTILAYER": 1, "JPEG": 2, "TIFF": 3, "WEBP": 4}

# Index of the transient "unsupported" display entry (see _output_format_items).
_OUTPUT_FORMAT_UNSUPPORTED_INDEX = len(_OUTPUT_FORMAT_ITEMS)

# Dynamic-enum GC guard: Blender keeps weak references to item strings (same issue as the group
# dropdown) — hold the last built list at module level.
_OUTPUT_FORMAT_ITEMS_CACHE: list[tuple] = []


def _scene_image_settings():
    scene = getattr(bpy.context, "scene", None)
    render = getattr(scene, "render", None)
    return getattr(render, "image_settings", None)


def _scene_file_format() -> str:
    image_settings = _scene_image_settings()
    return (getattr(image_settings, "file_format", "") or "") if image_settings is not None else ""


def _output_format_items(self, context):
    """The curated list, PLUS a transient read-only entry showing the scene's REAL format when it is
    unsupported. Displaying 'PNG' for a TIFF scene (the old index-0 fallback) made the SWITCH_FORMAT
    blocker look like a false alarm — and clicking 'PNG' was a no-op because the displayed value
    didn't change, so the setter never fired. Now the control tells the truth and any pick works."""
    items = [(identifier, label, description, "", index)
             for index, (identifier, label, description) in enumerate(_OUTPUT_FORMAT_ITEMS)]

    fmt = _scene_file_format()
    if fmt and fmt not in _OUTPUT_FORMAT_TO_INDEX:
        items.append(("UNSUPPORTED", f"{fmt} (not supported)",
                      "The scene's current output format — the farm cannot render it; pick one of the "
                      "supported formats", "ERROR", _OUTPUT_FORMAT_UNSUPPORTED_INDEX))

    _OUTPUT_FORMAT_ITEMS_CACHE.clear()
    _OUTPUT_FORMAT_ITEMS_CACHE.extend(items)
    return _OUTPUT_FORMAT_ITEMS_CACHE


def _mark_scene_modified(self, context) -> None:
    """Our Format/Frame controls are TRANSIT props on the WindowManager whose set-callbacks write
    into the scene FROM PYTHON — and Python writes do not push an undo step, so Blender never
    flags the file as modified (`bpy.data.is_dirty` stays False) and the Save-scene button never
    appeared. Push one undo step to raise the flag; skip when already dirty so dragging a slider
    does not spam the undo stack."""
    if bool(getattr(bpy.data, "is_dirty", False)):
        return
    try:
        bpy.ops.ed.undo_push(message="OmnibusCloud render setting")
    except Exception:
        pass


# The still Frame is bucket 2 ("derive from the scene, don't store"): it binds to the scene's
# current frame, so it persists in the .blend and survives restarts with the file — an unbound
# IntProperty reset to 1 every session and read as "my Frame is not saved".
def _still_frame_get(self) -> int:
    scene = getattr(bpy.context, "scene", None)
    if scene is None:
        return 1
    return max(1, int(getattr(scene, "frame_current", 1) or 1))


def _still_frame_set(self, value: int) -> None:
    scene = getattr(bpy.context, "scene", None)
    if scene is not None:
        scene.frame_current = max(1, int(value))


# Video FPS is bucket 2 ("derive from the scene"): it binds to scene.render.fps, so it persists
# in the .blend — an unbound IntProperty reset to 24 every session was the same class of bug as
# the unbound still Frame.
def _video_fps_get(self) -> int:
    scene = getattr(bpy.context, "scene", None)
    render = getattr(scene, "render", None)
    return max(1, int(getattr(render, "fps", 24) or 24)) if render is not None else 24


def _video_fps_set(self, value: int) -> None:
    scene = getattr(bpy.context, "scene", None)
    render = getattr(scene, "render", None)
    if render is not None:
        render.fps = max(1, int(value))


def _output_format_get(self) -> int:
    fmt = _scene_file_format()
    if not fmt:
        # No scene/render context (headless, early draw) — the transient entry is absent then.
        return 0
    return _OUTPUT_FORMAT_TO_INDEX.get(fmt, _OUTPUT_FORMAT_UNSUPPORTED_INDEX)


def _output_format_set(self, value: int) -> None:
    image_settings = _scene_image_settings()
    if image_settings is not None and 0 <= value < len(_OUTPUT_FORMAT_ITEMS):
        image_settings.file_format = _OUTPUT_FORMAT_ITEMS[value][0]


class OutWitBridgeRuntimeState(PropertyGroup):
    bridge_version: StringProperty(name="Bridge Version", default="")
    bridge_url: StringProperty(name="Bridge Url", default="")
    context_path: StringProperty(name="Context Path", default="")
    bridge_process_id: IntProperty(name="Bridge Process Id", default=0)
    bridge_is_running: BoolProperty(name="Bridge Is Running", default=False)
    bridge_started_by_addon: BoolProperty(name="Bridge Started By Addon", default=False)
    bridge_session_directory: StringProperty(name="Bridge Session Directory", default="")
    bridge_executable_path: StringProperty(name="Bridge Executable Path", default="")
    bridge_launch_message: StringProperty(name="Bridge Launch Message", default="")
    bridge_lease_id: StringProperty(name="Bridge Lease Id", default="")
    bridge_lease_acquired: BoolProperty(name="Bridge Lease Acquired", default=False)
    bridge_heartbeat_interval_seconds: IntProperty(name="Bridge Heartbeat Interval Seconds", default=5, min=1)
    bridge_lease_timeout_seconds: IntProperty(name="Bridge Lease Timeout Seconds", default=30, min=1)
    is_secret_required: BoolProperty(name="Secret Required", default=False)
    is_signed_in: BoolProperty(name="Signed In", default=False)
    is_connected_to_cloud: BoolProperty(name="Connected To Cloud", default=False)
    can_launch: BoolProperty(name="Can Launch", default=False)
    can_run_on_all_clients: BoolProperty(name="Can Run On All Clients", default=False)
    group_count: IntProperty(name="Group Count", default=0)
    project_count: IntProperty(name="Project Count", default=0)
    groups_json: StringProperty(name="Groups Json", default="")
    selected_client_group: EnumProperty(
        name="Target",
        description="Which group of nodes to render on",
        items=selected_group_items,
        update=_mark_render_settings_changed,
    )
    run_on_all_nodes: BoolProperty(
        name="Run on all nodes",
        description="Render on any available node instead of a specific group "
                    "(only offered when your account is allowed to)",
        default=False,
        update=_mark_render_settings_changed,
    )
    output_format: EnumProperty(
        name="Format",
        description="Output image format — only the formats the render farm supports. Writes to the "
                    "scene's Output Properties (File Format)",
        items=_output_format_items,
        get=_output_format_get,
        set=_output_format_set,
        update=_mark_scene_modified_and_invalidate,
    )
    current_user_display_name: StringProperty(name="Display Name", default="")
    current_user_id: StringProperty(name="User Id", default="")
    last_error: StringProperty(name="Last Error", default="")
    status_message: StringProperty(name="Status Message", default="Not connected.")
    current_blend_path: StringProperty(name="Current Blend Path", default="")
    current_blend_file_exists: BoolProperty(name="Current Blend File Exists", default=False)
    current_blend_is_dirty: BoolProperty(name="Current Blend Is Dirty", default=False)
    uploaded_blob_id: StringProperty(name="Uploaded Blob Id", default="")
    uploaded_source_path: StringProperty(name="Uploaded Source Path", default="")
    uploaded_output_signature: StringProperty(name="Uploaded Output Signature", default="")
    # Source .blend mtime at upload time — re-saving the scene (camera added, sim re-baked, …) busts
    # the upload cache even when path + output settings are unchanged.
    uploaded_source_mtime: StringProperty(name="Uploaded Source Mtime", default="")
    uploaded_file_name: StringProperty(name="Uploaded File Name", default="")
    uploaded_file_size: IntProperty(name="Uploaded File Size", default=0)
    # Local-bake ("On this computer") transient state: whether a modal bake is running, and the JSON
    # manifest of fluid-cache attachments collected from the locally-baked scene (already uploaded, so
    # the launch merges them into the upload manifest without re-uploading).
    local_bake_in_progress: BoolProperty(name="Local Bake In Progress", default=False)
    local_bake_fluid_manifest_json: StringProperty(name="Local Bake Fluid Manifest Json", default="")
    uploaded_attachment_manifest_json: StringProperty(name="Uploaded Attachment Manifest Json", default="")
    upload_message: StringProperty(name="Upload Message", default="")
    dependency_plan_total_count: IntProperty(name="Dependency Plan Total Count", default=0)
    dependency_plan_count_summary: StringProperty(name="Dependency Plan Count Summary", default="")
    dependency_plan_packed_count: IntProperty(name="Dependency Plan Packed Count", default=0)
    dependency_plan_packed_summary: StringProperty(name="Dependency Plan Packed Summary", default="")
    dependency_plan_attachment_count: IntProperty(name="Dependency Plan Attachment Count", default=0)
    dependency_plan_attachment_summary: StringProperty(name="Dependency Plan Attachment Summary", default="")
    scene_frame_current: IntProperty(name="Scene Frame Current", default=0)
    scene_frame_start: IntProperty(name="Scene Frame Start", default=0)
    scene_frame_end: IntProperty(name="Scene Frame End", default=0)
    scene_camera_name: StringProperty(name="Scene Camera Name", default="")
    scene_render_engine: StringProperty(name="Scene Render Engine", default="")
    scene_engine_family: StringProperty(name="Scene Engine Family", default="")
    scene_use_nodes: BoolProperty(name="Scene Use Nodes", default=False)
    # Bakeable-simulation analysis (filled by the scene scan in bridge_operators). Transient, like the
    # other scene_* props — drives the bake-strategy UI and the launch gate.
    scene_has_simulation: BoolProperty(name="Scene Has Simulation", default=False)
    scene_simulation_summary: StringProperty(name="Scene Simulation Summary", default="")
    scene_unbaked_simulation_summary: StringProperty(name="Scene Unbaked Simulation Summary", default="")
    render_film_transparent: BoolProperty(name="Render Film Transparent", default=False)
    render_file_format: StringProperty(name="Render File Format", default="")
    render_color_mode: StringProperty(name="Render Color Mode", default="")
    render_alpha_mode: StringProperty(name="Render Alpha Mode", default="")
    validate_job_id: StringProperty(name="Validate Job Id", default="")
    validate_status: StringProperty(name="Validate Status", default="")
    validate_message: StringProperty(name="Validate Message", default="")
    validate_is_valid: BoolProperty(name="Validate Is Valid", default=False)
    validate_issue_summary: StringProperty(name="Validate Issue Summary", default="")
    validate_warning_summary: StringProperty(name="Validate Warning Summary", default="")
    preflight_status: StringProperty(name="Preflight Status", default="")
    preflight_message: StringProperty(name="Preflight Message", default="")
    preflight_can_render_all: BoolProperty(name="Preflight Can Render All", default=False)
    preflight_still_ready: BoolProperty(name="Preflight Still Ready", default=False)
    preflight_frames_ready: BoolProperty(name="Preflight Frames Ready", default=False)
    preflight_still_tiled_ready: BoolProperty(name="Preflight Still Tiled Ready", default=False)
    preflight_video_ready: BoolProperty(name="Preflight Video Ready", default=False)
    preflight_still_issue_summary: StringProperty(name="Preflight Still Issue Summary", default="")
    preflight_still_warning_summary: StringProperty(name="Preflight Still Warning Summary", default="")
    preflight_frames_issue_summary: StringProperty(name="Preflight Frames Issue Summary", default="")
    preflight_frames_warning_summary: StringProperty(name="Preflight Frames Warning Summary", default="")
    preflight_still_tiled_issue_summary: StringProperty(name="Preflight Still Tiled Issue Summary", default="")
    preflight_still_tiled_warning_summary: StringProperty(name="Preflight Still Tiled Warning Summary", default="")
    preflight_video_issue_summary: StringProperty(name="Preflight Video Issue Summary", default="")
    preflight_video_warning_summary: StringProperty(name="Preflight Video Warning Summary", default="")
    preflight_issue_summary: StringProperty(name="Preflight Issue Summary", default="")
    preflight_warning_summary: StringProperty(name="Preflight Warning Summary", default="")
    still_frame: IntProperty(
        name="Still Frame",
        description="The frame to render — the scene's current frame (stored in the .blend)",
        default=1,
        min=1,
        get=_still_frame_get,
        set=_still_frame_set,
        update=_mark_scene_modified_and_invalidate,
    )
    tiles_x: IntProperty(name="Tiles X", default=2, min=1, update=_mark_render_settings_changed_and_invalidate)
    tiles_y: IntProperty(name="Tiles Y", default=2, min=1, update=_mark_render_settings_changed_and_invalidate)
    tile_overlap_px: IntProperty(name="Tile Overlap Px", default=8, min=0, update=_mark_render_settings_changed_and_invalidate)
    video_frame_rate: IntProperty(
        name="Video Frame Rate",
        description="Output frame rate — the scene's FPS (stored in the .blend)",
        default=24,
        min=1,
        get=_video_fps_get,
        set=_video_fps_set,
        update=_mark_scene_modified_and_invalidate,
    )
    video_constant_rate_factor: IntProperty(
        name="Video Constant Rate Factor",
        default=23,
        min=0,
        max=51,
        update=_mark_render_settings_changed_and_invalidate,
    )
    # Container+codec PRESET (one control instead of two axes — invalid combos unrepresentable).
    # Bucket 1: persisted on the bridge as the VideoContainer/VideoCodec pair.
    video_format: EnumProperty(
        name="Video format",
        description="Container and codec for the encoded video",
        items=[
            ("MP4_H264", "MP4 · H.264", "Universal playback (the default)"),
            ("MP4_H265", "MP4 · H.265", "Same quality at roughly half the size; needs newer players"),
            ("WEBM_VP9", "WebM · VP9", "Open web format"),
            ("MOV_PRORES_422HQ", "MOV · ProRes 422 HQ",
             "Editing/grading intermediate (fixed quality — CRF does not apply)"),
            ("MOV_PRORES_4444", "MOV · ProRes 4444",
             "Keeps the alpha channel for transparent video (fixed quality — CRF does not apply)"),
        ],
        default="MP4_H264",
        update=_mark_render_settings_changed_and_invalidate,
    )
    render_mode: EnumProperty(
        name="Render Mode",
        items=[
            ("Still", "Still", "Run RenderStill for the selected still frame"),
            ("StillTiled", "Tiled Still", "Run RenderStillTiled for the selected still frame"),
            ("Frames", "Frames", "Run RenderFrames for the current frame range"),
            ("Video", "Video", "Run RenderVideo for the current frame range"),
        ],
        default="Still",
    )
    # 2-axis artist-facing output (derives render_mode above via _sync_render_mode).
    output_axis: EnumProperty(
        name="Output",
        description="What to render: a single image, or an animation over the frame range",
        items=[
            ("Image", "Image", "Render a single frame"),
            ("Animation", "Animation", "Render the scene's frame range"),
        ],
        default="Image",
        update=_sync_render_mode,
    )
    split_frame: BoolProperty(
        name="Split frame across machines",
        description="Tile the frame and render the tiles across multiple machines (heavy single frames)",
        default=False,
        update=_sync_render_mode_and_persist,
    )
    anim_result: EnumProperty(
        name="Result",
        description="Deliver the animation as an image sequence, or a single encoded video",
        items=[
            ("Sequence", "Sequence", "Render each frame as an image (one file per frame)"),
            ("Video", "Video", "Encode a single video after all frames return"),
        ],
        default="Sequence",
        update=_sync_render_mode_and_persist,
    )
    # How to bake the scene's simulations before a distributed render. Shown + applied only when the
    # scene scan finds a bakeable simulation (scene_has_simulation); a sim must never reach a plain
    # Render* script unbaked. Bucket-1 persisted preference (round-trips via the bridge store).
    bake_strategy: EnumProperty(
        name="Bake simulations",
        description="How to bake the scene's simulations into a frame-addressable cache before the "
                    "distributed render — a simulation cannot be rendered unbaked across nodes",
        items=[
            ("DELEGATED", "On render farm",
             "Bake on the fastest available node, then render distributed — no wait in Blender"),
            ("LOCAL", "On this computer",
             "Bake here in Blender before uploading — you watch the bake; uses your machine"),
        ],
        default="DELEGATED",
        update=_mark_render_settings_changed_and_invalidate,
    )
    # A Render click is in flight (upload/validate/preflight/submit — no job id yet). Drives the
    # local SUBMITTING phase so the panel reacts INSTANTLY; mirrors the operators' re-entry guard.
    launch_in_progress: BoolProperty(name="Launch In Progress", default=False)
    active_job_id: StringProperty(name="Active Job Id", default="")
    active_job_script_name: StringProperty(name="Active Job Script Name", default="")
    active_job_status: StringProperty(name="Active Job Status", default="")
    active_job_progress: StringProperty(name="Active Job Progress", default="")
    active_job_progress_factor: FloatProperty(name="Active Job Progress Factor", default=0.0, min=0.0, max=1.0)
    active_job_distributed_progress: StringProperty(name="Active Job Computation Progress", default="")
    active_job_distributed_progress_factor: FloatProperty(name="Active Job Computation Progress Factor", default=0.0, min=0.0, max=1.0)
    active_job_error: StringProperty(name="Active Job Error", default="")
    active_job_result_blob_id: StringProperty(name="Active Job Result Blob Id", default="")
    active_job_result_blob_count: IntProperty(name="Active Job Result Blob Count", default=0)
    active_job_is_completed: BoolProperty(name="Active Job Is Completed", default=False)
    active_job_cancel_requested: BoolProperty(name="Active Job Cancel Requested", default=False)
    auto_refresh_active_job: BoolProperty(name="Auto Refresh Active Job", default=False)
    auto_refresh_interval_seconds: IntProperty(name="Auto Refresh Interval Seconds", default=5, min=1, max=60)
    download_status: StringProperty(name="Download Status", default="")
    download_message: StringProperty(name="Download Message", default="")
    download_primary_path: StringProperty(name="Download Primary Path", default="")
    download_primary_file_name: StringProperty(name="Download Primary File Name", default="")
    download_item_count: IntProperty(name="Download Item Count", default=0)


CLASSES = (OutWitBridgeRuntimeState,)


def register_state():
    WindowManager.outwit_bridge_state = PointerProperty(type=OutWitBridgeRuntimeState)


def unregister_state():
    if hasattr(WindowManager, "outwit_bridge_state"):
        del WindowManager.outwit_bridge_state
