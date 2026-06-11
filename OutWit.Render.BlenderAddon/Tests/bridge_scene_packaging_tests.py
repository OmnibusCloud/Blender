from __future__ import annotations

import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace


ADDON_DIR = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"
PACKAGE_NAME = "outwit_render_bridge"


def _load_bridge_scene_packaging_module(binary_path: str):
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ADDON_DIR)]
    sys.modules[PACKAGE_NAME] = package

    bpy_module = types.ModuleType("bpy")
    bpy_module.app = SimpleNamespace(binary_path=binary_path)
    sys.modules["bpy"] = bpy_module

    module_spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.bridge_scene_packaging",
        ADDON_DIR / "bridge_scene_packaging.py",
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("Failed to load bridge_scene_packaging.py")

    module = importlib.util.module_from_spec(module_spec)
    sys.modules[f"{PACKAGE_NAME}.bridge_scene_packaging"] = module
    module_spec.loader.exec_module(module)
    return module


class BridgeScenePackagingTests(unittest.TestCase):
    def test_create_packed_upload_copy_returns_temporary_blend_copy_when_subprocess_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            source_blend = pathlib.Path(temp_directory) / "scene.blend"
            source_blend.write_bytes(b"blend-data")
            fake_blender = pathlib.Path(temp_directory) / "blender.exe"
            fake_blender.write_text("binary", encoding="utf-8")

            module = _load_bridge_scene_packaging_module(str(fake_blender))
            module.subprocess.run = lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr="")

            with module.create_packed_upload_copy(str(source_blend)) as (packed_path, message):
                self.assertTrue(pathlib.Path(packed_path).is_file())
                self.assertEqual(b"blend-data", pathlib.Path(packed_path).read_bytes())
                self.assertIn("packed temporary copy", message)

    def test_create_packed_upload_copy_raises_when_packing_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            source_blend = pathlib.Path(temp_directory) / "scene.blend"
            source_blend.write_bytes(b"blend-data")
            fake_blender = pathlib.Path(temp_directory) / "blender.exe"
            fake_blender.write_text("binary", encoding="utf-8")

            module = _load_bridge_scene_packaging_module(str(fake_blender))
            module.subprocess.run = lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="pack failed", stderr="boom")

            with self.assertRaises(module.ScenePackagingError):
                with module.create_packed_upload_copy(str(source_blend)):
                    self.fail("Expected ScenePackagingError before yielding a packed copy.")


class SceneOutputSignatureTests(unittest.TestCase):
    """The upload-cache key half of Phase 5 D: a change in any Output Properties facet that travels
    inside the .blend must produce a different signature → force a re-upload."""

    @staticmethod
    def _scene(file_format="PNG", color_mode="RGBA", color_depth="8",
               film_transparent=False, ffmpeg_format="", ffmpeg_codec=""):
        return SimpleNamespace(render=SimpleNamespace(
            image_settings=SimpleNamespace(
                file_format=file_format, color_mode=color_mode, color_depth=color_depth),
            film_transparent=film_transparent,
            ffmpeg=SimpleNamespace(format=ffmpeg_format, codec=ffmpeg_codec),
        ))

    def test_same_output_settings_produce_stable_signature(self) -> None:
        module = _load_bridge_scene_packaging_module("")

        self.assertEqual(
            module.scene_output_signature(self._scene()),
            module.scene_output_signature(self._scene()),
        )

    def test_each_output_facet_changes_the_signature(self) -> None:
        module = _load_bridge_scene_packaging_module("")
        base = module.scene_output_signature(self._scene())

        variants = [
            self._scene(file_format="OPEN_EXR"),
            self._scene(color_mode="RGB"),
            self._scene(color_depth="16"),
            self._scene(film_transparent=True),
            self._scene(ffmpeg_format="MPEG4"),
            self._scene(ffmpeg_codec="H264"),
        ]

        for variant in variants:
            self.assertNotEqual(base, module.scene_output_signature(variant))

    def test_missing_render_attributes_do_not_raise(self) -> None:
        module = _load_bridge_scene_packaging_module("")

        self.assertIsInstance(module.scene_output_signature(SimpleNamespace()), str)


if __name__ == "__main__":
    unittest.main()
