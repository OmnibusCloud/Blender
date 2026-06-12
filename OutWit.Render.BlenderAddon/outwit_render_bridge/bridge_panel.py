"""The N-panel UI. Phase 2 of the redesign (see docs/omnibuscloud-render-bridge-implementation-plan.md):
the 12-class panel collapses into three visible surfaces — identity header, the Render work-flow, and a
collapsed Advanced/Diagnostics block — so the artist sees one clean flow (90%) with diagnostics tucked
away (10%).

The whole main flow reads ONE `StatusView` from `bridge_status.compute_status`: the identity gate, the
Render setup/lifecycle/results, and the readiness of the big Render button all come from the same source,
so the panel and the operators can no longer drift. The Advanced panels keep their own policy helpers —
that is the diagnostic 10%, not the main flow.
"""

from __future__ import annotations

import os

import bpy
from bpy.types import Panel

from .branding import get_logo_icon_id, get_mark_icon_id, get_tray_icon_id
from .bridge_dependency_policy import (
    get_dependency_portability_blocking_issue,
    get_simulation_cache_blocking_issue,
)
from .bridge_launcher import note_panel_visible
from .bridge_engine_routing import scene_frame_count
from .bridge_status import (
    Phase,
    authorized_group_count,
    compute_status,
    connection_icon_key,
    first_non_empty,
    first_summary_item,
    merge_unique_summaries,
    target_label,
    target_option_count,
    wrap_message,
)


# region Tools


def _get_runtime_state(context):
    return context.window_manager.outwit_bridge_state


def _has_uploaded_blob(state) -> bool:
    return bool(state.uploaded_blob_id)


def _has_active_job(state) -> bool:
    return bool(state.active_job_id)


def _has_downloaded_result(state) -> bool:
    return bool(state.download_primary_path)


def _can_load_result_image(state) -> bool:
    if not state.download_primary_path:
        return False

    extension = os.path.splitext(state.download_primary_path)[1].lower()
    return extension in {".png", ".jpg", ".jpeg", ".exr", ".bmp", ".tga", ".tif", ".tiff"}


def _blend_basename(state) -> str:
    return os.path.basename(state.current_blend_path) if state.current_blend_path else "Not saved"


# endregion


# region Diagnostics policy (the Advanced 10% — kept local; not on the main status path)


def _summary_items(summary: str) -> list[str]:
    return [item.strip() for item in (summary or "").split("|") if item.strip()]


def _draw_issue_lines(layout, summary: str) -> None:
    for item in _summary_items(summary):
        layout.label(text=item)


def _selected_mode_value(state, still, still_tiled, frames, video):
    if state.render_mode == "Still":
        return still
    if state.render_mode == "StillTiled":
        return still_tiled
    if state.render_mode == "Frames":
        return frames
    return video


def _render_mode_label(state) -> str:
    return _selected_mode_value(state, "Still", "Tiled still", "Frames", "Video")


def _selected_mode_preflight_issue_summary(state) -> str:
    return _selected_mode_value(
        state,
        state.preflight_still_issue_summary,
        state.preflight_still_tiled_issue_summary,
        state.preflight_frames_issue_summary,
        state.preflight_video_issue_summary,
    )


def _selected_mode_preflight_warning_summary(state) -> str:
    return _selected_mode_value(
        state,
        state.preflight_still_warning_summary,
        state.preflight_still_tiled_warning_summary,
        state.preflight_frames_warning_summary,
        state.preflight_video_warning_summary,
    )


def _has_validation_result(state) -> bool:
    return bool(
        state.validate_job_id
        or state.validate_status
        or state.validate_message
        or state.validate_issue_summary
        or state.validate_warning_summary
    )


def _has_preflight_result(state) -> bool:
    return bool(
        state.preflight_status
        or state.preflight_message
        or state.preflight_issue_summary
        or state.preflight_warning_summary
        or state.preflight_still_ready
        or state.preflight_frames_ready
        or state.preflight_still_tiled_ready
        or state.preflight_video_ready
        or state.preflight_can_render_all
    )


def _policy_icon(policy: str) -> str:
    if policy == "Ready":
        return "CHECKMARK"
    if policy == "Ready with warnings":
        return "INFO"
    if policy == "Blocked":
        return "ERROR"
    return "QUESTION"


def _draw_policy_line(layout, label: str, policy: str) -> None:
    layout.label(text=f"{label}: {policy}", icon=_policy_icon(policy))


def _engine_policy(state) -> str:
    if state.scene_engine_family == "Unsupported":
        return "Blocked"
    if state.scene_engine_family:
        return "Ready"
    return "Not checked"


def _validation_policy(state) -> str:
    if not _has_validation_result(state):
        return "Not checked"
    if state.validate_issue_summary:
        return "Blocked"
    if get_dependency_portability_blocking_issue(state.validate_warning_summary):
        return "Blocked"
    if state.validate_warning_summary:
        return "Ready with warnings"
    return "Ready" if state.validate_is_valid else "Blocked"


def _dependency_policy_message(state) -> str:
    return get_dependency_portability_blocking_issue(
        merge_unique_summaries(state.validate_warning_summary, _selected_mode_preflight_warning_summary(state))
    )


def _simulation_cache_policy_message(state) -> str:
    return get_simulation_cache_blocking_issue(
        merge_unique_summaries(state.validate_issue_summary, _selected_mode_preflight_issue_summary(state))
    )


def _selected_mode_policy(state) -> str:
    if _validation_policy(state) == "Blocked":
        return "Blocked"
    if not _has_preflight_result(state):
        return "Not checked"
    is_ready = bool(_selected_mode_value(
        state,
        state.preflight_still_ready,
        state.preflight_still_tiled_ready,
        state.preflight_frames_ready,
        state.preflight_video_ready,
    ))
    if not is_ready:
        return "Blocked"
    if _dependency_policy_message(state):
        return "Blocked"
    if state.validate_warning_summary or _selected_mode_preflight_warning_summary(state):
        return "Ready with warnings"
    return "Ready"


def _unsupported_engine_message(state) -> str:
    if state.scene_engine_family != "Unsupported":
        return ""
    engine_token = state.scene_render_engine or "unknown"
    return f"Unsupported Blender render engine '{engine_token}'. Supported engines: Cycles, Eevee/Eevee Next, Grease Pencil."


def _primary_finding(state) -> str:
    return first_non_empty(
        _simulation_cache_policy_message(state),
        first_summary_item(state.validate_issue_summary),
        first_summary_item(_selected_mode_preflight_issue_summary(state)),
        _unsupported_engine_message(state),
        _dependency_policy_message(state),
        first_summary_item(state.validate_warning_summary),
        first_summary_item(_selected_mode_preflight_warning_summary(state)),
    )


def _primary_finding_policy(state) -> str:
    if _simulation_cache_policy_message(state):
        return "Blocked"
    if state.validate_issue_summary or state.validate_warning_summary:
        return _validation_policy(state)
    if _selected_mode_preflight_issue_summary(state) or _selected_mode_preflight_warning_summary(state):
        return _selected_mode_policy(state)
    if _engine_policy(state) == "Blocked":
        return "Blocked"
    return "Not checked"


def _dependency_plan_block_message(state) -> str:
    return _primary_finding(state) if _primary_finding_policy(state) == "Blocked" else ""


# endregion


# region Main-flow draw (single source: compute_status)


def _scene_is_dirty() -> bool:
    """LIVE unsaved-changes check. state.current_blend_is_dirty is a snapshot taken at the
    one-shot state sync — changing the format/frame AFTER it left the flag stale False, so the
    Save-scene button never appeared and the user could not persist the change into the .blend
    (the format then 'reverted' on the next Blender start)."""
    return bool(getattr(bpy.data, "is_dirty", False))


def _addon_version_text() -> str:
    """The installed addon version from bl_info (package __init__), e.g. '0.10.0'."""
    try:
        import sys

        info = getattr(sys.modules.get(__package__), "bl_info", None)
        version = info.get("version") if info else None
        return ".".join(str(part) for part in version) if version else ""
    except Exception:
        return ""


def _wrap_width_chars(context) -> int:
    """Estimate how many characters fit one panel line (labels never wrap on their own)."""
    region = getattr(context, "region", None)
    width_px = getattr(region, "width", 0) or 300
    try:
        ui_scale = float(context.preferences.system.ui_scale) or 1.0
    except Exception:
        ui_scale = 1.0
    return max(16, int(width_px / (7.5 * ui_scale)))


def _draw_message(layout, context, text, icon="NONE", alert=False, copyable=False) -> None:
    """A long status/blocker/error message, wrapped over multiple label rows so it is readable in
    full (a single label silently truncates to the panel width), with an optional copy-to-clipboard
    button for error texts worth pasting into a report."""
    lines = wrap_message(text, _wrap_width_chars(context))
    if not lines:
        return

    column = layout.column(align=True)
    column.alert = alert
    for index, line in enumerate(lines):
        column.label(text=line, icon=icon if index == 0 else "NONE")

    if copyable:
        copy_row = layout.row()
        copy_row.alignment = "RIGHT"
        props = copy_row.operator("outwit.bridge_copy_text", text="Copy", icon="COPYDOWN")
        props.text = text


def _draw_status(layout, context, view) -> None:
    """One status line + (at most) one actionable blocker. Reads the StatusView, so the panel and the
    operators always agree on status/blocker/readiness."""
    is_blocked = view.phase == Phase.BLOCKED
    _draw_message(layout, context, view.status_line, icon=view.status_icon, alert=is_blocked,
                  copyable=is_blocked)

    blocker = view.blocker
    if blocker is not None and blocker.has_fix:
        layout.row().operator(blocker.fix_operator, text=blocker.fix_label, icon="ERROR")


def _draw_identity(layout, context, state, view) -> None:
    # Compact brand lockup: connection badge (the desktop client's tray states) + wordmark on the
    # left, account + icon-only Logout right-aligned on the same line.
    icon_id = get_tray_icon_id(connection_icon_key(view.phase)) or get_logo_icon_id(context)
    header = layout.row(align=True)
    if icon_id:
        header.template_icon(icon_value=icon_id, scale=1)
    header.label(text="OmnibusCloud")

    if state.is_signed_in:
        account = header.row(align=True)
        account.alignment = "RIGHT"
        if state.current_user_display_name:
            account.label(text=state.current_user_display_name)
        account.operator("outwit.bridge_sign_out", text="", icon="UNLOCKED")


def _draw_connection_gate(layout, context, state, view) -> None:
    """The pre-Ready gate (shown in the root panel): connecting / bridge-missing / cloud-unreachable /
    signed-out. Login is the brand CTA when signed out; otherwise a status line + a contextual retry.
    Phase 3 replaces the manual buttons with the heartbeat-driven auto-reconnect / Locate / Install."""
    phase = view.phase

    if phase == Phase.SIGNED_OUT:
        # Brand lockup (design §07 "связь и вход"): the detailed mark + wordmark over the Login CTA.
        mark = get_mark_icon_id(context)
        if mark:
            lockup = layout.column(align=True)
            mark_row = lockup.row()
            mark_row.alignment = "CENTER"
            mark_row.template_icon(icon_value=mark, scale=4.0)
            word_row = lockup.row()
            word_row.alignment = "CENTER"
            word_row.label(text="OmnibusCloud")

        box = layout.column(align=True)
        box.label(text="Not signed in")
        login = box.row()
        login.scale_y = 1.4
        # Sign-in runs through the bridge's OIDC flow; it does NOT need the cloud-connected flag (which
        # is normally false until a session exists). Reaching SIGNED_OUT already implies the bridge runs.
        login.operator("outwit.bridge_sign_in", text="Login", icon="URL")
        # begin_sign_in only STARTS the browser flow and returns; the session lands later. Until Phase 3's
        # heartbeat polls it, nothing flips is_signed_in on its own — give an in-place refresh so the user
        # isn't stranded on "Not signed in" after completing sign-in in the browser.
        box.operator("outwit.bridge_refresh_status", text="I've signed in — refresh", icon="FILE_REFRESH")
        return

    line = layout.row()
    line.alert = phase in {Phase.BRIDGE_MISSING, Phase.CLOUD_UNREACHABLE}
    line.label(text=view.status_line, icon=view.status_icon)

    actions = layout.row(align=True)
    if phase == Phase.BRIDGE_MISSING:
        actions.operator("outwit.bridge_start", text="Locate / Start", icon="FILE_FOLDER")
    elif phase == Phase.CLOUD_UNREACHABLE:
        actions.operator("outwit.bridge_refresh_status", text="Reconnect", icon="FILE_REFRESH")
    else:  # DISCONNECTED / CONNECTING
        actions.operator("outwit.bridge_start", text="Connect", icon="PLAY")


def _recommendation_label(recommended: str) -> str:
    # recommended_render_mode only ever returns "Still" or "Video".
    return "Animation · Video" if recommended == "Video" else "Image"


def _draw_output(layout, context, state, view) -> None:
    """The artist-facing output, as two axes (the design's core simplification):
      Output: Image | Animation; Image reveals a 'split across machines' toggle (-> tiles); Animation
      reveals a frame range + Result: Sequence | Video (-> container/quality). These drive render_mode."""
    scene = context.scene

    # Non-blocking nudge when the selection doesn't fit the scene's output (e.g. a video format on
    # Image). Wrapped like every other message — a one-row label truncated to "Recommend…"; plain
    # labels cannot carry tooltips, so the full text lives in the lines + the button's description.
    if view.recommendation:
        _draw_message(layout, context,
                      f"Recommended: {_recommendation_label(view.recommendation)}", icon="INFO")
        hint = layout.row()
        hint.operator("outwit.bridge_use_recommended_mode", text="Use recommended")

    layout.prop(state, "output_axis", expand=True)

    if state.output_axis == "Image":
        layout.prop(state, "still_frame", text="Frame")
        # Curated format list (only farm-supported PNG/EXR/JPEG); bound to the scene's Output Properties,
        # so the .blend records it and the render reads it live at launch (no re-upload needed).
        layout.prop(state, "output_format", text="Format")
        layout.prop(state, "split_frame")
        if state.split_frame:
            tiles = layout.box()
            tiles.prop(state, "tiles_x")
            tiles.prop(state, "tiles_y")
            tiles.prop(state, "tile_overlap_px")
        return

    # Animation: the frame range lives in the scene (single source of truth); editing here edits it.
    frame_range = layout.row(align=True)
    frame_range.prop(scene, "frame_start", text="Start")
    frame_range.prop(scene, "frame_end", text="End")
    layout.label(text=f"{scene_frame_count(scene)} frames")

    layout.prop(state, "anim_result", expand=True)
    if state.anim_result == "Sequence":
        # Curated format list (farm-supported only); bound to the scene's Output Properties.
        layout.prop(state, "output_format", text="Format")
    else:
        video = layout.box()
        video.prop(state, "video_format", text="Format")
        video.prop(state, "video_frame_rate", text="FPS")
        # ProRes quality is fixed by the profile — CRF does not apply there.
        if not state.video_format.startswith("MOV_PRORES"):
            video.prop(state, "video_constant_rate_factor", text="Quality (CRF)")
        video.label(text="Encodes after all frames return", icon="INFO")


def _draw_target(layout, state) -> None:
    """Target = a specific GROUP (dropdown). 'Run on all nodes' is a separate checkbox, shown only when
    the account is allowed to; when it is checked the group dropdown is disabled. With no authorized
    groups the dropdown is hidden — the checkbox is then the only target."""
    if not state.is_signed_in:
        return

    col = layout.column(align=True)
    if state.can_run_on_all_clients:
        col.prop(state, "run_on_all_nodes")

    if authorized_group_count(state) > 0:
        row = col.row()
        row.enabled = not (state.can_run_on_all_clients and state.run_on_all_nodes)
        row.prop(state, "selected_client_group")


def _draw_render_setup(layout, context, state, view) -> None:
    _draw_target(layout, state)

    _draw_output(layout, context, state, view)

    # One status line + one actionable blocker, from compute_status (replaces the Engine/Scene/Mode matrix).
    _draw_status(layout, context, view)

    # Settings changes routinely dirty the scene (format/frame/range live in the .blend) and a dirty
    # scene blocks Render — give the save right here, above the button (design: Save scene over
    # Render). MUST be the live flag: the state snapshot goes stale the moment the user edits.
    scene_dirty = _scene_is_dirty()
    if scene_dirty:
        layout.label(text="Unsaved changes", icon="ERROR")
        save_row = layout.row()
        save_row.scale_y = 1.2
        save_row.operator("wm.save_mainfile", text="Save scene", icon="FILE_TICK")

    render_row = layout.row()
    render_row.enabled = view.is_ready and not scene_dirty
    render_row.scale_y = 1.6
    render_row.operator("outwit.bridge_launch_render", text="Render", icon="RENDER_STILL")


def _draw_job_progress(layout, state) -> None:
    # Two graphical bars (Blender 4.0+ layout.progress): "Overall" is the engine's coarse stage
    # progress (whole script); "Computation" is the distributed render work that the engine sees as one
    # opaque Grid.ForEach stage — it only shows while/after there is distributed work.
    if state.active_job_progress:
        layout.progress(
            factor=state.active_job_progress_factor,
            text=f"Overall: {state.active_job_progress}",
            type="BAR",
        )
    if state.active_job_distributed_progress:
        layout.progress(
            factor=state.active_job_distributed_progress_factor,
            text=f"Computation: {state.active_job_distributed_progress}",
            type="BAR",
        )


def _draw_job_lifecycle(layout, state, view) -> None:
    """Inline progress + Cancel while a cloud job runs — the artist never leaves the Render panel."""
    context_block = layout.column(align=True)
    context_block.enabled = False
    if state.is_signed_in and target_option_count(state) > 1:
        context_block.label(text=f"Target: {target_label(state)}")
    context_block.label(text=f"Output: {_render_mode_label(state)}")

    layout.label(text=view.status_line, icon=view.status_icon)
    _draw_job_progress(layout, state)

    cancel = layout.row()
    # Cancel only while a server job exists and is still running; during the local SUBMITTING phase
    # there is no job id yet, and once Cancel is clicked we are in CANCELLING and the button is
    # disabled ("finishing current task…" comes from the status line above).
    cancel.enabled = bool(state.active_job_id) \
        and view.phase != Phase.CANCELLING and not state.active_job_is_completed
    cancel.operator("outwit.bridge_cancel_job", text="Cancel", icon="CANCEL")


def _draw_job_results(layout, context, state, view) -> None:
    """Inline result + download/open after a terminal job, with one click back to a fresh render."""
    layout.label(text=view.status_line, icon=view.status_icon)

    if view.phase == Phase.FAILED and state.active_job_error:
        _draw_message(layout, context, state.active_job_error, icon="ERROR", alert=True, copyable=True)

    if view.phase == Phase.COMPLETED:
        if state.download_primary_file_name:
            layout.label(text=state.download_primary_file_name, icon="IMAGE_DATA")

        download = layout.row()
        download.scale_y = 1.3
        download.enabled = _has_active_job(state)
        download.operator("outwit.bridge_download_result", text="Download result", icon="IMPORT")

        open_actions = layout.row(align=True)
        open_actions.enabled = _has_downloaded_result(state)
        open_actions.operator("outwit.bridge_open_result", text="Open")
        open_actions.operator("outwit.bridge_open_result_folder", text="Folder")

        load_image = layout.row()
        load_image.enabled = _can_load_result_image(state)
        load_image.operator("outwit.bridge_load_result_image", text="Load in Blender")

        if state.download_message:
            layout.label(text=state.download_message)

    again = layout.row()
    again.operator("outwit.bridge_reset_job", text="Render again", icon="LOOP_BACK")


# endregion


# region Panels


class OUTWIT_PT_bridge_panel(Panel):
    bl_label = "OmnibusCloud"
    bl_idname = "OUTWIT_PT_bridge_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"

    def draw(self, context):
        # Lazy-first-start: showing the OmnibusCloud panel is what triggers the (off-thread) bridge
        # launch driven by the heartbeat timer. Keep this trivial — draw() runs on the UI thread.
        note_panel_visible()

        layout = self.layout
        state = _get_runtime_state(context)
        view = compute_status(context.scene, state)

        _draw_identity(layout, context, state, view)
        if view.is_connection_issue:
            _draw_connection_gate(layout, context, state, view)


class OUTWIT_PT_bridge_launch_panel(Panel):
    bl_label = "Render"
    bl_idname = "OUTWIT_PT_bridge_launch_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_panel"

    @classmethod
    def poll(cls, context):
        # Hidden behind the connection/auth gate — the root panel handles those phases.
        state = _get_runtime_state(context)
        return not compute_status(context.scene, state).is_connection_issue

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)
        view = compute_status(context.scene, state)

        # The Render block walks its lifecycle in place: setup -> running -> result.
        if view.is_active_job:
            _draw_job_lifecycle(layout, state, view)
        elif view.is_terminal_job:
            _draw_job_results(layout, context, state, view)
        else:
            _draw_render_setup(layout, context, state, view)


class OUTWIT_PT_bridge_advanced_panel(Panel):
    bl_label = "Advanced / Diagnostics"
    bl_idname = "OUTWIT_PT_bridge_advanced_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    # Top-level panel (no bl_parent_id) so it reads as a fully separate collapsible block in the
    # sidebar, like Blender's own Active Tool / Options / Workspace panels — not nested under Render.
    bl_order = 10
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        self.layout.label(text="Diagnostics and manual tools.")


class OUTWIT_PT_bridge_connection_panel(Panel):
    bl_label = "Connection"
    bl_idname = "OUTWIT_PT_bridge_connection_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        layout.label(
            text=f"Bridge: {'Running' if state.bridge_is_running else 'Stopped'}",
            icon="CHECKMARK" if state.bridge_is_running else "X",
        )
        layout.label(
            text=f"Cloud: {'Connected' if state.is_connected_to_cloud else 'Offline'}",
            icon="CHECKMARK" if state.is_connected_to_cloud else "RADIOBUT_OFF",
        )
        # Two different versions: the ADDON (bl_info, what the user installed) and the BRIDGE process
        # it spawned. The old single "Version:" line showed the bridge's and read as a wrong addon
        # version.
        addon_version = _addon_version_text()
        if addon_version:
            layout.label(text=f"Add-on: {addon_version}")
        if state.bridge_version:
            layout.label(text=f"Bridge: {state.bridge_version}")

        actions = layout.row(align=True)
        actions.operator("outwit.bridge_refresh_status", text="Refresh")
        start_button = actions.row(align=True)
        start_button.enabled = not state.bridge_is_running
        start_button.operator("outwit.bridge_start", text="Start")
        stop_button = actions.row(align=True)
        stop_button.enabled = state.bridge_is_running and state.bridge_started_by_addon
        stop_button.operator("outwit.bridge_stop", text="Stop")


class OUTWIT_PT_bridge_account_panel(Panel):
    bl_label = "Account & scope"
    bl_idname = "OUTWIT_PT_bridge_account_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return _get_runtime_state(context).is_signed_in

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        layout.label(text=f"User: {state.current_user_display_name or '—'}")
        layout.operator("outwit.bridge_sign_out", text="Logout", icon="UNLOCKED")

        layout.separator()
        layout.label(text=f"Can launch: {'Yes' if state.can_launch else 'No'}")
        layout.label(text=f"Groups: {state.group_count}   Projects: {state.project_count}")
        if state.can_run_on_all_clients:
            layout.label(text="All clients allowed")


class OUTWIT_PT_bridge_scene_panel(Panel):
    bl_label = "Scene & dependencies"
    bl_idname = "OUTWIT_PT_bridge_scene_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        layout.label(text=f"File: {_blend_basename(state)}")
        if _scene_is_dirty():
            layout.label(text="Unsaved changes", icon="ERROR")
        layout.label(text=f"Frames: {state.scene_frame_start}-{state.scene_frame_end}   Camera: {state.scene_camera_name or 'None'}")
        layout.label(text=f"Engine: {state.scene_engine_family or 'Unknown'}   Format: {state.render_file_format or '—'}")

        upload_row = layout.row()
        upload_row.enabled = bool(state.current_blend_path)
        upload_row.operator("outwit.bridge_upload_blend", text="Upload Blend")
        if state.uploaded_blob_id:
            layout.label(text=f"Uploaded: {state.uploaded_file_name}", icon="CHECKMARK")

        if state.dependency_plan_total_count:
            layout.label(
                text=f"Dependencies: {state.dependency_plan_total_count} found · "
                     f"{state.dependency_plan_packed_count} packed · {state.dependency_plan_attachment_count} attached"
            )
        blocker = _dependency_plan_block_message(state)
        if blocker:
            layout.label(text=blocker, icon="ERROR")


class OUTWIT_PT_bridge_manual_panel(Panel):
    bl_label = "Manual steps"
    bl_idname = "OUTWIT_PT_bridge_manual_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        # These run automatically as part of Render; exposed here only as manual escape hatches.
        validate_row = layout.row()
        validate_row.enabled = _has_uploaded_blob(state)
        validate_row.operator("outwit.bridge_validate_blend", text="Validate")
        _draw_policy_line(layout, "Scene", _validation_policy(state))
        if _validation_policy(state) == "Blocked":
            _draw_issue_lines(layout, state.validate_issue_summary)

        layout.separator()

        layout.operator("outwit.bridge_run_preflight", text="Run preflight")
        _draw_policy_line(layout, _render_mode_label(state), _selected_mode_policy(state))
        if _selected_mode_policy(state) == "Blocked":
            _draw_issue_lines(layout, _selected_mode_preflight_issue_summary(state))
        if state.preflight_message:
            layout.label(text=state.preflight_message)


class OUTWIT_PT_bridge_error_panel(Panel):
    bl_label = "Last Error"
    bl_idname = "OUTWIT_PT_bridge_error_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return bool(_get_runtime_state(context).last_error)

    def draw(self, context):
        _draw_message(self.layout, context, _get_runtime_state(context).last_error,
                      icon="ERROR", copyable=True)


# endregion


CLASSES = (
    OUTWIT_PT_bridge_panel,
    OUTWIT_PT_bridge_launch_panel,
    OUTWIT_PT_bridge_advanced_panel,
    OUTWIT_PT_bridge_connection_panel,
    OUTWIT_PT_bridge_account_panel,
    OUTWIT_PT_bridge_scene_panel,
    OUTWIT_PT_bridge_manual_panel,
    OUTWIT_PT_bridge_error_panel,
)
