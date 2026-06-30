from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace


ADDON_DIR = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"
PACKAGE_NAME = "outwit_render_bridge"


def _load_bridge_operators_module():
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ADDON_DIR)]
    sys.modules[PACKAGE_NAME] = package

    bpy_module = types.ModuleType("bpy")
    bpy_types_module = types.ModuleType("bpy.types")

    class Operator:
        def __init__(self):
            self.report_calls: list[tuple[set[str], str]] = []

        def report(self, levels, message):
            self.report_calls.append((set(levels), message))

    bpy_types_module.Operator = Operator
    bpy_types_module.PropertyGroup = type("PropertyGroup", (), {})
    bpy_types_module.WindowManager = type("WindowManager", (), {})
    bpy_module.types = bpy_types_module
    # bridge_operators does `from bpy.props import StringProperty` — the from-import resolves the
    # submodule via sys.modules, so a stub entry is enough (bpy itself is not a package here).
    bpy_props_module = types.ModuleType("bpy.props")
    for _prop in ("StringProperty", "BoolProperty", "IntProperty", "FloatProperty",
                  "EnumProperty", "PointerProperty"):
        setattr(bpy_props_module, _prop, lambda **kwargs: None)
    bpy_module.props = bpy_props_module
    sys.modules["bpy.props"] = bpy_props_module
    bpy_module.data = SimpleNamespace(
        filepath="C:/Workspace/test.blend",
        is_dirty=False,
        images=SimpleNamespace(get=lambda _: None, load=lambda path, check_existing=True: path),
    )
    bpy_module.path = SimpleNamespace(abspath=lambda path: path)
    bpy_module.app = SimpleNamespace(
        timers=SimpleNamespace(
            is_registered=lambda _: False,
            register=lambda *args, **kwargs: None,
            unregister=lambda *args, **kwargs: None,
        ),
        # @bpy.app.handlers.persistent decorator + load_post list (addon 0.4.0 recommended-mode hook).
        handlers=SimpleNamespace(persistent=lambda func: func, load_post=[]),
    )
    bpy_module.context = SimpleNamespace(window_manager=None)

    sys.modules["bpy"] = bpy_module
    sys.modules["bpy.types"] = bpy_types_module

    bridge_client_module = types.ModuleType(f"{PACKAGE_NAME}.bridge_client")

    class BridgeClientError(Exception):
        pass

    class BridgeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def run_render_validate_blend(self, *_args, **_kwargs):
            raise NotImplementedError

        def run_render_preflight(self, *_args, **_kwargs):
            raise NotImplementedError

    bridge_client_module.BridgeClient = BridgeClient
    bridge_client_module.BridgeClientError = BridgeClientError
    sys.modules[f"{PACKAGE_NAME}.bridge_client"] = bridge_client_module

    # bridge_render_settings (Phase 5 seed/sticky logic) is covered by its own headless suite;
    # here it is stubbed like bridge_client (its bridge_models import uses dataclass(slots=True),
    # which needs the Blender-bundled Python, not necessarily the test interpreter).
    render_settings_module = types.ModuleType(f"{PACKAGE_NAME}.bridge_render_settings")
    render_settings_module.compose_remember_payload = lambda current, remember: {}
    render_settings_module.compose_sticky_payload = lambda current, **kwargs: {}
    render_settings_module.group_name_for = lambda groups, group_id: ""
    render_settings_module.resolve_target_seed = lambda settings, groups, can_all: None
    render_settings_module.seed_prop_values = lambda settings: {}
    sys.modules[f"{PACKAGE_NAME}.bridge_render_settings"] = render_settings_module

    bridge_context_module = types.ModuleType(f"{PACKAGE_NAME}.bridge_context")
    bridge_context_module.load_latest_context = lambda *_args, **_kwargs: (None, "")
    bridge_context_module.try_load_latest_context = lambda *_args, **_kwargs: (None, None)
    sys.modules[f"{PACKAGE_NAME}.bridge_context"] = bridge_context_module

    bridge_engine_module = types.ModuleType(f"{PACKAGE_NAME}.bridge_engine_routing")

    class SceneEngineRoutingError(Exception):
        pass

    bridge_engine_module.detect_scene_engine_family = lambda _scene: ("Cycles", 0)
    bridge_engine_module.get_scene_engine_token = lambda _scene: "CYCLES"
    bridge_engine_module.recommended_render_mode = lambda _scene: "Still"
    bridge_engine_module.render_mode_matches_recommendation = lambda current, recommended: current == recommended
    bridge_engine_module.scene_frame_count = lambda _scene: 1
    bridge_engine_module.SceneEngineRoutingError = SceneEngineRoutingError
    sys.modules[f"{PACKAGE_NAME}.bridge_engine_routing"] = bridge_engine_module

    bridge_launcher_module = types.ModuleType(f"{PACKAGE_NAME}.bridge_launcher")
    bridge_launcher_module.acquire_bridge_lease = lambda *_args, **_kwargs: None
    bridge_launcher_module.cleanup_bridge_on_unregister = lambda *_args, **_kwargs: None
    bridge_launcher_module.ensure_bridge_running = lambda *_args, **_kwargs: None
    bridge_launcher_module.get_effective_context_directory = lambda *_args, **_kwargs: "context-dir"
    bridge_launcher_module.launch_bridge = lambda *_args, **_kwargs: None
    bridge_launcher_module.ping_bridge_lease = lambda *_args, **_kwargs: None
    bridge_launcher_module.refresh_bridge_process_state = lambda *_args, **_kwargs: None
    bridge_launcher_module.release_bridge_lease = lambda *_args, **_kwargs: None
    bridge_launcher_module.stop_bridge = lambda *_args, **_kwargs: None
    # Lazy-first-start surface (addon 0.8.0).
    bridge_launcher_module.apply_launched_state = lambda *_args, **_kwargs: None
    bridge_launcher_module.panel_was_seen = lambda: False
    bridge_launcher_module.resolve_launch_target = lambda *_args, **_kwargs: ("bridge.exe", "session")
    bridge_launcher_module.spawn_bridge_process = lambda *_args, **_kwargs: 0
    bridge_launcher_module.is_process_running = lambda _pid: False
    sys.modules[f"{PACKAGE_NAME}.bridge_launcher"] = bridge_launcher_module

    dependency_policy_spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.bridge_dependency_policy",
        ADDON_DIR / "bridge_dependency_policy.py",
    )
    if dependency_policy_spec is None or dependency_policy_spec.loader is None:
        raise RuntimeError("Failed to load bridge_dependency_policy.py")

    dependency_policy_module = importlib.util.module_from_spec(dependency_policy_spec)
    sys.modules[f"{PACKAGE_NAME}.bridge_dependency_policy"] = dependency_policy_module
    dependency_policy_spec.loader.exec_module(dependency_policy_module)

    bridge_scene_packaging_module = types.ModuleType(f"{PACKAGE_NAME}.bridge_scene_packaging")

    class ScenePackagingError(Exception):
        pass

    class _PackedCopyContext:
        def __init__(self, packed_path: str, message: str):
            self._packed_path = packed_path
            self._message = message

        def __enter__(self):
            return self._packed_path, self._message

        def __exit__(self, exc_type, exc, tb):
            return False

    bridge_scene_packaging_module.ScenePackagingError = ScenePackagingError
    bridge_scene_packaging_module.create_packed_upload_copy = lambda path: _PackedCopyContext(path, "Packed upload copy created.")
    bridge_scene_packaging_module.scene_output_signature = lambda _scene: "PNG|RGBA|8|O||"
    sys.modules[f"{PACKAGE_NAME}.bridge_scene_packaging"] = bridge_scene_packaging_module

    bridge_scene_attachments_module = types.ModuleType(f"{PACKAGE_NAME}.bridge_scene_attachments")
    bridge_scene_attachments_module.collect_scene_attachment_metadata = lambda: []
    bridge_scene_attachments_module.summarize_scene_attachment_metadata = lambda attachments: {
        "TotalCount": len(attachments),
        "CountSummary": "",
        "PackedCount": len([me for me in attachments if me.get("PackagingStrategy") == "PackedBlendCopy"]),
        "PackedSummary": "",
        "AttachmentCount": len([me for me in attachments if me.get("PackagingStrategy") == "SceneAttachmentBlob"]),
        "AttachmentSummary": "",
    }
    sys.modules[f"{PACKAGE_NAME}.bridge_scene_attachments"] = bridge_scene_attachments_module

    operators_spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.bridge_operators",
        ADDON_DIR / "bridge_operators.py",
    )
    if operators_spec is None or operators_spec.loader is None:
        raise RuntimeError("Failed to load bridge_operators.py")

    operators_module = importlib.util.module_from_spec(operators_spec)
    sys.modules[f"{PACKAGE_NAME}.bridge_operators"] = operators_module
    operators_spec.loader.exec_module(operators_module)
    return operators_module


bridge_operators = _load_bridge_operators_module()

# Several tests monkeypatch bridge_operators._scene_requires_upload (without restoring it), so keep a
# pristine reference for the test that exercises the real cache-invalidation logic.
_REAL_SCENE_REQUIRES_UPLOAD = bridge_operators._scene_requires_upload


def _create_state() -> SimpleNamespace:
    return SimpleNamespace(
        uploaded_blob_id="blob-1",
        dependency_plan_total_count=0,
        dependency_plan_count_summary="",
        dependency_plan_packed_count=0,
        dependency_plan_packed_summary="",
        dependency_plan_attachment_count=0,
        dependency_plan_attachment_summary="",
        validate_job_id="",
        validate_status="",
        validate_message="",
        validate_is_valid=False,
        validate_issue_summary="",
        validate_warning_summary="",
        preflight_status="",
        preflight_message="",
        preflight_can_render_all=False,
        preflight_still_ready=False,
        preflight_frames_ready=False,
        preflight_still_tiled_ready=False,
        preflight_video_ready=False,
        preflight_still_issue_summary="",
        preflight_still_warning_summary="",
        preflight_frames_issue_summary="",
        preflight_frames_warning_summary="",
        preflight_still_tiled_issue_summary="",
        preflight_still_tiled_warning_summary="",
        preflight_video_issue_summary="",
        preflight_video_warning_summary="",
        preflight_issue_summary="",
        preflight_warning_summary="",
        status_message="",
        last_error="",
        render_mode="Still",
        tiles_x=2,
        tiles_y=2,
        tile_overlap_px=8,
        video_frame_rate=24,
        video_constant_rate_factor=23,
        active_job_id="",
        active_job_status="",
        active_job_script_name="",
        active_job_progress="",
        active_job_error="",
        active_job_result_blob_id="",
        active_job_result_blob_count=0,
        active_job_is_completed=False,
        current_blend_path="C:/Workspace/test.blend",
        current_blend_file_exists=True,
        current_blend_is_dirty=False,
    )


def _create_context(state: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        scene=SimpleNamespace(frame_start=1, frame_end=3),
        window=None,
        window_manager=SimpleNamespace(
            outwit_bridge_state=state,
            event_timer_add=lambda *args, **kwargs: object(),
            event_timer_remove=lambda timer: None,
            modal_handler_add=lambda operator: None,
        ),
        preferences=SimpleNamespace(addons={PACKAGE_NAME: SimpleNamespace(preferences=SimpleNamespace(bridge_context_directory="context-dir"))}),
    )


def _run_launch_operator(operator, context):
    """Drive the launch operator like Blender does: execute() may defer the fast tail to a modal
    TIMER tick (instant-feedback repaint) — pump modal until a terminal result."""
    result = operator.execute(context)
    guard = 0
    while "RUNNING_MODAL" in result:
        guard += 1
        assert guard < 10, "launch operator did not terminate"
        result = operator.modal(context, SimpleNamespace(type="TIMER"))
    return result


def _create_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validated with warnings.",
        is_valid=True,
        issues=[],
        warnings=["Scene uses external image asset 'Texture' from '/tmp/texture.png'."],
    )


def _create_clean_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validated successfully.",
        is_valid=True,
        issues=[],
        warnings=[],
    )


def _create_cache_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validated with warnings.",
        is_valid=True,
        issues=[],
        warnings=["Scene uses external cache file 'SimCache' from '/tmp/sim.abc'. Ensure this cache remains portable for remote rendering."],
    )


def _create_simulation_issue_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validation failed.",
        is_valid=False,
        issues=["Fluid domain 'Domain' uses external cache directory '/tmp/cache', which is not portable to remote nodes in the current v1 flow."],
        warnings=[],
    )


def _create_baked_simulation_issue_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validation failed.",
        is_valid=False,
        issues=["Fluid domain 'Domain' requires baked simulation data before remote rendering."],
        warnings=[],
    )


def _create_baked_mesh_cache_issue_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validation failed.",
        is_valid=False,
        issues=["Fluid domain 'Domain' requires baked mesh cache before remote rendering."],
        warnings=[],
    )


def _create_cloth_simulation_issue_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validation failed.",
        is_valid=False,
        issues=["Cloth simulation 'Pillow' is not yet portable to remote rendering in the current v1 flow."],
        warnings=[],
    )


def _create_particle_simulation_issue_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validation failed.",
        is_valid=False,
        issues=["Particle simulation 'Emitter' is not yet portable to remote rendering in the current v1 flow."],
        warnings=[],
    )


def _create_geometry_cache_issue_validate_response() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job-1",
        status="Completed",
        message="Blend validation failed.",
        is_valid=False,
        issues=["Geometry cache 'AlembicCharacter' is not yet portable to remote rendering in the current v1 flow."],
        warnings=[],
    )


def _create_ready_preflight_response() -> SimpleNamespace:
    return SimpleNamespace(
        status="Completed",
        message="Render preflight completed successfully.",
        result=SimpleNamespace(
            can_render_all=True,
            still=SimpleNamespace(can_render=True, issues=[], warnings=[]),
            frames=SimpleNamespace(can_render=True, issues=[], warnings=[]),
            still_tiled=SimpleNamespace(can_render=True, issues=[], warnings=[]),
            video=SimpleNamespace(can_render=True, issues=[], warnings=[]),
        ),
    )


class BridgeOperatorPolicyTests(unittest.TestCase):
    def test_scene_requires_upload_reuploads_after_a_saved_edit(self) -> None:
        # Regression: adding a camera (or any edit) + saving must re-upload even when the path and the
        # output-settings signature are unchanged — tracked via the .blend's modification time.
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".blend")
        os.close(fd)
        try:
            signature = "PNG|RGBA|8|O||"
            state = _create_state()
            state.uploaded_source_path = path
            state.uploaded_output_signature = signature
            state.uploaded_source_mtime = bridge_operators._blend_file_mtime(path)

            # Same file, same settings → cached (no re-upload).
            self.assertFalse(_REAL_SCENE_REQUIRES_UPLOAD(state, path, signature))

            # Re-save advances mtime → must re-upload despite identical path + signature.
            os.utime(path, (123456789, 123456789))
            self.assertTrue(_REAL_SCENE_REQUIRES_UPLOAD(state, path, signature))
        finally:
            os.remove(path)

    def test_upload_operator_reports_packed_upload_message(self) -> None:
        state = _create_state()
        context = _create_context(state)

        bridge_operators._upload_current_blend = lambda _context: SimpleNamespace(
            uploaded=True,
            blob_id="blob-2",
            file_name="scene.blend",
            file_size=123,
            message="Blend uploaded from a packed temporary copy with Blender-packable dependencies included.",
        )

        operator = bridge_operators.OUTWIT_OT_bridge_upload_blend()
        result = operator.execute(context)

        self.assertEqual({"FINISHED"}, result)
        self.assertEqual("Blend uploaded.", state.status_message)
        self.assertIn(({"INFO"}, "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."), operator.report_calls)

    def test_upload_current_blend_prefers_packed_upload_copy_when_available(self) -> None:
        state = _create_state()
        context = _create_context(state)
        uploaded_paths: list[str] = []

        class PackedCopyContext:
            def __enter__(self):
                return "C:/Temp/packed-scene.blend", "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."

            def __exit__(self, exc_type, exc, tb):
                return False

        class FakeClient:
            def upload_blend(self, path):
                uploaded_paths.append(path)
                return SimpleNamespace(uploaded=True, blob_id="blob-2", file_name=path.split("/")[-1], file_size=123, message="")

            def upload_file(self, path):
                raise AssertionError(f"Did not expect separate attachment upload in this packed-copy test: {path}")

        bridge_operators._get_bridge_client = lambda _context: FakeClient()
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators.collect_scene_attachment_metadata = lambda: []
        bridge_operators.create_packed_upload_copy = lambda _path: PackedCopyContext()

        response = bridge_operators._upload_current_blend(context)

        self.assertTrue(response.uploaded)
        self.assertEqual(["C:/Temp/packed-scene.blend"], uploaded_paths)
        self.assertIn("packed temporary copy", state.upload_message)

    def test_upload_current_blend_falls_back_to_original_when_packing_is_unavailable(self) -> None:
        state = _create_state()
        context = _create_context(state)
        uploaded_paths: list[str] = []

        class FakeClient:
            def upload_blend(self, path):
                uploaded_paths.append(path)
                return SimpleNamespace(uploaded=True, blob_id="blob-2", file_name=path.split("/")[-1], file_size=123, message="Blend uploaded successfully.")

            def upload_file(self, path):
                raise AssertionError(f"Did not expect separate attachment upload in fallback test: {path}")

        class FakeScenePackagingError(Exception):
            pass

        bridge_operators._get_bridge_client = lambda _context: FakeClient()
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators.collect_scene_attachment_metadata = lambda: []
        bridge_operators.ScenePackagingError = FakeScenePackagingError
        bridge_operators.create_packed_upload_copy = lambda _path: (_ for _ in ()).throw(FakeScenePackagingError("packing unavailable"))

        response = bridge_operators._upload_current_blend(context)

        self.assertTrue(response.uploaded)
        self.assertEqual(["C:/Workspace/test.blend"], uploaded_paths)
        self.assertEqual("Blend uploaded successfully.", state.upload_message)

    def test_upload_current_blend_uploads_scene_attachment_blob_metadata(self) -> None:
        state = _create_state()
        context = _create_context(state)
        uploaded_blend_paths: list[str] = []
        uploaded_attachment_paths: list[str] = []

        class FakeClient:
            def upload_blend(self, path):
                uploaded_blend_paths.append(path)
                return SimpleNamespace(uploaded=True, blob_id="blob-2", file_name=path.split("/")[-1], file_size=123, message="")

            def upload_file(self, path):
                uploaded_attachment_paths.append(path)
                return SimpleNamespace(uploaded=True, blob_id="attachment-blob-1", file_name=path.split("/")[-1], file_size=42, message="File uploaded successfully.")

        bridge_operators._get_bridge_client = lambda _context: FakeClient()
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators.collect_scene_attachment_metadata = lambda: [
            {
                "Kind": "Font",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Fonts/Brand.ttf",
                "RelativePath": "deps/fonts/Brand.ttf",
                "PackagingStrategy": "SceneAttachmentBlob",
            }
        ]

        class PackedCopyContext:
            def __enter__(self):
                return "C:/Temp/packed-scene.blend", "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."

            def __exit__(self, exc_type, exc, tb):
                return False

        bridge_operators.create_packed_upload_copy = lambda _path: PackedCopyContext()

        response = bridge_operators._upload_current_blend(context)

        self.assertTrue(response.uploaded)
        self.assertEqual(["C:/Assets/Fonts/Brand.ttf"], uploaded_attachment_paths)
        self.assertEqual(["C:/Temp/packed-scene.blend"], uploaded_blend_paths)
        self.assertIn("attachment-blob-1", state.uploaded_attachment_manifest_json)

    def test_upload_current_blend_populates_dependency_plan_summary(self) -> None:
        state = _create_state()
        context = _create_context(state)

        class FakeClient:
            def upload_blend(self, path):
                return SimpleNamespace(uploaded=True, blob_id="blob-2", file_name=path.split("/")[-1], file_size=123, message="")

            def upload_file(self, path):
                return SimpleNamespace(uploaded=True, blob_id=f"blob-{path.split('/')[-1]}", file_name=path.split("/")[-1], file_size=42, message="")

        bridge_operators._get_bridge_client = lambda _context: FakeClient()
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators.collect_scene_attachment_metadata = lambda: [
            {
                "Kind": "ImageAsset",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Textures/texture.png",
                "RelativePath": "deps/images/texture.png",
                "PackagingStrategy": "PackedBlendCopy",
            },
            {
                "Kind": "Font",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Fonts/Brand.ttf",
                "RelativePath": "deps/fonts/Brand.ttf",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
        ]
        bridge_operators.summarize_scene_attachment_metadata = lambda _attachments: {
            "TotalCount": 2,
            "CountSummary": "Fonts × 1 | Image assets × 1",
            "PackedCount": 1,
            "PackedSummary": "Image assets × 1",
            "AttachmentCount": 1,
            "AttachmentSummary": "Fonts × 1",
        }

        class PackedCopyContext:
            def __enter__(self):
                return "C:/Temp/packed-scene.blend", "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."

            def __exit__(self, exc_type, exc, tb):
                return False

        bridge_operators.create_packed_upload_copy = lambda _path: PackedCopyContext()

        response = bridge_operators._upload_current_blend(context)

        self.assertTrue(response.uploaded)
        self.assertEqual(2, state.dependency_plan_total_count)
        self.assertEqual(1, state.dependency_plan_packed_count)
        self.assertEqual(1, state.dependency_plan_attachment_count)
        self.assertIn("Image assets × 1", state.dependency_plan_packed_summary)
        self.assertIn("Fonts × 1", state.dependency_plan_attachment_summary)

    def test_upload_current_blend_uploads_media_scene_attachment_blob_metadata(self) -> None:
        state = _create_state()
        context = _create_context(state)
        uploaded_attachment_paths: list[str] = []

        class FakeClient:
            def upload_blend(self, path):
                return SimpleNamespace(uploaded=True, blob_id="blob-2", file_name=path.split("/")[-1], file_size=123, message="")

            def upload_file(self, path):
                uploaded_attachment_paths.append(path)
                return SimpleNamespace(uploaded=True, blob_id=f"blob-{len(uploaded_attachment_paths)}", file_name=path.split("/")[-1], file_size=42, message="File uploaded successfully.")

        bridge_operators._get_bridge_client = lambda _context: FakeClient()
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators.collect_scene_attachment_metadata = lambda: [
            {
                "Kind": "Sound",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Audio/shot.wav",
                "RelativePath": "deps/sounds/shot.wav",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
            {
                "Kind": "MovieClip",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Clips/clip.png",
                "RelativePath": "deps/movie-clips/clip.png",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
            {
                "Kind": "VseMovieStrip",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Vse/strip.mp4",
                "RelativePath": "deps/vse/movie-strips/Strip/strip.mp4",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
        ]

        class PackedCopyContext:
            def __enter__(self):
                return "C:/Temp/packed-scene.blend", "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."

            def __exit__(self, exc_type, exc, tb):
                return False

        bridge_operators.create_packed_upload_copy = lambda _path: PackedCopyContext()

        response = bridge_operators._upload_current_blend(context)

        self.assertTrue(response.uploaded)
        self.assertEqual(
            [
                "C:/Assets/Audio/shot.wav",
                "C:/Assets/Clips/clip.png",
                "C:/Assets/Vse/strip.mp4",
            ],
            uploaded_attachment_paths,
        )
        self.assertIn("deps/sounds/shot.wav", state.uploaded_attachment_manifest_json)
        self.assertIn("deps/movie-clips/clip.png", state.uploaded_attachment_manifest_json)
        self.assertIn("deps/vse/movie-strips/Strip/strip.mp4", state.uploaded_attachment_manifest_json)

    def test_upload_current_blend_uploads_linked_library_and_volume_scene_attachment_blob_metadata(self) -> None:
        state = _create_state()
        context = _create_context(state)
        uploaded_attachment_paths: list[str] = []

        class FakeClient:
            def upload_blend(self, path):
                return SimpleNamespace(uploaded=True, blob_id="blob-2", file_name=path.split("/")[-1], file_size=123, message="")

            def upload_file(self, path):
                uploaded_attachment_paths.append(path)
                return SimpleNamespace(uploaded=True, blob_id=f"blob-{len(uploaded_attachment_paths)}", file_name=path.split("/")[-1], file_size=42, message="File uploaded successfully.")

        bridge_operators._get_bridge_client = lambda _context: FakeClient()
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators.collect_scene_attachment_metadata = lambda: [
            {
                "Kind": "LinkedLibrary",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Libraries/library.blend",
                "RelativePath": "deps/linked-libraries/library.blend",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
            {
                "Kind": "Volume",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Volumes/cloud.vdb",
                "RelativePath": "deps/volumes/cloud.vdb",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
        ]

        class PackedCopyContext:
            def __enter__(self):
                return "C:/Temp/packed-scene.blend", "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."

            def __exit__(self, exc_type, exc, tb):
                return False

        bridge_operators.create_packed_upload_copy = lambda _path: PackedCopyContext()

        response = bridge_operators._upload_current_blend(context)

        self.assertTrue(response.uploaded)
        self.assertEqual(
            [
                "C:/Assets/Libraries/library.blend",
                "C:/Assets/Volumes/cloud.vdb",
            ],
            uploaded_attachment_paths,
        )
        self.assertIn("deps/linked-libraries/library.blend", state.uploaded_attachment_manifest_json)
        self.assertIn("deps/volumes/cloud.vdb", state.uploaded_attachment_manifest_json)

    def test_upload_current_blend_uploads_image_sequence_scene_attachment_blob_metadata(self) -> None:
        state = _create_state()
        context = _create_context(state)
        uploaded_attachment_paths: list[str] = []

        class FakeClient:
            def upload_blend(self, path):
                return SimpleNamespace(uploaded=True, blob_id="blob-2", file_name=path.split("/")[-1], file_size=123, message="")

            def upload_file(self, path):
                uploaded_attachment_paths.append(path)
                return SimpleNamespace(uploaded=True, blob_id=f"blob-{len(uploaded_attachment_paths)}", file_name=path.split("/")[-1], file_size=42, message="File uploaded successfully.")

        bridge_operators._get_bridge_client = lambda _context: FakeClient()
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators.collect_scene_attachment_metadata = lambda: [
            {
                "Kind": "ImageSequenceFrame",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Sequence/plate_0001.png",
                "RelativePath": "deps/image-sequences/Plate/plate_0001.png",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
            {
                "Kind": "ImageSequenceFrame",
                "BlobId": "",
                "OriginalPath": "C:/Assets/Sequence/plate_0002.png",
                "RelativePath": "deps/image-sequences/Plate/plate_0002.png",
                "PackagingStrategy": "SceneAttachmentBlob",
            },
        ]

        class PackedCopyContext:
            def __enter__(self):
                return "C:/Temp/packed-scene.blend", "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."

            def __exit__(self, exc_type, exc, tb):
                return False

        bridge_operators.create_packed_upload_copy = lambda _path: PackedCopyContext()

        response = bridge_operators._upload_current_blend(context)

        self.assertTrue(response.uploaded)
        self.assertEqual(
            [
                "C:/Assets/Sequence/plate_0001.png",
                "C:/Assets/Sequence/plate_0002.png",
            ],
            uploaded_attachment_paths,
        )
        self.assertIn("deps/image-sequences/Plate/plate_0001.png", state.uploaded_attachment_manifest_json)
        self.assertIn("deps/image-sequences/Plate/plate_0002.png", state.uploaded_attachment_manifest_json)

    def test_validate_operator_surfaces_dependency_policy_block_message(self) -> None:
        state = _create_state()
        context = _create_context(state)
        response = _create_validate_response()

        # Modern launch flow (0.2.0+): execute() validates the blend path and the upload-cache key
        # itself, then runs the fast tail synchronously when no upload is needed.
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)

        operator = bridge_operators.OUTWIT_OT_bridge_validate_blend()
        result = operator.execute(context)

        self.assertEqual({"FINISHED"}, result)
        self.assertIn("Current v1 policy blocks scenes with unresolved external dependencies", state.status_message)
        self.assertIn(({"ERROR"}, state.status_message), operator.report_calls)

    def test_validate_operator_surfaces_cache_specific_policy_block_message(self) -> None:
        state = _create_state()
        context = _create_context(state)
        response = _create_cache_validate_response()

        # Modern launch flow (0.2.0+): execute() validates the blend path and the upload-cache key
        # itself, then runs the fast tail synchronously when no upload is needed.
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)

        operator = bridge_operators.OUTWIT_OT_bridge_validate_blend()
        result = operator.execute(context)

        self.assertEqual({"FINISHED"}, result)
        self.assertIn("unresolved external cache dependencies", state.status_message)
        self.assertIn(({"ERROR"}, state.status_message), operator.report_calls)







    def test_preflight_operator_blocks_on_external_dependency_warning(self) -> None:
        state = _create_state()
        context = _create_context(state)
        response = _create_validate_response()

        bridge_operators._get_bridge_client = lambda _context: object()
        # Modern launch flow (0.2.0+): execute() validates the blend path and the upload-cache key
        # itself, then runs the fast tail synchronously when no upload is needed.
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False

        def run_validate_blend(_context):
            bridge_operators._apply_validate_response(state, response)
            return response

        bridge_operators._run_validate_blend = run_validate_blend

        operator = bridge_operators.OUTWIT_OT_bridge_run_preflight()
        result = operator.execute(context)

        self.assertEqual({"CANCELLED"}, result)
        self.assertFalse(state.preflight_can_render_all)
        self.assertIn("Current v1 policy blocks scenes with unresolved external dependencies", state.preflight_issue_summary)
        self.assertIn(({"ERROR"}, state.preflight_issue_summary), operator.report_calls)

    def test_preflight_operator_blocks_on_external_cache_warning_with_cache_specific_message(self) -> None:
        state = _create_state()
        context = _create_context(state)
        response = _create_cache_validate_response()

        bridge_operators._get_bridge_client = lambda _context: object()
        # Modern launch flow (0.2.0+): execute() validates the blend path and the upload-cache key
        # itself, then runs the fast tail synchronously when no upload is needed.
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False

        def run_validate_blend(_context):
            bridge_operators._apply_validate_response(state, response)
            return response

        bridge_operators._run_validate_blend = run_validate_blend

        operator = bridge_operators.OUTWIT_OT_bridge_run_preflight()
        result = operator.execute(context)

        self.assertEqual({"CANCELLED"}, result)
        self.assertFalse(state.preflight_can_render_all)
        self.assertIn("unresolved external cache dependencies", state.preflight_issue_summary)
        self.assertIn(({"ERROR"}, state.preflight_issue_summary), operator.report_calls)

    def test_preflight_operator_allows_clean_validation_after_packed_upload_path(self) -> None:
        state = _create_state()
        context = _create_context(state)
        validate_response = _create_clean_validate_response()
        preflight_response = _create_ready_preflight_response()

        bridge_operators._ensure_current_scene_uploaded = lambda _context: SimpleNamespace(
            uploaded=True,
            blob_id="blob-2",
            file_name="scene.blend",
            file_size=123,
            message="Blend uploaded from a packed temporary copy with Blender-packable dependencies included.",
        )

        def run_validate_blend(_context):
            bridge_operators._apply_validate_response(state, validate_response)
            return validate_response

        def run_preflight(_context):
            bridge_operators._apply_preflight_response(state, preflight_response)
            return preflight_response

        bridge_operators._run_validate_blend = run_validate_blend
        bridge_operators._run_preflight = run_preflight

        operator = bridge_operators.OUTWIT_OT_bridge_run_preflight()
        result = operator.execute(context)

        self.assertEqual({"FINISHED"}, result)
        self.assertTrue(state.preflight_can_render_all)
        self.assertTrue(state.preflight_still_ready)
        self.assertEqual("Still render ready.", state.status_message)
        self.assertIn(({"INFO"}, "Still render ready."), operator.report_calls)






    def test_launch_operator_blocks_on_external_dependency_warning(self) -> None:
        state = _create_state()
        context = _create_context(state)
        response = _create_validate_response()

        # Modern launch flow (0.2.0+): execute() validates the blend path and the upload-cache key
        # itself, then runs the fast tail synchronously when no upload is needed.
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False

        def run_validate_blend(_context):
            bridge_operators._apply_validate_response(state, response)
            return response

        bridge_operators._run_validate_blend = run_validate_blend

        operator = bridge_operators.OUTWIT_OT_bridge_launch_render()
        result = _run_launch_operator(operator, context)

        self.assertEqual({"CANCELLED"}, result)
        self.assertIn("Current v1 policy blocks scenes with unresolved external dependencies", state.status_message)
        self.assertIn(({"ERROR"}, state.status_message), operator.report_calls)

    def test_launch_operator_blocks_on_external_cache_warning_with_cache_specific_message(self) -> None:
        state = _create_state()
        context = _create_context(state)
        response = _create_cache_validate_response()

        # Modern launch flow (0.2.0+): execute() validates the blend path and the upload-cache key
        # itself, then runs the fast tail synchronously when no upload is needed.
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False

        def run_validate_blend(_context):
            bridge_operators._apply_validate_response(state, response)
            return response

        bridge_operators._run_validate_blend = run_validate_blend

        operator = bridge_operators.OUTWIT_OT_bridge_launch_render()
        result = _run_launch_operator(operator, context)

        self.assertEqual({"CANCELLED"}, result)
        self.assertIn("unresolved external cache dependencies", state.status_message)
        self.assertIn(({"ERROR"}, state.status_message), operator.report_calls)

    def test_launch_operator_succeeds_when_validation_is_clean_after_packed_upload_path(self) -> None:
        state = _create_state()
        context = _create_context(state)
        validate_response = _create_clean_validate_response()
        preflight_response = _create_ready_preflight_response()
        launch_response = SimpleNamespace(job_id="job-2", status="Completed", message="RenderStill launched successfully.")

        # Modern launch flow (0.2.0+): execute() validates the blend path and the upload-cache key
        # itself, then runs the fast tail synchronously when no upload is needed.
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False

        def run_validate_blend(_context):
            bridge_operators._apply_validate_response(state, validate_response)
            return validate_response

        def run_preflight(_context):
            bridge_operators._apply_preflight_response(state, preflight_response)
            return preflight_response

        bridge_operators._run_validate_blend = run_validate_blend
        bridge_operators._run_preflight = run_preflight
        bridge_operators._run_selected_launch = lambda _context: launch_response

        operator = bridge_operators.OUTWIT_OT_bridge_launch_render()
        result = _run_launch_operator(operator, context)

        self.assertEqual({"FINISHED"}, result)
        self.assertEqual("Still render launched.", state.status_message)
        self.assertIn(({"INFO"}, "RenderStill launched successfully."), operator.report_calls)







    # --- Simulation bake plan (delegated bakes; local blocks until its driver ships) -----------------
    # Per-kind recognition (fluid/cloth/particle/…) is covered in bridge_dependency_policy_tests;
    # these verify the OPERATOR flow routes by bake plan, not by kind.

    def test_validate_operator_reports_delegated_bake_for_simulation(self) -> None:
        state = _create_state()
        context = _create_context(state)
        response = _create_simulation_issue_validate_response()

        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)

        operator = bridge_operators.OUTWIT_OT_bridge_validate_blend()
        result = operator.execute(context)

        self.assertEqual({"FINISHED"}, result)
        self.assertIn("baked on the render farm", state.status_message)
        self.assertIn(({"INFO"}, state.status_message), operator.report_calls)

    def test_validate_operator_blocks_simulation_when_local_bake_unavailable(self) -> None:
        state = _create_state()
        state.bake_strategy = "LOCAL"
        context = _create_context(state)
        response = _create_simulation_issue_validate_response()

        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)

        operator = bridge_operators.OUTWIT_OT_bridge_validate_blend()
        result = operator.execute(context)

        self.assertEqual({"FINISHED"}, result)
        self.assertIn("render farm", state.status_message)
        self.assertIn(({"ERROR"}, state.status_message), operator.report_calls)

    def test_preflight_operator_skips_when_simulation_is_delegated_bake(self) -> None:
        # A simulation covered by a delegated bake is not preflighted on the unbaked scene; the
        # operator reports informationally and leaves the per-mode verdicts unset (Not checked).
        state = _create_state()
        context = _create_context(state)
        response = _create_simulation_issue_validate_response()

        bridge_operators._get_bridge_client = lambda _context: object()
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)

        operator = bridge_operators.OUTWIT_OT_bridge_run_preflight()
        result = operator.execute(context)

        self.assertEqual({"FINISHED"}, result)
        self.assertIn("baked on the render farm", state.status_message)
        self.assertFalse(state.preflight_still_ready)
        self.assertIn(({"INFO"}, state.status_message), operator.report_calls)

    def test_preflight_operator_blocks_simulation_when_local_bake_unavailable(self) -> None:
        state = _create_state()
        state.bake_strategy = "LOCAL"
        context = _create_context(state)
        response = _create_simulation_issue_validate_response()

        bridge_operators._get_bridge_client = lambda _context: object()
        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)

        operator = bridge_operators.OUTWIT_OT_bridge_run_preflight()
        result = operator.execute(context)

        self.assertEqual({"CANCELLED"}, result)
        self.assertFalse(state.preflight_can_render_all)
        self.assertIn("render farm", state.preflight_issue_summary)
        self.assertIn(({"ERROR"}, state.preflight_issue_summary), operator.report_calls)

    def test_launch_operator_routes_unbaked_simulation_to_delegated_bake(self) -> None:
        # The crux: an unbaked simulation with DELEGATED must NOT block and must NOT reach a plain
        # Render* script — it routes to the BakeAndRender* path (bake=True), skipping the plain-scene
        # preflight (which would re-flag the very simulation being baked).
        state = _create_state()
        context = _create_context(state)
        response = _create_simulation_issue_validate_response()
        launch_response = SimpleNamespace(job_id="job-9", status="Pending", message="BakeAndRenderStill launched successfully.")
        captured = {}

        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)

        def run_preflight(_context):
            raise AssertionError("preflight must be skipped on the delegated-bake path")

        def run_selected_launch(_context, *, bake=False):
            captured["bake"] = bake
            return launch_response

        bridge_operators._run_preflight = run_preflight
        bridge_operators._run_selected_launch = run_selected_launch
        bridge_operators._sticky_render_settings_after_submit = lambda _context: None

        operator = bridge_operators.OUTWIT_OT_bridge_launch_render()
        result = _run_launch_operator(operator, context)

        self.assertEqual({"FINISHED"}, result)
        self.assertTrue(captured.get("bake"), "launch must route to the BakeAndRender* path")
        self.assertIn(({"INFO"}, "BakeAndRenderStill launched successfully."), operator.report_calls)

    def test_launch_operator_blocks_simulation_when_local_bake_unavailable(self) -> None:
        # LOCAL baking is not available yet, so the launch must refuse rather than silently delegate
        # or render unbaked — the gate the user required ("no render without a bake plan").
        state = _create_state()
        state.bake_strategy = "LOCAL"
        context = _create_context(state)
        response = _create_simulation_issue_validate_response()

        bridge_operators._ensure_current_scene_uploaded = lambda _context: None
        bridge_operators._get_current_blend_path = lambda: "C:/Workspace/test.blend"
        bridge_operators._scene_requires_upload = lambda *_args: False
        bridge_operators._run_validate_blend = lambda _context: (bridge_operators._apply_validate_response(state, response) or response)
        bridge_operators._run_selected_launch = lambda _context, *, bake=False: (_ for _ in ()).throw(AssertionError("must not submit when blocked"))

        operator = bridge_operators.OUTWIT_OT_bridge_launch_render()
        result = _run_launch_operator(operator, context)

        self.assertEqual({"CANCELLED"}, result)
        self.assertIn("render farm", state.status_message)
        self.assertIn(({"ERROR"}, state.status_message), operator.report_calls)


if __name__ == "__main__":
    unittest.main()
