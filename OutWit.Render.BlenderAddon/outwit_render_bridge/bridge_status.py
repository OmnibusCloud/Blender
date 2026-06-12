"""Single source of truth for "what state are we in, and what should the panel show".

Phase 1 of the redesign (see docs/omnibuscloud-render-bridge-implementation-plan.md): the panel and
the operators used to each derive status/blocker text from a scatter of boolean flags, and the two
copies drifted (operator reported one thing, panel showed another). `compute_status` is the ONE pure
function that turns the raw runtime state + scene facts into a `StatusView`: a single phase, a single
status line, a single typed blocker (with an optional fix-action), and a collapsed diagnostics map.

Authoritative phase source: the job-execution phases (Submitting/Running/Finalizing/Cancelling/
Completed/Failed/Cancelled) come from the bridge's job poll (the server's job status), NOT a local
guess — connection/auth/blocker phases are computed locally. This structurally prevents the
"locally Running, on the server Cancelled" drift.

This module is UI-free (it reads `scene`/`state`, never draws). The panel and operators both call it.
"""

from __future__ import annotations

import json
import os
import textwrap
from dataclasses import dataclass, field
from enum import Enum

from .bridge_dependency_policy import (
    get_dependency_portability_blocking_issue,
    get_simulation_cache_blocking_issue,
)
from .bridge_engine_routing import (
    recommended_render_mode,
    render_mode_matches_recommendation,
)


# region Phases


class Phase(Enum):
    """The lifecycle the Render block walks through. Connection/auth/blocker phases are computed
    locally; the job-execution phases are sourced from the bridge's job poll (server truth)."""

    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"
    BRIDGE_MISSING = "BridgeMissing"
    CLOUD_UNREACHABLE = "CloudUnreachable"
    SIGNED_OUT = "SignedOut"
    READY = "Ready"
    BLOCKED = "Blocked"
    SUBMITTING = "Submitting"
    RUNNING = "Running"
    FINALIZING = "Finalizing"
    CANCELLING = "Cancelling"   # transitional: Cancel clicked, server/node winding down (current task finishes)
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


# A cloud job is active (running on the farm) in these phases.
ACTIVE_JOB_PHASES = frozenset({Phase.SUBMITTING, Phase.RUNNING, Phase.FINALIZING, Phase.CANCELLING})
# The job has finished (one way or another).
TERMINAL_JOB_PHASES = frozenset({Phase.COMPLETED, Phase.FAILED, Phase.CANCELLED})
# The connection/auth is not yet usable.
CONNECTION_PHASES = frozenset(
    {Phase.DISCONNECTED, Phase.CONNECTING, Phase.BRIDGE_MISSING, Phase.CLOUD_UNREACHABLE, Phase.SIGNED_OUT}
)

# Tray-style connection badge keys (mirror the desktop client's tray icon states).
CONNECTION_ICON_ONLINE = "online"
CONNECTION_ICON_OFFLINE = "offline"
CONNECTION_ICON_ISSUE = "issue"


def connection_icon_key(phase: Phase) -> str:
    """The identity-row connection badge: 'issue' = the link itself is broken (bridge missing /
    cloud unreachable); 'offline' = not connected or not signed in yet; 'online' = an authenticated
    session exists. Scene/policy blockers do NOT demote the badge — the connection is fine."""
    if phase in (Phase.BRIDGE_MISSING, Phase.CLOUD_UNREACHABLE):
        return CONNECTION_ICON_ISSUE
    if phase in (Phase.DISCONNECTED, Phase.CONNECTING, Phase.SIGNED_OUT):
        return CONNECTION_ICON_OFFLINE
    return CONNECTION_ICON_ONLINE


def wrap_message(text: str, max_chars: int) -> list[str]:
    """Splits a long status/blocker/error message into label-sized lines. Blender labels do not
    wrap — a long message used to be silently truncated to the panel width (unreadable and
    uncopyable). Whitespace is normalized so multi-line server errors flow as one paragraph."""
    clean = " ".join((text or "").split())
    if not clean:
        return []
    return textwrap.wrap(clean, width=max(16, int(max_chars)))


# endregion


# region Blockers


class BlockerKind(Enum):
    """A blocker carries a typed fix-action so the panel can render the matching button and the
    operator behind it. NONE = no blocker; kinds without a fix-operator are informational stops."""

    NONE = "none"
    SAVE_SCENE = "save_scene"
    SIGN_IN = "sign_in"
    RECONNECT = "reconnect"
    LOCATE_BRIDGE = "locate_bridge"
    INSTALL_BRIDGE = "install_bridge"
    SWITCH_TO_ANIMATION = "switch_to_animation"
    SWITCH_FORMAT = "switch_format"
    UNSUPPORTED_ENGINE = "unsupported_engine"   # no auto-fix (artist changes the engine)
    NO_ELIGIBLE_TARGET = "no_eligible_target"   # no clients/group available
    POLICY = "policy"                           # validation / preflight / dependency / simulation block


@dataclass(frozen=True)
class Blocker:
    kind: BlockerKind
    message: str
    fix_label: str = ""
    fix_operator: str = ""   # bpy operator idname for the fix button, or "" if no one-click fix

    @property
    def has_fix(self) -> bool:
        return bool(self.fix_operator)


# The only Blender output formats the render controller actually honours (BlenderRenderArgsBuilder +
# the RenderFormat wire enum). Anything else — TIFF, BMP, TARGA, WEBP, … — used to be SILENTLY mapped
# to PNG (_map_render_format's default), so the artist asked for TIFF and got a PNG. We now BLOCK an
# unsupported format with a clear message instead of producing a quietly-wrong result. Image-producing
# modes only (Video encodes to a container, so the frame format is intermediate, not the deliverable).
SUPPORTED_IMAGE_FORMATS = frozenset({"PNG", "OPEN_EXR", "OPEN_EXR_MULTILAYER", "JPEG"})
_IMAGE_OUTPUT_MODES = frozenset({"Still", "StillTiled", "Frames"})


def _scene_image_format(scene) -> str:
    render = getattr(scene, "render", None)
    image_settings = getattr(render, "image_settings", None)
    return (getattr(image_settings, "file_format", "") or "") if image_settings is not None else ""


# endregion


# region StatusView


@dataclass
class StatusView:
    phase: Phase
    status_line: str
    status_icon: str = "BLANK1"
    blocker: Blocker | None = None
    is_ready: bool = False                 # the Render button may fire
    recommendation: str = ""               # recommended render mode if the selection mismatches; else ""
    diagnostics: dict = field(default_factory=dict)

    @property
    def is_active_job(self) -> bool:
        return self.phase in ACTIVE_JOB_PHASES

    @property
    def is_terminal_job(self) -> bool:
        return self.phase in TERMINAL_JOB_PHASES

    @property
    def is_connection_issue(self) -> bool:
        return self.phase in CONNECTION_PHASES


# endregion


# region Summary helpers (single source — formerly duplicated in panel + operators)


def summary_items(summary: str) -> list[str]:
    return [item.strip() for item in (summary or "").split("|") if item.strip()]


def first_summary_item(summary: str) -> str:
    for item in summary_items(summary):
        return item
    return ""


def merge_unique_summaries(*summaries: str) -> str:
    values: list[str] = []
    for summary in summaries:
        for item in summary_items(summary):
            if item not in values:
                values.append(item)
    return " | ".join(values)


def first_non_empty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def target_option_count(state) -> int:
    """How many render targets exist: 'all nodes' (when allowed) plus each authorized group. Always
    >= 1. Used as the read-only job-context cue (was the Target-dropdown hide test before 'all nodes'
    became a checkbox)."""
    count = 1 if getattr(state, "can_run_on_all_clients", False) else 0
    count += authorized_group_count(state)
    return max(1, count)


def authorized_group_count(state) -> int:
    """Number of authorized GROUPS only ('all nodes' is a separate checkbox, not counted here). 0 when
    the user has no groups — the Target dropdown is then hidden (the all-nodes checkbox covers them)."""
    try:
        groups = json.loads(getattr(state, "groups_json", "") or "") or []
    except (ValueError, TypeError):
        groups = []
    return sum(1 for group in groups if str(group.get("id", "")).strip())


def target_label(state) -> str:
    """Human label for the resolved render target — 'All nodes' or the selected group's name. Used as
    the read-only cue while a job runs (the editable controls are hidden then)."""
    if getattr(state, "run_on_all_nodes", False) and getattr(state, "can_run_on_all_clients", False):
        return "All nodes"
    selected = getattr(state, "selected_client_group", "") or ""
    try:
        groups = json.loads(getattr(state, "groups_json", "") or "") or []
    except (ValueError, TypeError):
        groups = []
    for group in groups:
        if str(group.get("id", "")).strip() == selected:
            return str(group.get("name", "")).strip() or selected
    return "—"


# endregion


# region Output axes <-> render_mode (the artist-facing 2-axis model maps onto the 4 internal paths)


def render_mode_for_axes(output_axis: str, split_frame: bool, anim_result: str) -> str:
    """The internal render_mode for a 2-axis selection. Image+split = StillTiled, Image = Still,
    Animation+Video = Video, Animation = Frames."""
    if output_axis == "Image":
        return "StillTiled" if split_frame else "Still"
    return "Video" if anim_result == "Video" else "Frames"


def axes_for_render_mode(mode: str) -> tuple[str, bool, str]:
    """Inverse: (output_axis, split_frame, anim_result) for a render_mode. The axis not implied by the
    mode keeps a neutral default; callers apply only the relevant sub-control to avoid clobbering the
    user's other-axis choice."""
    if mode == "StillTiled":
        return "Image", True, "Sequence"
    if mode == "Frames":
        return "Animation", False, "Sequence"
    if mode == "Video":
        return "Animation", False, "Video"
    return "Image", False, "Sequence"


# endregion


# region Policy (consolidated from bridge_panel._*_policy — the single readiness/blocker authority)


def _selected_mode_value(state, still, still_tiled, frames, video):
    mode = getattr(state, "render_mode", "Still")
    if mode == "Still":
        return still
    if mode == "StillTiled":
        return still_tiled
    if mode == "Frames":
        return frames
    return video


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


def _simulation_cache_block(state) -> str:
    return get_simulation_cache_blocking_issue(
        merge_unique_summaries(state.validate_issue_summary, _selected_mode_preflight_issue_summary(state))
    )


def _dependency_block(state) -> str:
    return get_dependency_portability_blocking_issue(
        merge_unique_summaries(state.validate_warning_summary, _selected_mode_preflight_warning_summary(state))
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
    if _dependency_block(state):
        return "Blocked"
    if state.validate_warning_summary or _selected_mode_preflight_warning_summary(state):
        return "Ready with warnings"
    return "Ready"


# endregion


# region Phase derivation


def _job_phase(state) -> Phase | None:
    """The job-execution phase, sourced from the bridge's reported job status (server truth).
    Returns None when there is no active job."""
    if not getattr(state, "active_job_id", ""):
        return None

    status = (getattr(state, "active_job_status", "") or "").strip().lower()

    # Optimistic transitional state: Cancel was clicked, the server/node are winding down (the current
    # task still finishes). Held until the server reports a terminal status.
    cancel_requested = bool(getattr(state, "active_job_cancel_requested", False))
    if cancel_requested and "cancel" not in status and "complet" not in status and "fail" not in status:
        return Phase.CANCELLING

    if "cancel" in status:
        return Phase.CANCELLED
    if "fail" in status:
        return Phase.FAILED
    if "complet" in status or getattr(state, "active_job_is_completed", False):
        return Phase.COMPLETED
    if "final" in status:
        return Phase.FINALIZING
    if status in {"pending", "scheduled", "waitingforresources", "queued", "submitted", "submitting"}:
        return Phase.SUBMITTING

    # A job exists with a running/unknown status → it is active.
    return Phase.RUNNING


def _connection_phase(state) -> Phase:
    if not getattr(state, "bridge_is_running", False):
        exe = getattr(state, "bridge_executable_path", "") or ""
        if exe and not os.path.exists(exe):
            return Phase.BRIDGE_MISSING
        # Phase 3 refines this to CONNECTING while a launch/connect is in flight.
        return Phase.DISCONNECTED
    # Sign-in is the gate, NOT the bridge's cloud flag. A freshly started bridge legitimately reports
    # cloud "offline" until an authenticated session exists (the addon even treats "signed in with scope"
    # as the cloud-connected signal), so the artist must be able to reach the Login CTA from that state.
    # Cloud-unreachable only matters AFTER sign-in (e.g. the session/scope fetch fails) — a real
    # post-auth connectivity problem, not the normal pre-sign-in state.
    if not getattr(state, "is_signed_in", False):
        return Phase.SIGNED_OUT
    if not getattr(state, "is_connected_to_cloud", False):
        return Phase.CLOUD_UNREACHABLE
    return Phase.READY


# endregion


# region Blocker selection


def _primary_blocker(scene, state) -> Blocker | None:
    """The ONE blocker shown above the Render button (when signed-in + connected). Mirrors the old
    `_can_start_render` gate, but as a typed, fixable blocker."""
    if not getattr(state, "can_launch", False):
        return Blocker(BlockerKind.NO_ELIGIBLE_TARGET, "No eligible render clients available")

    if not getattr(state, "current_blend_path", "") or not getattr(state, "current_blend_file_exists", False):
        return Blocker(BlockerKind.SAVE_SCENE, "Scene not saved", "Save scene", "wm.save_mainfile")

    if _engine_policy(state) == "Blocked":
        return Blocker(
            BlockerKind.UNSUPPORTED_ENGINE,
            "Unsupported render engine (use Cycles, Eevee, or Grease Pencil)",
        )

    image_format = _scene_image_format(scene)
    if getattr(state, "render_mode", "Still") in _IMAGE_OUTPUT_MODES \
            and image_format and image_format not in SUPPORTED_IMAGE_FORMATS:
        return Blocker(
            BlockerKind.SWITCH_FORMAT,
            f"Output format '{image_format}' is not supported — the farm renders PNG, EXR, or JPEG.",
            "Switch to PNG",
            "outwit.bridge_switch_format_to_png",
        )

    simulation = _simulation_cache_block(state)
    if simulation:
        return Blocker(BlockerKind.POLICY, first_summary_item(simulation) or simulation)

    if _validation_policy(state) == "Blocked":
        message = first_summary_item(state.validate_issue_summary) \
            or _dependency_block(state) \
            or state.validate_message \
            or "Scene validation failed"
        return Blocker(BlockerKind.POLICY, message)

    if _selected_mode_policy(state) == "Blocked":
        message = first_summary_item(_selected_mode_preflight_issue_summary(state)) \
            or _dependency_block(state) \
            or "Preflight blocked for the selected output"
        return Blocker(BlockerKind.POLICY, message)

    return None


def _recommendation(scene, state) -> str:
    """A non-blocking nudge: the recommended render mode when the current selection mismatches
    (e.g. a video output format while a still mode is selected). Empty when the selection fits."""
    try:
        recommended = recommended_render_mode(scene)
    except Exception:
        return ""
    current = getattr(state, "render_mode", "Still")
    if render_mode_matches_recommendation(current, recommended):
        return ""
    return recommended


# endregion


# region Diagnostics (collapsed Advanced detail)


def _diagnostics(state) -> dict:
    return {
        "bridge_running": bool(getattr(state, "bridge_is_running", False)),
        "cloud_connected": bool(getattr(state, "is_connected_to_cloud", False)),
        "bridge_version": getattr(state, "bridge_version", "") or "",
        "user": getattr(state, "current_user_display_name", "") or "",
        "engine_family": getattr(state, "scene_engine_family", "") or "",
        "blend_path": getattr(state, "current_blend_path", "") or "",
        "validation_issues": getattr(state, "validate_issue_summary", "") or "",
        "validation_warnings": getattr(state, "validate_warning_summary", "") or "",
        "preflight_issues": _selected_mode_preflight_issue_summary(state),
        "preflight_warnings": _selected_mode_preflight_warning_summary(state),
        "last_error": getattr(state, "last_error", "") or "",
    }


# endregion


# region compute_status (the single entry point)


def _connection_status_view(state, phase: Phase) -> StatusView:
    if phase == Phase.BRIDGE_MISSING:
        return StatusView(phase, "Bridge not found", "ERROR",
                          blocker=Blocker(BlockerKind.LOCATE_BRIDGE, "Bridge not found"),
                          diagnostics=_diagnostics(state))
    if phase == Phase.DISCONNECTED:
        return StatusView(phase, "Connecting to bridge…", "SORTTIME", diagnostics=_diagnostics(state))
    if phase == Phase.CLOUD_UNREACHABLE:
        return StatusView(phase, "Cloud unreachable", "ERROR",
                          blocker=Blocker(BlockerKind.RECONNECT, "Cloud unreachable"),
                          diagnostics=_diagnostics(state))
    # SIGNED_OUT
    return StatusView(phase, "Not signed in", "INFO",
                      blocker=Blocker(BlockerKind.SIGN_IN, "Not signed in"),
                      diagnostics=_diagnostics(state))


def _job_status_view(state, phase: Phase) -> StatusView:
    progress = getattr(state, "active_job_progress", "") or ""
    if phase == Phase.RUNNING:
        return StatusView(phase, progress or "Running…", "SORTTIME", diagnostics=_diagnostics(state))
    if phase == Phase.SUBMITTING:
        return StatusView(phase, "Submitting…", "SORTTIME", diagnostics=_diagnostics(state))
    if phase == Phase.FINALIZING:
        return StatusView(phase, "Finalizing…", "SORTTIME", diagnostics=_diagnostics(state))
    if phase == Phase.CANCELLING:
        return StatusView(phase, "Cancelling — finishing current task…", "SORTTIME", diagnostics=_diagnostics(state))
    if phase == Phase.COMPLETED:
        return StatusView(phase, "Completed", "CHECKMARK", diagnostics=_diagnostics(state))
    if phase == Phase.CANCELLED:
        return StatusView(phase, "Cancelled", "CANCEL", diagnostics=_diagnostics(state))
    # FAILED
    error = getattr(state, "active_job_error", "") or "Render failed"
    return StatusView(phase, first_summary_item(error) or "Render failed", "ERROR", diagnostics=_diagnostics(state))


def compute_status(scene, state) -> StatusView:
    """The one function the panel and operators call. Precedence:
      1. an active/terminal job → its server-sourced phase;
      2. otherwise the connection/auth ladder;
      3. otherwise Ready, or a single typed blocker.
    """
    job_phase = _job_phase(state)
    if job_phase is not None:
        return _job_status_view(state, job_phase)

    connection = _connection_phase(state)
    if connection != Phase.READY:
        return _connection_status_view(state, connection)

    blocker = _primary_blocker(scene, state)
    if blocker is not None:
        return StatusView(
            Phase.BLOCKED, blocker.message, "ERROR",
            blocker=blocker, is_ready=False,
            recommendation=_recommendation(scene, state), diagnostics=_diagnostics(state),
        )

    return StatusView(
        Phase.READY, "Ready to render", "CHECKMARK",
        is_ready=True, recommendation=_recommendation(scene, state), diagnostics=_diagnostics(state),
    )


# endregion
