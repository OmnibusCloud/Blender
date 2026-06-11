"""Headless unit tests for bridge_status.compute_status (the redesign's single source of truth).

compute_status is a pure function — it reads a duck-typed `scene` + `state`, never touches bpy. Its
only imports are two sibling modules; we inject controllable stubs for them so the whole module loads
WITHOUT Blender. This is the regression net for all of Phase 1's panel/operator wiring.

Run: python -m unittest (from OutWit.Render.BlenderAddon/tests) — no bpy, no Blender required.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from types import SimpleNamespace as NS

# --- Load bridge_status.py with its two sibling deps stubbed (no bpy needed) ---------------------

_PKG = "owrb_status_test"
_VIDEO_FORMATS = {"FFMPEG", "AVI_JPEG", "AVI_RAW"}


def _load_bridge_status():
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = []
    sys.modules[_PKG] = pkg

    routing = types.ModuleType(_PKG + ".bridge_engine_routing")

    def recommended_render_mode(scene):
        image_settings = getattr(getattr(scene, "render", None), "image_settings", None)
        fmt = getattr(image_settings, "file_format", "") if image_settings is not None else ""
        return "Video" if fmt in _VIDEO_FORMATS else "Still"

    def render_mode_matches_recommendation(current, recommended):
        if current == recommended:
            return True
        return recommended == "Still" and current == "StillTiled"

    routing.recommended_render_mode = recommended_render_mode
    routing.render_mode_matches_recommendation = render_mode_matches_recommendation
    sys.modules[_PKG + ".bridge_engine_routing"] = routing

    deps = types.ModuleType(_PKG + ".bridge_dependency_policy")
    # Defaults: nothing blocks. Tests override via _DEP_BLOCK / _SIM_BLOCK below.
    deps.get_dependency_portability_blocking_issue = lambda summary: _DEP_BLOCK
    deps.get_simulation_cache_blocking_issue = lambda summary: _SIM_BLOCK
    sys.modules[_PKG + ".bridge_dependency_policy"] = deps

    path = os.path.join(os.path.dirname(__file__), "..", "outwit_render_bridge", "bridge_status.py")
    spec = importlib.util.spec_from_file_location(_PKG + ".bridge_status", os.path.abspath(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_DEP_BLOCK = ""   # mutated per-test to simulate a dependency-portability block
_SIM_BLOCK = ""   # mutated per-test to simulate a simulation-cache block
status = _load_bridge_status()


# --- Fakes ----------------------------------------------------------------------------------------

def make_scene(file_format="PNG", frame_start=1, frame_end=1):
    return NS(render=NS(image_settings=NS(file_format=file_format)),
              frame_start=frame_start, frame_end=frame_end, objects=[])


def make_state(**overrides):
    """A connected + signed-in + saved + supported baseline (→ Ready). Override per test."""
    defaults = dict(
        # connection / auth
        bridge_is_running=True, bridge_executable_path="", is_connected_to_cloud=True, is_signed_in=True,
        can_launch=True,
        # scene / blend
        current_blend_path="/proj/scene.blend", current_blend_file_exists=True, current_blend_is_dirty=False,
        scene_engine_family="Cycles", render_mode="Still",
        # validation (empty = not checked → not a blocker)
        validate_job_id="", validate_status="", validate_message="", validate_issue_summary="",
        validate_warning_summary="", validate_is_valid=False,
        # preflight (empty = not checked)
        preflight_status="", preflight_message="", preflight_issue_summary="", preflight_warning_summary="",
        preflight_can_render_all=False,
        preflight_still_ready=False, preflight_frames_ready=False, preflight_still_tiled_ready=False,
        preflight_video_ready=False,
        preflight_still_issue_summary="", preflight_still_tiled_issue_summary="",
        preflight_frames_issue_summary="", preflight_video_issue_summary="",
        preflight_still_warning_summary="", preflight_still_tiled_warning_summary="",
        preflight_frames_warning_summary="", preflight_video_warning_summary="",
        # job
        active_job_id="", active_job_status="", active_job_error="", active_job_is_completed=False,
        active_job_progress="", active_job_cancel_requested=False,
        # diagnostics
        bridge_version="1.0.0", current_user_display_name="dmitry", last_error="",
    )
    defaults.update(overrides)
    return NS(**defaults)


class ComputeStatusTests(unittest.TestCase):

    def setUp(self):
        global _DEP_BLOCK, _SIM_BLOCK
        _DEP_BLOCK = ""
        _SIM_BLOCK = ""

    # --- connection / auth ladder ---

    def test_bridge_not_running_is_disconnected(self):
        view = status.compute_status(make_scene(), make_state(bridge_is_running=False))
        self.assertEqual(view.phase, status.Phase.DISCONNECTED)
        self.assertFalse(view.is_ready)

    def test_bridge_exe_missing_is_bridge_missing(self):
        view = status.compute_status(make_scene(), make_state(
            bridge_is_running=False, bridge_executable_path="/no/such/bridge.exe"))
        self.assertEqual(view.phase, status.Phase.BRIDGE_MISSING)

    def test_signed_in_but_not_connected_is_cloud_unreachable(self):
        # Cloud-unreachable is only a phase AFTER sign-in (post-auth connectivity loss).
        view = status.compute_status(make_scene(), make_state(is_connected_to_cloud=False))
        self.assertEqual(view.phase, status.Phase.CLOUD_UNREACHABLE)

    def test_signed_out_takes_precedence_over_cloud_offline(self):
        # A freshly started bridge reports cloud offline until signed in; the artist must still reach the
        # Login CTA. Regression: gating cloud-before-auth dead-ended at 'Cloud unreachable / Reconnect'.
        view = status.compute_status(make_scene(), make_state(is_signed_in=False, is_connected_to_cloud=False))
        self.assertEqual(view.phase, status.Phase.SIGNED_OUT)
        self.assertEqual(view.blocker.kind, status.BlockerKind.SIGN_IN)

    def test_connected_not_signed_in_is_signed_out_with_signin_blocker(self):
        view = status.compute_status(make_scene(), make_state(is_signed_in=False))
        self.assertEqual(view.phase, status.Phase.SIGNED_OUT)
        self.assertEqual(view.blocker.kind, status.BlockerKind.SIGN_IN)

    # --- blockers (signed in + connected) ---

    def test_no_eligible_target_blocks(self):
        view = status.compute_status(make_scene(), make_state(can_launch=False))
        self.assertEqual(view.phase, status.Phase.BLOCKED)
        self.assertEqual(view.blocker.kind, status.BlockerKind.NO_ELIGIBLE_TARGET)

    def test_unsaved_scene_blocks_with_save_fix(self):
        view = status.compute_status(make_scene(), make_state(current_blend_file_exists=False))
        self.assertEqual(view.phase, status.Phase.BLOCKED)
        self.assertEqual(view.blocker.kind, status.BlockerKind.SAVE_SCENE)
        self.assertTrue(view.blocker.has_fix)
        self.assertEqual(view.blocker.fix_operator, "wm.save_mainfile")

    def test_unsupported_engine_blocks(self):
        view = status.compute_status(make_scene(), make_state(scene_engine_family="Unsupported"))
        self.assertEqual(view.blocker.kind, status.BlockerKind.UNSUPPORTED_ENGINE)
        self.assertFalse(view.blocker.has_fix)

    def test_validation_issue_blocks(self):
        view = status.compute_status(make_scene(), make_state(
            validate_job_id="v1", validate_issue_summary="Missing texture: wood.png"))
        self.assertEqual(view.phase, status.Phase.BLOCKED)
        self.assertEqual(view.blocker.kind, status.BlockerKind.POLICY)
        self.assertIn("wood.png", view.blocker.message)

    def test_simulation_cache_blocks(self):
        global _SIM_BLOCK
        _SIM_BLOCK = "Fluid simulation requires baked data"
        view = status.compute_status(make_scene(), make_state(
            validate_job_id="v1", validate_issue_summary="x"))
        self.assertEqual(view.blocker.kind, status.BlockerKind.POLICY)
        self.assertIn("Fluid", view.blocker.message)

    def test_ready_when_signed_in_saved_supported_and_unchecked(self):
        view = status.compute_status(make_scene(), make_state())
        self.assertEqual(view.phase, status.Phase.READY)
        self.assertTrue(view.is_ready)
        self.assertIsNone(view.blocker)

    # --- recommendation (non-blocking) ---

    def test_recommendation_flags_video_format_with_still_mode(self):
        view = status.compute_status(make_scene(file_format="FFMPEG"), make_state(render_mode="Still"))
        self.assertEqual(view.recommendation, "Video")

    def test_no_recommendation_when_mode_matches(self):
        view = status.compute_status(make_scene(file_format="PNG"), make_state(render_mode="Still"))
        self.assertEqual(view.recommendation, "")

    # --- job phases (server-sourced, authoritative) ---

    def test_processing_is_running(self):
        view = status.compute_status(make_scene(), make_state(active_job_id="j1", active_job_status="Processing"))
        self.assertEqual(view.phase, status.Phase.RUNNING)
        self.assertTrue(view.is_active_job)

    def test_pending_is_submitting(self):
        view = status.compute_status(make_scene(), make_state(active_job_id="j1", active_job_status="Pending"))
        self.assertEqual(view.phase, status.Phase.SUBMITTING)

    def test_cancel_requested_is_cancelling_until_terminal(self):
        view = status.compute_status(make_scene(), make_state(
            active_job_id="j1", active_job_status="Processing", active_job_cancel_requested=True))
        self.assertEqual(view.phase, status.Phase.CANCELLING)

    def test_cancel_requested_yields_to_server_cancelled(self):
        view = status.compute_status(make_scene(), make_state(
            active_job_id="j1", active_job_status="Cancelled", active_job_cancel_requested=True))
        self.assertEqual(view.phase, status.Phase.CANCELLED)

    def test_completed_is_completed(self):
        view = status.compute_status(make_scene(), make_state(active_job_id="j1", active_job_status="Completed"))
        self.assertEqual(view.phase, status.Phase.COMPLETED)
        self.assertTrue(view.is_terminal_job)

    def test_failed_is_failed(self):
        view = status.compute_status(make_scene(), make_state(
            active_job_id="j1", active_job_status="Failed", active_job_error="Blob download failed"))
        self.assertEqual(view.phase, status.Phase.FAILED)

    def test_active_job_takes_precedence_over_connection(self):
        # Even if the connection flags look off, an active job's phase wins (it came from the bridge).
        view = status.compute_status(make_scene(), make_state(
            active_job_id="j1", active_job_status="Processing", is_connected_to_cloud=False))
        self.assertEqual(view.phase, status.Phase.RUNNING)


class TargetOptionCountTests(unittest.TestCase):
    """Drives the panel's 'show Target only when there is more than one choice' rule."""

    def test_all_clients_only_is_one_option(self):
        state = NS(can_run_on_all_clients=True, groups_json="")
        self.assertEqual(status.target_option_count(state), 1)

    def test_no_all_clients_no_groups_falls_back_to_one(self):
        state = NS(can_run_on_all_clients=False, groups_json="")
        self.assertEqual(status.target_option_count(state), 1)

    def test_all_clients_plus_groups_counts_each(self):
        state = NS(can_run_on_all_clients=True,
                   groups_json='[{"id":"g1","name":"A"},{"id":"g2","name":"B"}]')
        self.assertEqual(status.target_option_count(state), 3)

    def test_groups_without_all_clients(self):
        state = NS(can_run_on_all_clients=False, groups_json='[{"id":"g1","name":"A"}]')
        self.assertEqual(status.target_option_count(state), 1)

    def test_blank_group_ids_are_ignored(self):
        state = NS(can_run_on_all_clients=True, groups_json='[{"id":"","name":"x"},{"id":"g2"}]')
        self.assertEqual(status.target_option_count(state), 2)

    def test_malformed_groups_json_is_safe(self):
        state = NS(can_run_on_all_clients=True, groups_json="{not json")
        self.assertEqual(status.target_option_count(state), 1)


class OutputAxisMappingTests(unittest.TestCase):
    """The 2-axis Output model maps 1:1 onto the four internal render_mode paths."""

    def test_image_maps_to_still(self):
        self.assertEqual(status.render_mode_for_axes("Image", False, "Sequence"), "Still")

    def test_image_split_maps_to_tiled(self):
        self.assertEqual(status.render_mode_for_axes("Image", True, "Sequence"), "StillTiled")

    def test_animation_sequence_maps_to_frames(self):
        self.assertEqual(status.render_mode_for_axes("Animation", False, "Sequence"), "Frames")

    def test_animation_video_maps_to_video(self):
        self.assertEqual(status.render_mode_for_axes("Animation", False, "Video"), "Video")

    def test_split_ignored_for_animation(self):
        # split_frame only applies to Image; an Animation selection ignores it.
        self.assertEqual(status.render_mode_for_axes("Animation", True, "Sequence"), "Frames")

    def test_round_trip_every_mode(self):
        for mode in ("Still", "StillTiled", "Frames", "Video"):
            axis, split, result = status.axes_for_render_mode(mode)
            self.assertEqual(status.render_mode_for_axes(axis, split, result), mode)


class UnsupportedFormatBlockerTests(unittest.TestCase):
    """The controller honours only PNG/EXR/JPEG; an unsupported output format used to be SILENTLY
    rendered as PNG. compute_status now blocks it (SWITCH_FORMAT) for image-producing modes."""

    def setUp(self):
        global _DEP_BLOCK, _SIM_BLOCK
        _DEP_BLOCK = ""
        _SIM_BLOCK = ""

    def test_tiff_blocks_in_image_mode(self):
        view = status.compute_status(make_scene(file_format="TIFF"), make_state(render_mode="Still"))
        self.assertEqual(view.phase, status.Phase.BLOCKED)
        self.assertEqual(view.blocker.kind, status.BlockerKind.SWITCH_FORMAT)
        self.assertFalse(view.is_ready)

    def test_supported_formats_do_not_block(self):
        for fmt in ("PNG", "OPEN_EXR", "OPEN_EXR_MULTILAYER", "JPEG"):
            view = status.compute_status(make_scene(file_format=fmt), make_state(render_mode="Still"))
            self.assertNotEqual(view.blocker.kind if view.blocker else status.BlockerKind.NONE,
                                status.BlockerKind.SWITCH_FORMAT, fmt)

    def test_frames_mode_also_blocks_unsupported(self):
        view = status.compute_status(make_scene(file_format="BMP"), make_state(render_mode="Frames"))
        self.assertEqual(view.blocker.kind, status.BlockerKind.SWITCH_FORMAT)

    def test_video_mode_ignores_image_format(self):
        # Video encodes to a container; the per-frame image format is intermediate, not the deliverable.
        view = status.compute_status(make_scene(file_format="TIFF"), make_state(render_mode="Video"))
        self.assertNotEqual(view.blocker.kind if view.blocker else status.BlockerKind.NONE,
                            status.BlockerKind.SWITCH_FORMAT)


class TargetResolutionTests(unittest.TestCase):
    """'All nodes' is a checkbox; Target carries groups only (authorized_group_count / target_label)."""

    _TWO_GROUPS = '[{"id": "g1", "name": "Studio GPUs"}, {"id": "g2", "name": "Farm"}]'

    def test_group_count_is_groups_only(self):
        self.assertEqual(status.authorized_group_count(make_state(groups_json=self._TWO_GROUPS)), 2)
        self.assertEqual(status.authorized_group_count(make_state(groups_json="")), 0)
        self.assertEqual(
            status.authorized_group_count(make_state(groups_json='[{"id": "  ", "name": "blank"}]')), 0)

    def test_target_label_all_nodes(self):
        label = status.target_label(make_state(run_on_all_nodes=True, can_run_on_all_clients=True))
        self.assertEqual(label, "All nodes")

    def test_target_label_group_name(self):
        label = status.target_label(make_state(
            run_on_all_nodes=False, can_run_on_all_clients=False,
            groups_json=self._TWO_GROUPS, selected_client_group="g2"))
        self.assertEqual(label, "Farm")

    def test_all_nodes_only_when_allowed(self):
        # The checkbox is honoured only with the permission; checked-but-not-allowed falls back to group.
        label = status.target_label(make_state(
            run_on_all_nodes=True, can_run_on_all_clients=False,
            groups_json=self._TWO_GROUPS, selected_client_group="g1"))
        self.assertEqual(label, "Studio GPUs")


if __name__ == "__main__":
    unittest.main()
