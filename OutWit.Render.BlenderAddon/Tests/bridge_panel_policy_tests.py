from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace


ADDON_DIR = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"
PACKAGE_NAME = "outwit_render_bridge"


def _load_bridge_panel_module():
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ADDON_DIR)]
    sys.modules[PACKAGE_NAME] = package

    bpy_module = types.ModuleType("bpy")
    bpy_types_module = types.ModuleType("bpy.types")

    class Panel:
        pass

    bpy_types_module.Panel = Panel
    bpy_module.types = bpy_types_module

    sys.modules["bpy"] = bpy_module
    sys.modules["bpy.types"] = bpy_types_module

    branding_module = types.ModuleType(f"{PACKAGE_NAME}.branding")
    branding_module.get_logo_icon_id = lambda _context: 0
    sys.modules[f"{PACKAGE_NAME}.branding"] = branding_module

    dependency_policy_spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.bridge_dependency_policy",
        ADDON_DIR / "bridge_dependency_policy.py",
    )
    if dependency_policy_spec is None or dependency_policy_spec.loader is None:
        raise RuntimeError("Failed to load bridge_dependency_policy.py")

    dependency_policy_module = importlib.util.module_from_spec(dependency_policy_spec)
    sys.modules[f"{PACKAGE_NAME}.bridge_dependency_policy"] = dependency_policy_module
    dependency_policy_spec.loader.exec_module(dependency_policy_module)

    panel_spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.bridge_panel",
        ADDON_DIR / "bridge_panel.py",
    )
    if panel_spec is None or panel_spec.loader is None:
        raise RuntimeError("Failed to load bridge_panel.py")

    panel_module = importlib.util.module_from_spec(panel_spec)
    sys.modules[f"{PACKAGE_NAME}.bridge_panel"] = panel_module
    panel_spec.loader.exec_module(panel_module)
    return panel_module


bridge_panel = _load_bridge_panel_module()


def _create_state() -> SimpleNamespace:
    return SimpleNamespace(
        uploaded_blob_id="blob-1",
        is_signed_in=True,
        can_launch=True,
        current_blend_path="C:/Workspace/test.blend",
        current_blend_file_exists=True,
        validate_job_id="job-1",
        validate_status="Completed",
        validate_message="Blend validated with warnings.",
        validate_is_valid=True,
        validate_issue_summary="",
        validate_warning_summary="Scene uses external image asset 'Texture' from '/tmp/texture.png'.",
        preflight_status="",
        preflight_message="",
        preflight_issue_summary="",
        preflight_warning_summary="",
        preflight_still_ready=False,
        preflight_frames_ready=False,
        preflight_still_tiled_ready=False,
        preflight_video_ready=False,
        preflight_can_render_all=False,
        preflight_still_issue_summary="",
        preflight_still_warning_summary="",
        preflight_frames_issue_summary="",
        preflight_frames_warning_summary="",
        preflight_still_tiled_issue_summary="",
        preflight_still_tiled_warning_summary="",
        preflight_video_issue_summary="",
        preflight_video_warning_summary="",
        dependency_plan_total_count=2,
        dependency_plan_count_summary="Image assets × 1 | Fonts × 1",
        dependency_plan_packed_count=1,
        dependency_plan_packed_summary="Image assets × 1",
        dependency_plan_attachment_count=1,
        dependency_plan_attachment_summary="Fonts × 1",
        render_mode="Still",
        active_job_id="",
        active_job_status="",
        active_job_error="",
        active_job_script_name="",
        active_job_progress="",
        active_job_result_blob_id="",
        active_job_result_blob_count=0,
        active_job_is_completed=False,
        download_primary_path="",
        download_primary_file_name="",
        download_status="",
        download_item_count=0,
        scene_engine_family="Cycles",
        scene_render_engine="CYCLES",
        status_message="Blend validated with warnings.",
    )


class BridgePanelPolicyTests(unittest.TestCase):
    def test_validation_policy_treats_external_dependency_warning_as_blocked(self) -> None:
        state = _create_state()

        result = bridge_panel._validation_policy(state)

        self.assertEqual("Blocked", result)

    def test_primary_finding_uses_dependency_policy_message_before_raw_warning(self) -> None:
        state = _create_state()

        result = bridge_panel._primary_finding(state)

        self.assertIn("Current v1 policy blocks scenes with unresolved external dependencies", result)
        self.assertIn("Scene uses external image asset 'Texture'", result)

    def test_can_start_render_returns_false_for_dependency_policy_block(self) -> None:
        state = _create_state()

        result = bridge_panel._can_start_render(state)

        self.assertFalse(result)

    def test_primary_finding_uses_cache_specific_policy_message_for_external_cache_warning(self) -> None:
        state = _create_state()
        state.validate_warning_summary = "Scene uses external cache file 'SimCache' from '/tmp/sim.abc'. Ensure this cache remains portable for remote rendering."

        result = bridge_panel._primary_finding(state)

        self.assertIn("unresolved external cache dependencies", result)
        self.assertIn("supported attachment-backed cache-file path", result)

    def test_selected_mode_policy_returns_blocked_for_cache_portability_warning(self) -> None:
        state = _create_state()
        state.validate_warning_summary = "Scene uses external cache file 'SimCache' from '/tmp/sim.abc'. Ensure this cache remains portable for remote rendering."
        state.preflight_status = "Completed"
        state.preflight_can_render_all = True
        state.preflight_still_ready = True

        result = bridge_panel._selected_mode_policy(state)

        self.assertEqual("Blocked", result)

    def test_primary_finding_uses_simulation_cache_policy_message_before_raw_issue(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Fluid domain 'Domain' uses external cache directory '/tmp/cache', which is not portable to remote nodes in the current v1 flow."

        result = bridge_panel._primary_finding(state)

        self.assertIn("fluid simulations that depend on external cache directories", result)
        self.assertIn("Fluid domain 'Domain' uses external cache directory", result)

    def test_primary_finding_uses_baked_mesh_cache_policy_message_before_raw_issue(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Fluid domain 'Domain' requires baked mesh cache before remote rendering."

        result = bridge_panel._primary_finding(state)

        self.assertIn("require baked mesh cache before remote rendering", result)
        self.assertIn("Fluid domain 'Domain' requires baked mesh cache", result)

    def test_primary_finding_uses_baked_simulation_data_policy_message_before_raw_issue(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Fluid domain 'Domain' requires baked simulation data before remote rendering."

        result = bridge_panel._primary_finding(state)

        self.assertIn("require baked data before remote rendering", result)
        self.assertIn("Fluid domain 'Domain' requires baked simulation data", result)

    def test_primary_finding_uses_cloth_simulation_policy_message_before_raw_issue(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Cloth simulation 'Pillow' is not yet portable to remote rendering in the current v1 flow."

        result = bridge_panel._primary_finding(state)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Cloth simulation 'Pillow'", result)

    def test_primary_finding_uses_particle_simulation_policy_message_before_raw_issue(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Particle simulation 'Emitter' is not yet portable to remote rendering in the current v1 flow."

        result = bridge_panel._primary_finding(state)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Particle simulation 'Emitter'", result)

    def test_primary_finding_uses_geometry_cache_policy_message_before_raw_issue(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Geometry cache 'AlembicCharacter' is not yet portable to remote rendering in the current v1 flow."

        result = bridge_panel._primary_finding(state)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Geometry cache 'AlembicCharacter'", result)

    def test_dependency_plan_block_message_returns_primary_finding_only_when_blocked(self) -> None:
        state = _create_state()

        result = bridge_panel._dependency_plan_block_message(state)

        self.assertIn("Current v1 policy blocks scenes with unresolved external dependencies", result)

    def test_dependency_plan_block_message_returns_empty_when_scene_is_not_blocked(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_message = "Blend validated successfully."
        state.validate_is_valid = True

        result = bridge_panel._dependency_plan_block_message(state)

        self.assertEqual("", result)

    def test_dependency_plan_block_message_returns_simulation_policy_message_when_simulation_is_blocked(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Cloth simulation 'Pillow' is not yet portable to remote rendering in the current v1 flow."

        result = bridge_panel._dependency_plan_block_message(state)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Cloth simulation 'Pillow'", result)

    def test_can_start_render_returns_false_for_simulation_cache_policy_block(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_issue_summary = "Particle simulation 'Emitter' is not yet portable to remote rendering in the current v1 flow."
        state.preflight_status = "Completed"
        state.preflight_can_render_all = True
        state.preflight_still_ready = True

        result = bridge_panel._can_start_render(state)

        self.assertFalse(result)

    def test_supported_image_sequence_attachment_path_stays_ready_in_compact_policy_flow(self) -> None:
        state = _create_state()
        state.validate_warning_summary = ""
        state.validate_message = "Blend validated successfully."
        state.validate_is_valid = True
        state.dependency_plan_total_count = 2
        state.dependency_plan_count_summary = "Image sequences × 2"
        state.dependency_plan_packed_count = 0
        state.dependency_plan_packed_summary = ""
        state.dependency_plan_attachment_count = 2
        state.dependency_plan_attachment_summary = "Image sequences × 2"
        state.preflight_status = "Completed"
        state.preflight_can_render_all = True
        state.preflight_still_ready = True
        state.preflight_message = "Still render ready."

        policy = bridge_panel._selected_mode_policy(state)
        can_start = bridge_panel._can_start_render(state)
        block_message = bridge_panel._dependency_plan_block_message(state)

        self.assertEqual("Ready", policy)
        self.assertTrue(can_start)
        self.assertEqual("", block_message)


if __name__ == "__main__":
    unittest.main()
