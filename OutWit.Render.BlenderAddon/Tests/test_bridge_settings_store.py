"""The AddonPreferences-backed render settings store: defaults, round trip, one-time
migration of the embedded-era render-settings.json, and clamping of corrupt values.

bpy is stubbed; the preferences object is a plain namespace with the same attributes the
real OutWitBridgeAddonPreferences declares (defaults mirrored from the property defaults).

Run: python -m unittest Tests.test_bridge_settings_store
"""
from __future__ import annotations

import importlib
import json
import pathlib
import sys
import tempfile
import types
import unittest

ADDON_DIR = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge"
PACKAGE_NAME = "owrb_settings_store_test"


def _bootstrap_package():
    if PACKAGE_NAME in sys.modules:
        return
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(ADDON_DIR)]
    sys.modules[PACKAGE_NAME] = package


_bootstrap_package()
store = importlib.import_module(f"{PACKAGE_NAME}.bridge_settings_store")
bridge_models = importlib.import_module(f"{PACKAGE_NAME}.bridge_models")


class FakePreferences(types.SimpleNamespace):
    """The property defaults of OutWitBridgeAddonPreferences, as plain attributes."""

    def __init__(self):
        super().__init__(
            remember_render_settings=True,
            render_settings_version=0,
            rs_split_frame=False,
            rs_tiles_x=2,
            rs_tiles_y=2,
            rs_tile_overlap=8,
            rs_anim_result="Sequence",
            rs_video_container="",
            rs_video_codec="",
            rs_video_crf=23,
            rs_last_target_id="",
            rs_last_target_name="",
            rs_bake_strategy="DELEGATED",
        )


class FakeContext:
    def __init__(self, prefs):
        addon = types.SimpleNamespace(preferences=prefs)
        # The store resolves preferences by its own package name (__package__).
        self.preferences = types.SimpleNamespace(addons={store.__package__: addon}, is_dirty=False)


def _context() -> tuple[FakeContext, FakePreferences]:
    prefs = FakePreferences()
    return FakeContext(prefs), prefs


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        # No legacy file unless a test plants one.
        self._legacy_dir = tempfile.TemporaryDirectory()
        self._original = store._legacy_json_path
        store._legacy_json_path = lambda: str(pathlib.Path(self._legacy_dir.name) / "render-settings.json")

    def tearDown(self):
        store._legacy_json_path = self._original
        self._legacy_dir.cleanup()

    def _plant_legacy(self, payload: dict) -> None:
        path = pathlib.Path(store._legacy_json_path())
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_fresh_load_returns_the_historical_defaults(self):
        context, prefs = _context()
        settings = store.load_render_settings(context)
        self.assertEqual(
            (settings.remember_render_settings, settings.split_frame, settings.tiles_x,
             settings.tiles_y, settings.tile_overlap, settings.anim_result, settings.video_crf,
             settings.bake_strategy),
            (True, False, 2, 2, 8, "Sequence", 23, "DELEGATED"))
        self.assertEqual(prefs.render_settings_version, 1, "a fresh store is stamped current")

    def test_save_and_load_round_trip(self):
        context, prefs = _context()
        settings = bridge_models.RenderSettingsResponse(
            split_frame=True, tiles_x=4, tiles_y=3, tile_overlap=16, anim_result="Video",
            video_container="WEBM", video_codec="VP9", video_crf=18,
            last_group_id="g:11111111-1111-1111-1111-111111111111", last_group_name="Render Group",
            bake_strategy="LOCAL")
        store.save_render_settings(context, settings.to_payload())
        loaded = store.load_render_settings(context)
        self.assertEqual(loaded, settings)
        self.assertTrue(context.preferences.is_dirty, "Blender is asked to save the preferences")

    def test_legacy_json_migrates_once_and_wins_over_defaults(self):
        context, prefs = _context()
        self._plant_legacy({
            "RememberRenderSettings": True, "SplitFrame": True, "TilesX": 4, "TilesY": 4,
            "TileOverlap": 8, "AnimResult": "Sequence", "VideoContainer": "MP4",
            "VideoCodec": "H264", "VideoCrf": 23,
            "LastGroupId": "g:c442626d-3f90-4d18-bd14-16034375ccc2",
            "LastGroupName": "Render Group", "BakeStrategy": "DELEGATED",
        })
        loaded = store.load_render_settings(context)
        self.assertEqual((loaded.tiles_x, loaded.last_group_name), (4, "Render Group"))
        self.assertEqual(prefs.render_settings_version, 1)

        # A later legacy edit is ignored: the preferences are authoritative now.
        self._plant_legacy({"TilesX": 9})
        self.assertEqual(store.load_render_settings(context).tiles_x, 4)

    def test_corrupt_values_are_clamped_on_save(self):
        context, prefs = _context()
        store.save_render_settings(context, {"TilesX": 0, "TileOverlap": -5, "VideoCrf": 99})
        loaded = store.load_render_settings(context)
        self.assertEqual((loaded.tiles_x, loaded.tile_overlap, loaded.video_crf), (1, 0, 51))

    def test_unreadable_legacy_file_falls_back_to_defaults(self):
        context, prefs = _context()
        path = pathlib.Path(store._legacy_json_path())
        path.write_text("{not json", encoding="utf-8")
        settings = store.load_render_settings(context)
        self.assertEqual(settings.tiles_x, 2)
        self.assertEqual(prefs.render_settings_version, 1)


if __name__ == "__main__":
    unittest.main()
