"""Headless unit tests for the Phase 5 render-settings logic (seed/sticky decisions).

bridge_render_settings is bpy-free by design — its only import is the bpy-free bridge_models —
so the whole seed/sticky decision surface (what to apply on connect, how the remembered target
resolves against the current scope, how the sticky write is composed) loads and runs WITHOUT
Blender. The thin appliers that touch bpy live in bridge_operators and are not under test here.

Run: python -m unittest discover -s Tests -p "test_*.py" (from OutWit.Render.BlenderAddon).
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import types
import unittest

_PKG = "owrb_render_settings_test"


def _exec_module(spec, module) -> None:
    """exec the module, shimming dataclass(slots=True) away on Python < 3.10.

    bridge_models targets Blender's bundled Python (3.11+, slots supported); the headless test
    interpreter may be older. Dropping `slots` only changes memory layout, not behaviour.
    """
    if sys.version_info >= (3, 10):
        spec.loader.exec_module(module)
        return

    real_dataclass = dataclasses.dataclass

    def shim(*args, **kwargs):
        kwargs.pop("slots", None)
        return real_dataclass(*args, **kwargs)

    dataclasses.dataclass = shim
    try:
        spec.loader.exec_module(module)
    finally:
        dataclasses.dataclass = real_dataclass


def _load_modules():
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = []
    sys.modules[_PKG] = pkg

    base = os.path.join(os.path.dirname(__file__), "..", "outwit_render_bridge")
    for name in ("bridge_models", "bridge_render_settings"):
        path = os.path.abspath(os.path.join(base, name + ".py"))
        spec = importlib.util.spec_from_file_location(f"{_PKG}.{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        _exec_module(spec, module)

    return sys.modules[f"{_PKG}.bridge_models"], sys.modules[f"{_PKG}.bridge_render_settings"]


_MODELS, _LOGIC = _load_modules()
RenderSettingsResponse = _MODELS.RenderSettingsResponse

_GROUPS = [
    {"id": "g-1", "name": "Studio GPUs"},
    {"id": "g-2", "name": "Render Farm B"},
]


class RenderSettingsModelTests(unittest.TestCase):
    def test_from_json_parses_pascal_case_payload(self):
        settings = RenderSettingsResponse.from_json({
            "RememberRenderSettings": False,
            "SplitFrame": True,
            "TilesX": 4,
            "TilesY": 3,
            "TileOverlap": 0,
            "AnimResult": "Video",
            "VideoContainer": "MP4",
            "VideoCodec": "H264",
            "LastGroupId": "g-1",
            "LastGroupName": "Studio GPUs",
        })

        self.assertFalse(settings.remember_render_settings)
        self.assertTrue(settings.split_frame)
        self.assertEqual(settings.tiles_x, 4)
        self.assertEqual(settings.tiles_y, 3)
        self.assertEqual(settings.tile_overlap, 0)  # 0 is a legitimate stored overlap
        self.assertEqual(settings.anim_result, "Video")
        self.assertEqual(settings.video_container, "MP4")
        self.assertEqual(settings.last_group_id, "g-1")

    def test_from_json_empty_payload_falls_back_to_defaults(self):
        settings = RenderSettingsResponse.from_json({})

        self.assertTrue(settings.remember_render_settings)
        self.assertFalse(settings.split_frame)
        self.assertEqual(settings.tiles_x, 2)
        self.assertEqual(settings.tiles_y, 2)
        self.assertEqual(settings.tile_overlap, 8)
        self.assertEqual(settings.anim_result, "Sequence")
        self.assertEqual(settings.last_group_id, "")

    def test_to_payload_round_trips_through_from_json(self):
        original = RenderSettingsResponse(
            remember_render_settings=True,
            split_frame=True,
            tiles_x=5,
            tiles_y=6,
            tile_overlap=0,
            anim_result="Video",
            video_container="MP4",
            video_codec="H264",
            last_group_id="g-2",
            last_group_name="Render Farm B",
        )

        restored = RenderSettingsResponse.from_json(original.to_payload())

        self.assertEqual(restored, original)


class SeedPropValuesTests(unittest.TestCase):
    def test_returns_empty_when_remember_is_off(self):
        settings = RenderSettingsResponse(remember_render_settings=False, split_frame=True)

        self.assertEqual(_LOGIC.seed_prop_values(settings), {})

    def test_maps_bucket_one_values_to_state_props(self):
        settings = RenderSettingsResponse(
            split_frame=True, tiles_x=4, tiles_y=3, tile_overlap=16, anim_result="Video",
            video_container="WEBM", video_codec="VP9")

        values = _LOGIC.seed_prop_values(settings)

        self.assertEqual(values, {
            "split_frame": True,
            "tiles_x": 4,
            "tiles_y": 3,
            "tile_overlap_px": 16,
            "anim_result": "Video",
            "video_format": "WEBM_VP9",
        })

    def test_sanitizes_corrupt_values_against_prop_constraints(self):
        settings = RenderSettingsResponse(
            tiles_x=0, tiles_y=-3, tile_overlap=-1, anim_result="Nonsense")

        values = _LOGIC.seed_prop_values(settings)

        self.assertEqual(values["tiles_x"], 1)
        self.assertEqual(values["tiles_y"], 1)
        self.assertEqual(values["tile_overlap_px"], 0)
        self.assertEqual(values["anim_result"], "Sequence")


class ResolveTargetSeedTests(unittest.TestCase):
    def test_returns_none_when_remember_is_off(self):
        settings = RenderSettingsResponse(remember_render_settings=False, last_group_id="g-1")

        self.assertIsNone(_LOGIC.resolve_target_seed(settings, _GROUPS, True))

    def test_restores_remembered_group_when_it_still_exists(self):
        settings = RenderSettingsResponse(last_group_id="g-2")

        self.assertEqual(_LOGIC.resolve_target_seed(settings, _GROUPS, False), ("g-2", False))

    def test_vanished_group_falls_back_to_defaults(self):
        settings = RenderSettingsResponse(last_group_id="g-gone")

        self.assertIsNone(_LOGIC.resolve_target_seed(settings, _GROUPS, True))

    def test_all_nodes_restored_only_while_still_allowed(self):
        settings = RenderSettingsResponse(last_group_id="")

        self.assertEqual(_LOGIC.resolve_target_seed(settings, _GROUPS, True), ("", True))
        self.assertIsNone(_LOGIC.resolve_target_seed(settings, _GROUPS, False))


class GroupNameForTests(unittest.TestCase):
    def test_resolves_known_group_name(self):
        self.assertEqual(_LOGIC.group_name_for(_GROUPS, "g-1"), "Studio GPUs")

    def test_unknown_or_empty_id_resolves_to_empty(self):
        self.assertEqual(_LOGIC.group_name_for(_GROUPS, "g-gone"), "")
        self.assertEqual(_LOGIC.group_name_for(_GROUPS, ""), "")


class ComposeStickyPayloadTests(unittest.TestCase):
    def test_overlays_used_values_including_video_preset(self):
        current = RenderSettingsResponse(video_container="MP4", video_codec="H264")

        payload = _LOGIC.compose_sticky_payload(
            current,
            remember=True,
            split_frame=True,
            tiles_x=4,
            tiles_y=3,
            tile_overlap=0,
            anim_result="Video",
            video_format="WEBM_VP9",
            group_id="g-1",
            group_name="Studio GPUs",
        )

        self.assertTrue(payload["RememberRenderSettings"])
        self.assertTrue(payload["SplitFrame"])
        self.assertEqual(payload["TilesX"], 4)
        self.assertEqual(payload["TileOverlap"], 0)
        self.assertEqual(payload["AnimResult"], "Video")
        self.assertEqual(payload["VideoContainer"], "WEBM")
        self.assertEqual(payload["VideoCodec"], "VP9")
        self.assertEqual(payload["LastGroupId"], "g-1")
        self.assertEqual(payload["LastGroupName"], "Studio GPUs")

    def test_all_nodes_submit_stores_empty_group(self):
        payload = _LOGIC.compose_sticky_payload(
            RenderSettingsResponse(),
            remember=True,
            split_frame=False,
            tiles_x=2,
            tiles_y=2,
            tile_overlap=8,
            anim_result="Sequence",
            video_format="MP4_H264",
            group_id="",
            group_name="",
        )

        self.assertEqual(payload["LastGroupId"], "")
        self.assertEqual(payload["LastGroupName"], "")
        self.assertEqual(payload["VideoContainer"], "MP4")
        self.assertEqual(payload["VideoCodec"], "H264")


class VideoFormatMappingTests(unittest.TestCase):
    def test_round_trips_all_presets(self):
        for preset in ("MP4_H264", "MP4_H265", "WEBM_VP9", "MOV_PRORES_422HQ", "MOV_PRORES_4444"):
            container, codec = _LOGIC.video_store_from_format(preset)
            self.assertEqual(_LOGIC.video_format_from_store(container, codec), preset)

    def test_legacy_empty_store_falls_back_to_default(self):
        self.assertEqual(_LOGIC.video_format_from_store("", ""), "MP4_H264")

    def test_unknown_pair_falls_back_to_default(self):
        self.assertEqual(_LOGIC.video_format_from_store("AVI", "XVID"), "MP4_H264")

    def test_store_lookup_is_case_insensitive(self):
        self.assertEqual(_LOGIC.video_format_from_store("webm", "vp9"), "WEBM_VP9")


class ComposeRememberPayloadTests(unittest.TestCase):
    def test_flips_only_the_master_flag(self):
        current = RenderSettingsResponse(
            split_frame=True, tiles_x=4, last_group_id="g-1", video_container="MP4")

        payload = _LOGIC.compose_remember_payload(current, False)

        self.assertFalse(payload["RememberRenderSettings"])
        self.assertTrue(payload["SplitFrame"])
        self.assertEqual(payload["TilesX"], 4)
        self.assertEqual(payload["LastGroupId"], "g-1")
        self.assertEqual(payload["VideoContainer"], "MP4")


if __name__ == "__main__":
    unittest.main()
