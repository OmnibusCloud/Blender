"""Single source of truth for "what state are we in, and what should the panel show".

The panel and the operators used to each derive status/blocker text from a scatter of boolean flags, and the two
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
    get_non_simulation_validation_issue,
    get_simulation_cache_blocking_issue,
    resolve_bake_plan,
)
from .bridge_engine_routing import (
    render_mode_matches_recommendation,
    scene_frame_count,
    suggested_render_mode,
)
from .bridge_targets import split_target_id


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
SUPPORTED_IMAGE_FORMATS = frozenset({"PNG", "OPEN_EXR", "OPEN_EXR_MULTILAYER", "JPEG", "TIFF", "WEBP"})
_IMAGE_OUTPUT_MODES = frozenset({"Still", "StillTiled", "Frames"})

# The ffmpeg tile stitcher (and the video intermediate-frame path) are verified for 8-bit PNG/JPEG
# only — the server preflight enforces the same allowlist. Mirroring it locally turns a
# launch-and-fail into a pre-launch blocker with a one-click fix.
_STITCH_SAFE_FORMATS = frozenset({"PNG", "JPEG"})


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


def _scope_entries(state, attr: str) -> list[dict]:
    try:
        entries = json.loads(getattr(state, attr, "") or "") or []
    except (ValueError, TypeError):
        entries = []
    return entries


def target_option_count(state) -> int:
    """How many render targets exist: 'all nodes' (when allowed) plus each authorized project and
    group. Always >= 1. Used as the read-only job-context cue (was the Target-dropdown hide test
    before 'all nodes' became a checkbox)."""
    count = 1 if getattr(state, "can_run_on_all_clients", False) else 0
    count += authorized_target_count(state)
    return max(1, count)


def authorized_group_count(state) -> int:
    """Number of authorized GROUPS only ('all nodes' is a separate checkbox, not counted here)."""
    return sum(1 for group in _scope_entries(state, "groups_json") if str(group.get("id", "")).strip())


def authorized_project_count(state) -> int:
    """Number of PROJECTS (campaigns) the user may launch into."""
    return sum(1 for project in _scope_entries(state, "projects_json") if str(project.get("id", "")).strip())


def authorized_target_count(state) -> int:
    """Dropdown entries: projects + groups. 0 hides the Target dropdown (the all-nodes checkbox is
    then the only option — or, without that right, Render is blocked with NO_RENDER_TARGET)."""
    return authorized_project_count(state) + authorized_group_count(state)


def has_render_target(state) -> bool:
    """Any way to launch at all: the all-nodes right, a project, or a group."""
    return bool(getattr(state, "can_run_on_all_clients", False)) or authorized_target_count(state) > 0


def target_label(state) -> str:
    """Human label for the resolved render target — 'All nodes' or the selected project/group name.
    Used as the read-only cue while a job runs (the editable controls are hidden then)."""
    if getattr(state, "run_on_all_nodes", False) and getattr(state, "can_run_on_all_clients", False):
        return "All nodes"
    kind, raw_id = split_target_id(getattr(state, "selected_client_group", "") or "")
    entries = _scope_entries(state, "projects_json" if kind == "project" else "groups_json")
    for entry in entries:
        if str(entry.get("id", "")).strip() == raw_id:
            return str(entry.get("name", "")).strip() or raw_id
    return "—"


def format_bytes(byte_count: int) -> str:
    """Human-readable size for progress text: 512 B, 4.2 MB, 1.3 GB."""
    size = float(max(0, int(byte_count)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


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


def _bake_plan(state):
    """How the artist's bake strategy resolves the scene's simulation-cache block (if any).

    The authoritative "is there an unbaked simulation?" signal is the validator/preflight
    simulation-cache block (what the farm would refuse); the strategy decides whether a bake
    covers it. Returns a ``BakePlan`` (see ``bridge_dependency_policy.resolve_bake_plan``)."""
    from .bridge_dependency_policy import LOCAL_BAKE_AVAILABLE

    return resolve_bake_plan(
        bool(_simulation_cache_block(state)),
        getattr(state, "bake_strategy", "DELEGATED"),
        LOCAL_BAKE_AVAILABLE,
    )


def _simulation_bake_covers(state) -> bool:
    """True when a chosen bake plan resolves the scene's simulation block, so the Render gate may
    treat the simulation as non-blocking (it will be baked before the distributed render)."""
    plan = _bake_plan(state)
    return (plan.should_delegate or plan.should_local) and not plan.block


def _residual_validation_issue(state) -> str:
    """The hard validation issue that still blocks after accounting for the bake plan.

    A simulation-cache issue is dropped when the bake plan covers it (the bake produces the cache);
    a strategy that cannot bake (LOCAL before its driver ships) keeps the block; any non-simulation
    issue always remains."""
    merged = merge_unique_summaries(state.validate_issue_summary, _selected_mode_preflight_issue_summary(state))
    if not merged:
        return ""

    plan = _bake_plan(state)
    if plan.block:
        return plan.block

    if plan.should_delegate or plan.should_local:
        return get_non_simulation_validation_issue(merged)

    return first_summary_item(merged) or merged


def _validation_policy(state) -> str:
    if not _has_validation_result(state):
        return "Not checked"
    if _residual_validation_issue(state):
        return "Blocked"
    if get_dependency_portability_blocking_issue(state.validate_warning_summary):
        return "Blocked"
    if state.validate_warning_summary:
        return "Ready with warnings"
    return "Ready" if (state.validate_is_valid or _simulation_bake_covers(state)) else "Blocked"


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
    if getattr(state, "embedded_session_pending", False) and not (
        getattr(state, "is_signed_in", False) and getattr(state, "is_connected_to_cloud", False)
    ):
        # Embedded startup: a persisted-session restore / connect is in flight. One calm
        # phase covers the whole window — flashing "Not signed in" and then a red
        # "Cloud unreachable" between its steps read as errors during a normal start.
        return Phase.CONNECTING
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
    # Launch-week req 4: a signed-in account with NO target at all (no all-nodes right, no project,
    # no group) gets a specific message and a greyed Render — not a server rejection after upload.
    if not has_render_target(state):
        return Blocker(
            BlockerKind.NO_ELIGIBLE_TARGET,
            "No render target — join a render group or start a campaign first",
        )

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
    render_mode = getattr(state, "render_mode", "Still")
    if render_mode in _IMAGE_OUTPUT_MODES \
            and image_format and image_format not in SUPPORTED_IMAGE_FORMATS:
        return Blocker(
            BlockerKind.SWITCH_FORMAT,
            f"Output format '{image_format}' is not supported — the farm renders PNG, EXR, JPEG, TIFF, or WebP.",
            "Switch to PNG",
            "outwit.bridge_switch_format_to_png",
        )

    # Mirror the server preflight allowlists LOCALLY so the artist sees the block before launching
    # (previously the same message arrived only as a launch failure).
    if render_mode == "StillTiled" and image_format and image_format not in _STITCH_SAFE_FORMATS:
        return Blocker(
            BlockerKind.SWITCH_FORMAT,
            f"Tiled still renders PNG or JPEG only (the tile stitcher) — switch the format or "
            "disable 'Split frame across machines'.",
            "Switch to PNG",
            "outwit.bridge_switch_format_to_png",
        )

    if render_mode == "Video" \
            and image_format in SUPPORTED_IMAGE_FORMATS and image_format not in _STITCH_SAFE_FORMATS:
        return Blocker(
            BlockerKind.SWITCH_FORMAT,
            "Video renders its frames as PNG or JPEG before encoding — switch the image format.",
            "Switch to PNG",
            "outwit.bridge_switch_format_to_png",
        )

    # An unbaked simulation blocks UNLESS the chosen bake strategy covers it (delegated bake, or
    # local once available). A strategy that cannot bake (LOCAL before its driver ships) blocks with
    # its own guidance — the render must never start without a bake plan.
    simulation = _simulation_cache_block(state)
    if simulation and not _simulation_bake_covers(state):
        plan = _bake_plan(state)
        return Blocker(BlockerKind.POLICY, plan.block or first_summary_item(simulation) or simulation)

    if _validation_policy(state) == "Blocked":
        residual = _residual_validation_issue(state)
        message = first_summary_item(residual) \
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
        recommended = suggested_render_mode(scene)
    except Exception:
        return ""
    current = getattr(state, "render_mode", "Still")
    if render_mode_matches_recommendation(current, recommended):
        return ""

    # 'Still' is the SAFETY DEFAULT on open (0.4.1 lesson: never auto-pick a 10000-frame run), not
    # a judgement about the scene: an explicit Animation choice on a MULTI-frame image-format scene
    # is perfectly legitimate — nagging 'Recommended: Image' against it only trains the artist to
    # ignore the hint. Flag Animation modes only when the scene really has a single frame.
    if recommended == "Still" and current in ("Frames", "Video"):
        try:
            if scene_frame_count(scene) > 1:
                return ""
        except Exception:
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
    if phase in (Phase.DISCONNECTED, Phase.CONNECTING):
        # One neutral line for every pre-auth startup frame, both transports: the cold
        # not-yet-ticked state (DISCONNECTED) and the in-flight restore/connect (CONNECTING).
        return StatusView(phase, "Connecting to OmnibusCloud…", "SORTTIME", diagnostics=_diagnostics(state))
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
      2. a launch in flight (upload/validate/preflight/submit) → local SUBMITTING;
      3. otherwise the connection/auth ladder;
      4. otherwise Ready, or a single typed blocker.
    """
    job_phase = _job_phase(state)
    if job_phase is not None:
        return _job_status_view(state, job_phase)

    # A click on Render starts upload + cloud checks BEFORE a job id exists. Without a local
    # transitional phase the panel kept showing READY (active Render button, no reaction at all)
    # until the submit answered 1-2s later — the user could keep clicking. SUBMITTING flips the
    # panel into the lifecycle view immediately; the live progress text is in status_message.
    if getattr(state, "launch_in_progress", False):
        return StatusView(
            Phase.SUBMITTING,
            getattr(state, "status_message", "") or "Submitting render...",
            "SORTTIME",
            diagnostics=_diagnostics(state),
        )

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
