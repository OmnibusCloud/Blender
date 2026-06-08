from __future__ import annotations

import os

import bpy
from bpy.types import Panel

from .branding import get_logo_icon_id
from .bridge_dependency_policy import get_dependency_portability_blocking_issue, get_simulation_cache_blocking_issue
from .bridge_engine_routing import (
    has_multi_frame_range,
    recommended_render_mode,
    render_mode_matches_recommendation,
    scene_frame_count,
)


def _get_runtime_state(context):
    return context.window_manager.outwit_bridge_state


def _get_context_directory(context) -> str:
    preferences = context.preferences.addons[__package__].preferences
    return preferences.bridge_context_directory


def _has_uploaded_blob(state) -> bool:
    return bool(state.uploaded_blob_id)


def _can_start_render(state) -> bool:
    return state.is_signed_in \
        and state.can_launch \
        and bool(state.current_blend_path) \
        and state.current_blend_file_exists \
        and _engine_policy(state) != "Blocked" \
        and _validation_policy(state) != "Blocked" \
        and _selected_mode_policy(state) != "Blocked"


def _has_active_job(state) -> bool:
    return bool(state.active_job_id)


def _has_downloaded_result(state) -> bool:
    return bool(state.download_primary_path)


def _can_load_result_image(state) -> bool:
    if not state.download_primary_path:
        return False

    extension = os.path.splitext(state.download_primary_path)[1].lower()
    return extension in {".png", ".jpg", ".jpeg", ".exr", ".bmp", ".tga", ".tif", ".tiff"}


def _has_job_content(state) -> bool:
    return bool(state.active_job_id or state.active_job_status or state.active_job_error)


def _has_results_content(state) -> bool:
    return bool(state.download_primary_path or state.download_primary_file_name or state.download_status or state.download_item_count)


def _draw_mode_specific_settings(layout, context, state) -> None:
    scene = context.scene

    if state.render_mode in {"Still", "StillTiled"}:
        layout.prop(state, "still_frame")
    else:
        layout.label(text=f"Frame range: {int(scene.frame_start)} - {int(scene.frame_end)}")

    if state.render_mode == "StillTiled":
        layout.prop(state, "tiles_x")
        layout.prop(state, "tiles_y")
        layout.prop(state, "tile_overlap_px")

    if state.render_mode == "Video":
        layout.prop(state, "video_frame_rate")
        layout.prop(state, "video_constant_rate_factor")


def _draw_issue_lines(layout, summary: str) -> None:
    if not summary:
        return

    for me in _summary_items(summary):
        layout.label(text=me)


def _summary_items(summary: str) -> list[str]:
    return [me.strip() for me in summary.split("|") if me.strip()]


def _first_summary_item(summary: str) -> str:
    for me in _summary_items(summary):
        return me

    return ""


def _display_summary(summary: str) -> str:
    return summary or "None"


def _merge_unique_summaries(*summaries: str) -> str:
    values: list[str] = []
    for summary in summaries:
        for item in _summary_items(summary):
            if item not in values:
                values.append(item)

    return " | ".join(values)


def _first_non_empty(*values: str) -> str:
    for me in values:
        if me:
            return me

    return ""


def _selected_mode_value(state, still, still_tiled, frames, video):
    if state.render_mode == "Still":
        return still

    if state.render_mode == "StillTiled":
        return still_tiled

    if state.render_mode == "Frames":
        return frames

    return video


def _primary_finding_policy(state) -> str:
    if _simulation_cache_policy_message(state):
        return "Blocked"

    if state.validate_issue_summary or state.validate_warning_summary:
        return _validation_policy(state)

    selected_mode_policy = _selected_mode_policy(state)
    if _selected_mode_preflight_issue_summary(state) or _selected_mode_preflight_warning_summary(state):
        return selected_mode_policy

    if _engine_policy(state) == "Blocked":
        return "Blocked"

    return "Not checked"


def _dependency_policy_message(state) -> str:
    return get_dependency_portability_blocking_issue(
        _merge_unique_summaries(state.validate_warning_summary, _selected_mode_preflight_warning_summary(state))
    )


def _simulation_cache_policy_message(state) -> str:
    return get_simulation_cache_blocking_issue(
        _merge_unique_summaries(state.validate_issue_summary, _selected_mode_preflight_issue_summary(state))
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


def _preflight_policy(state) -> str:
    if not _has_preflight_result(state):
        return "Not checked"

    if state.preflight_issue_summary or not state.preflight_can_render_all:
        return "Blocked"

    if state.preflight_warning_summary:
        return "Ready with warnings"

    return "Ready"


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


def _mode_policy(is_ready: bool, has_result: bool) -> str:
    if not has_result:
        return "Not checked"

    return "Ready" if is_ready else "Blocked"


def _engine_policy(state) -> str:
    if state.scene_engine_family == "Unsupported":
        return "Blocked"

    if state.scene_engine_family:
        return "Ready"

    return "Not checked"


def _render_mode_label(state) -> str:
    return _selected_mode_value(state, "Still", "Tiled still", "Frames", "Video")


def _draw_policy_line(layout, label: str, policy: str) -> None:
    layout.label(text=f"{label}: {policy}", icon=_policy_icon(policy))


def _finding_icon(policy: str) -> str:
    return "ERROR" if policy == "Blocked" else "INFO"


def _primary_finding(state) -> str:
    return _first_non_empty(
        _simulation_cache_policy_message(state),
        _first_summary_item(state.validate_issue_summary),
        _first_summary_item(_selected_mode_preflight_issue_summary(state)),
        _unsupported_engine_message(state),
        _dependency_policy_message(state),
        _first_summary_item(state.validate_warning_summary),
        _first_summary_item(_selected_mode_preflight_warning_summary(state)),
    )


def _unsupported_engine_message(state) -> str:
    if state.scene_engine_family != "Unsupported":
        return ""

    engine_token = state.scene_render_engine or "unknown"
    return f"Unsupported Blender render engine '{engine_token}'. Supported engines: Cycles, Eevee/Eevee Next, Grease Pencil."


def _dependency_plan_block_message(state) -> str:
    return _primary_finding(state) if _primary_finding_policy(state) == "Blocked" else ""


def _compact_status_label(state) -> str:
    if _has_job_content(state):
        return state.status_message or "OmnibusCloud Render"

    if _engine_policy(state) == "Blocked":
        return "Scene: Blocked"

    selected_mode_policy = _selected_mode_policy(state)
    if selected_mode_policy != "Not checked":
        return f"{_render_mode_label(state)}: {selected_mode_policy}"

    validation_policy = _validation_policy(state)
    if validation_policy != "Not checked":
        return f"Scene: {validation_policy}"

    return state.status_message or "OmnibusCloud Render"


def _job_phase_label(state) -> str:
    status = (state.active_job_status or "").strip()
    if status in {"", "Submitted", "Queued", "Created"}:
        return "Waiting"

    if status in {"Processing", "Running"}:
        return "Running"

    if status == "Finalizing":
        return "Encoding" if "Video" in (state.active_job_script_name or "") else "Collecting"

    if status == "Completed":
        return "Completed"

    if status == "Failed":
        return "Failed"

    if status == "Cancelled":
        return "Cancelled"

    return status


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


def _result_phase_label(state) -> str:
    if state.download_primary_path or state.download_status == "Downloaded":
        return "Downloaded"

    if state.active_job_is_completed and (state.active_job_result_blob_id or state.active_job_result_blob_count > 0):
        return "Ready to download"

    if state.active_job_status == "Finalizing":
        return "Preparing files"

    if _has_active_job(state):
        return "Waiting for completion"

    return "Not available"


def _draw_policy_box(layout, state) -> None:
    box = layout.box()
    selected_mode_policy = _selected_mode_policy(state)
    engine_policy = _engine_policy(state)
    box.alert = selected_mode_policy == "Blocked" or _validation_policy(state) == "Blocked" or engine_policy == "Blocked"
    _draw_policy_line(box, "Engine", engine_policy)
    _draw_policy_line(box, "Scene", _validation_policy(state))
    _draw_policy_line(box, _render_mode_label(state), selected_mode_policy)

    finding = _primary_finding(state)
    if finding:
        box.label(text=finding, icon=_finding_icon(_primary_finding_policy(state)))


class OUTWIT_PT_bridge_panel(Panel):
    bl_label = "OmnibusCloud"
    bl_idname = "OUTWIT_PT_bridge_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)
        icon_id = get_logo_icon_id(context)

        if icon_id:
            layout.template_icon(icon_value=icon_id, scale=3)

        layout.label(text=_compact_status_label(state))

        finding = "" if _has_job_content(state) else _primary_finding(state)
        if finding:
            layout.label(text=finding, icon=_finding_icon(_primary_finding_policy(state)))

        if state.current_user_display_name:
            layout.label(text=f"User: {state.current_user_display_name}")

        actions = layout.row(align=True)
        actions.operator("outwit.bridge_refresh_status", text="Refresh")
        if state.is_signed_in:
            actions.operator("outwit.bridge_sign_out", text="Sign Out")
        else:
            actions.operator("outwit.bridge_sign_in", text="Sign In")

        if _has_job_content(state):
            layout.label(text=f"Job: {_job_phase_label(state)}")
            _draw_job_progress(layout, state)


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

        layout.label(text=f"Bridge: {'Running' if state.bridge_is_running else 'Stopped'}")
        layout.label(text=f"Cloud: {'Connected' if state.is_connected_to_cloud else 'Offline'}")

        if state.bridge_version:
            layout.label(text=f"Bridge version: {state.bridge_version}")

        if state.bridge_launch_message:
            layout.label(text=state.bridge_launch_message)

        if state.last_error:
            layout.label(text=state.last_error)

        actions = layout.row(align=True)
        actions.operator("outwit.bridge_refresh_status", text="Refresh")
        start_button = actions.row(align=True)
        start_button.enabled = not state.bridge_is_running
        start_button.operator("outwit.bridge_start", text="Start")
        stop_button = actions.row(align=True)
        stop_button.enabled = state.bridge_is_running and state.bridge_started_by_addon
        stop_button.operator("outwit.bridge_stop", text="Stop")

class OUTWIT_PT_bridge_scope_panel(Panel):
    bl_label = "Execution Scope"
    bl_idname = "OUTWIT_PT_bridge_scope_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        state = _get_runtime_state(context)
        return state.is_signed_in

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        layout.label(text=f"Can launch: {'Yes' if state.can_launch else 'No'}")
        layout.label(text=f"All clients allowed: {'Yes' if state.can_run_on_all_clients else 'No'}")
        layout.label(text=f"Groups: {state.group_count}")
        layout.label(text=f"Projects: {state.project_count}")


class OUTWIT_PT_bridge_blend_panel(Panel):
    bl_label = "Blend"
    bl_idname = "OUTWIT_PT_bridge_blend_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        layout.label(text=f"File: {os.path.basename(state.current_blend_path) if state.current_blend_path else 'Not saved'}")
        layout.label(text=f"Dirty: {'Yes' if state.current_blend_is_dirty else 'No'}")
        upload_row = layout.row()
        upload_row.enabled = bool(state.current_blend_path)
        upload_row.operator("outwit.bridge_upload_blend", text="Upload Blend")

        if state.uploaded_blob_id:
            layout.label(text=f"Blob Id: {state.uploaded_blob_id}")
            layout.label(text=f"File: {state.uploaded_file_name}")
            layout.label(text=f"Size: {state.uploaded_file_size} bytes")
            if state.upload_message:
                layout.label(text=state.upload_message)

        plan = layout.box()
        plan.label(text="Dependency plan")
        plan.label(text=f"Total discovered: {state.dependency_plan_total_count}")
        plan.label(text=f"Packed in upload copy: {state.dependency_plan_packed_count}")
        plan.label(text=_display_summary(state.dependency_plan_packed_summary))
        plan.label(text=f"Uploaded separately: {state.dependency_plan_attachment_count}")
        plan.label(text=_display_summary(state.dependency_plan_attachment_summary))
        if state.dependency_plan_count_summary:
            plan.label(text="By type")
            _draw_issue_lines(plan, state.dependency_plan_count_summary)

        blocker = _dependency_plan_block_message(state)
        if blocker:
            plan.label(text="Launch blocker", icon="ERROR")
            plan.label(text=blocker)


class OUTWIT_PT_bridge_scene_diagnostics_panel(Panel):
    bl_label = "Scene Diagnostics"
    bl_idname = "OUTWIT_PT_bridge_scene_diagnostics_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        layout.label(text=f"Frame range: {state.scene_frame_start} - {state.scene_frame_end}")
        layout.label(text=f"Camera: {state.scene_camera_name or 'None'}")
        layout.label(text=f"Engine token: {state.scene_render_engine or 'Unknown'}")
        layout.label(text=f"Engine family: {state.scene_engine_family or 'Unknown'}")
        layout.label(text=f"File format: {state.render_file_format or 'Unknown'}")
        layout.label(text=f"Color mode: {state.render_color_mode or 'Unknown'}")


class OUTWIT_PT_bridge_validation_panel(Panel):
    bl_label = "Validation"
    bl_idname = "OUTWIT_PT_bridge_validation_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        validation_actions = layout.row()
        validation_actions.enabled = _has_uploaded_blob(state)
        validation_actions.operator("outwit.bridge_validate_blend", text="Validate Blend")
        _draw_policy_line(layout, "Scene", _validation_policy(state))
        if state.validate_status:
            layout.label(text=f"Status: {state.validate_status}")
        if state.validate_message:
            layout.label(text=state.validate_message)
        _draw_issue_lines(layout, state.validate_issue_summary)
        _draw_issue_lines(layout, state.validate_warning_summary)


class OUTWIT_PT_bridge_preflight_panel(Panel):
    bl_label = "Preflight"
    bl_idname = "OUTWIT_PT_bridge_preflight_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_advanced_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)
        has_preflight_result = _has_preflight_result(state)

        layout.operator("outwit.bridge_run_preflight", text="Run Preflight")
        _draw_policy_line(layout, _render_mode_label(state), _selected_mode_policy(state))
        _draw_policy_line(layout, "All modes", _preflight_policy(state))
        if state.preflight_message:
            layout.label(text=state.preflight_message)
        if _selected_mode_policy(state) == "Blocked":
            _draw_issue_lines(layout, _selected_mode_preflight_issue_summary(state))
        elif _selected_mode_preflight_warning_summary(state):
            _draw_issue_lines(layout, _selected_mode_preflight_warning_summary(state))

        matrix = layout.box()
        matrix.label(text="Mode matrix")
        _draw_policy_line(matrix, "Still", _mode_policy(state.preflight_still_ready, has_preflight_result))
        _draw_policy_line(matrix, "Tiled still", _mode_policy(state.preflight_still_tiled_ready, has_preflight_result))
        _draw_policy_line(matrix, "Frames", _mode_policy(state.preflight_frames_ready, has_preflight_result))
        _draw_policy_line(matrix, "Video", _mode_policy(state.preflight_video_ready, has_preflight_result))
        if state.preflight_status:
            layout.label(text=f"Status: {state.preflight_status}")
        if state.preflight_issue_summary and state.preflight_issue_summary != _selected_mode_preflight_issue_summary(state):
            _draw_issue_lines(layout, state.preflight_issue_summary)
        if state.preflight_warning_summary and state.preflight_warning_summary != _selected_mode_preflight_warning_summary(state):
            _draw_issue_lines(layout, state.preflight_warning_summary)


class OUTWIT_PT_bridge_launch_panel(Panel):
    bl_label = "Render"
    bl_idname = "OUTWIT_PT_bridge_launch_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_panel"

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)
        scene = context.scene

        layout.prop(state, "render_mode")

        # Nudge toward the mode that matches the scene's output (e.g. don't sit on Video for a still).
        recommended = recommended_render_mode(scene)
        if not render_mode_matches_recommendation(state.render_mode, recommended):
            hint = layout.row(align=True)
            hint.label(text=f"Recommended: {recommended}", icon="INFO")
            hint.operator("outwit.bridge_use_recommended_mode", text="Use")
        elif state.render_mode in {"Still", "StillTiled"} and has_multi_frame_range(scene):
            # On a still mode but the scene spans many frames — inform without forcing the expensive mode.
            layout.label(
                text=f"Still renders 1 frame. Scene has {scene_frame_count(scene)} frames — pick Frames for animation.",
                icon="INFO",
            )

        if state.is_signed_in:
            layout.prop(state, "selected_client_group")
        _draw_mode_specific_settings(layout, context, state)
        if state.render_mode in {"Frames", "Video"}:
            layout.label(
                text=f"Frames: {int(scene.frame_start)} - {int(scene.frame_end)}  ({scene_frame_count(scene)} frames)"
            )

        layout.label(text=f"Blend: {os.path.basename(state.current_blend_path) if state.current_blend_path else 'Not saved'}")
        if state.current_blend_is_dirty:
            layout.label(text="Save the scene before launching a cloud render.")

        _draw_policy_box(layout, state)

        # Primary action: one big Render button on its own row (upload -> validate -> preflight -> submit);
        # the preflight-only Check sits on a separate row below it.
        launch_enabled = _can_start_render(state) and not state.current_blend_is_dirty
        render_row = layout.row()
        render_row.enabled = launch_enabled
        render_row.scale_y = 1.6
        render_row.operator("outwit.bridge_launch_render", text="Render", icon="RENDER_STILL")
        check_row = layout.row()
        check_row.enabled = launch_enabled
        check_row.operator("outwit.bridge_run_preflight", text="Check")


class OUTWIT_PT_bridge_job_panel(Panel):
    bl_label = "Job"
    bl_idname = "OUTWIT_PT_bridge_job_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_panel"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        state = _get_runtime_state(context)
        return _has_job_content(state)

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        refresh_job = layout.row(align=True)
        refresh_job.enabled = _has_active_job(state)
        refresh_job.operator("outwit.bridge_refresh_job", text="Refresh")
        refresh_job.prop(state, "auto_refresh_active_job", text="Auto Refresh")
        actions = layout.row(align=True)
        cancel = actions.row(align=True)
        # Cancel only while a job is still running; Reset is always available so a stuck job/error can
        # be cleared without restarting Blender.
        cancel.enabled = _has_active_job(state) and not state.active_job_is_completed
        cancel.operator("outwit.bridge_cancel_job", text="Cancel", icon="CANCEL")
        actions.operator("outwit.bridge_reset_job", text="Reset", icon="LOOP_BACK")
        interval_row = layout.row()
        interval_row.enabled = state.auto_refresh_active_job
        interval_row.prop(state, "auto_refresh_interval_seconds", text="Interval")
        layout.label(text=f"Phase: {_job_phase_label(state)}")
        _draw_job_progress(layout, state)
        if state.active_job_result_blob_id or state.active_job_result_blob_count > 0:
            layout.label(text=f"Result: {_result_phase_label(state)}")
        if state.active_job_error:
            layout.label(text=state.active_job_error)


class OUTWIT_PT_bridge_results_panel(Panel):
    bl_label = "Results"
    bl_idname = "OUTWIT_PT_bridge_results_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_panel"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        state = _get_runtime_state(context)
        return _has_active_job(state) or _has_results_content(state)

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)

        download_button = layout.row()
        download_button.enabled = _has_active_job(state)
        download_button.operator("outwit.bridge_download_result", text="Download Result")
        open_actions = layout.row(align=True)
        open_actions.enabled = _has_downloaded_result(state)
        open_actions.operator("outwit.bridge_open_result", text="Open Result")
        open_actions.operator("outwit.bridge_open_result_folder", text="Open Folder")
        load_image = layout.row()
        load_image.enabled = _can_load_result_image(state)
        load_image.operator("outwit.bridge_load_result_image", text="Load Result Image")
        layout.label(text=f"State: {_result_phase_label(state)}")
        if state.download_primary_file_name:
            layout.label(text=f"File: {state.download_primary_file_name}")
        elif state.download_item_count > 0:
            layout.label(text=f"Items: {state.download_item_count}")
        if state.download_message:
            layout.label(text=state.download_message)


class OUTWIT_PT_bridge_advanced_panel(Panel):
    bl_label = "Advanced Diagnostics"
    bl_idname = "OUTWIT_PT_bridge_advanced_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.label(text="Diagnostics and manual tools.")


class OUTWIT_PT_bridge_error_panel(Panel):
    bl_label = "Last Error"
    bl_idname = "OUTWIT_PT_bridge_error_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OmnibusCloud"
    bl_parent_id = "OUTWIT_PT_bridge_panel"

    @classmethod
    def poll(cls, context):
        state = _get_runtime_state(context)
        return bool(state.last_error)

    def draw(self, context):
        layout = self.layout
        state = _get_runtime_state(context)
        layout.label(text=state.last_error)


CLASSES = (
    OUTWIT_PT_bridge_panel,
    OUTWIT_PT_bridge_launch_panel,
    OUTWIT_PT_bridge_job_panel,
    OUTWIT_PT_bridge_results_panel,
    OUTWIT_PT_bridge_advanced_panel,
    OUTWIT_PT_bridge_connection_panel,
    OUTWIT_PT_bridge_scope_panel,
    OUTWIT_PT_bridge_blend_panel,
    OUTWIT_PT_bridge_scene_diagnostics_panel,
    OUTWIT_PT_bridge_validation_panel,
    OUTWIT_PT_bridge_preflight_panel,
    OUTWIT_PT_bridge_error_panel,
)
