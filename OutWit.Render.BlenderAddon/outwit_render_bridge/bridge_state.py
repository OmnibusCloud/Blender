from __future__ import annotations

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import PropertyGroup, WindowManager


# Sentinel enum identifier for the "any available client" target (no specific group).
ALL_CLIENTS_GROUP_ID = "__ALL__"

# Blender keeps only weak references to the strings returned by a dynamic EnumProperty
# items callback; if we build them inline they get garbage-collected and the UI shows
# corrupted entries (or crashes). Hold a module-level reference to the last built list.
_GROUP_ENUM_ITEMS_CACHE: list[tuple[str, str, str]] = []


def selected_group_items(self, context):
    """Builds the Target dropdown: 'All clients' (when allowed) + each authorized group.

    Reads the groups the bridge reported for the signed-in user (serialized into
    ``groups_json``) plus ``can_run_on_all_clients``. Identifier is the group id GUID,
    or ``ALL_CLIENTS_GROUP_ID`` for the unscoped option.
    """
    items: list[tuple[str, str, str]] = []

    if self.can_run_on_all_clients:
        items.append((ALL_CLIENTS_GROUP_ID, "All clients", "Render on any available client"))

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

    # Always offer at least one option so the control is never empty.
    if not items:
        items.append((ALL_CLIENTS_GROUP_ID, "All clients", "Render on any available client"))

    _GROUP_ENUM_ITEMS_CACHE.clear()
    _GROUP_ENUM_ITEMS_CACHE.extend(items)
    return _GROUP_ENUM_ITEMS_CACHE


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
        description="Which clients to render on: all available clients, or a specific group",
        items=selected_group_items,
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
    uploaded_file_name: StringProperty(name="Uploaded File Name", default="")
    uploaded_file_size: IntProperty(name="Uploaded File Size", default=0)
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
    still_frame: IntProperty(name="Still Frame", default=1, min=1)
    tiles_x: IntProperty(name="Tiles X", default=2, min=1)
    tiles_y: IntProperty(name="Tiles Y", default=2, min=1)
    tile_overlap_px: IntProperty(name="Tile Overlap Px", default=8, min=0)
    video_frame_rate: IntProperty(name="Video Frame Rate", default=24, min=1)
    video_constant_rate_factor: IntProperty(name="Video Constant Rate Factor", default=23, min=0)
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
