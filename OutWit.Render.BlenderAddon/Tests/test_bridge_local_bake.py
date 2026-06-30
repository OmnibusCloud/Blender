"""Headless unit tests for bridge_local_bake — the bpy-free local-bake logic, chiefly the fluid-cache
frame tagging that MUST match the controller's Render.BakeSimulation (gas density per-frame; liquid /
noise / config whole). bpy-free, so it loads and runs without Blender.

Run: python -m unittest discover -s Tests -p "*test*.py" (from OutWit.Render.BlenderAddon).
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge" / "bridge_local_bake.py"
SPEC = importlib.util.spec_from_file_location("bridge_local_bake", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Failed to load bridge_local_bake from {MODULE_PATH}")

bridge_local_bake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge_local_bake)


class ParseCacheFrameTests(unittest.TestCase):
    def test_parses_padded_frame_number(self):
        self.assertEqual(bridge_local_bake.parse_cache_frame("fluid_data_0042.vdb"), 42)

    def test_parses_single_digit(self):
        self.assertEqual(bridge_local_bake.parse_cache_frame("density_0001.vdb"), 1)

    def test_returns_none_without_frame(self):
        self.assertIsNone(bridge_local_bake.parse_cache_frame("config.uni"))


class FluidCacheFrameTests(unittest.TestCase):
    def test_gas_density_vdb_is_per_frame(self):
        self.assertEqual(bridge_local_bake.fluid_cache_frame("fluid_data_0042.vdb", is_liquid=False), 42)

    def test_gas_noise_vdb_is_global(self):
        # Noise grids ship whole — upsampling can depend on neighbours.
        self.assertIsNone(bridge_local_bake.fluid_cache_frame("fluid_noise_0042.vdb", is_liquid=False))

    def test_liquid_vdb_is_global(self):
        # A liquid mesh needs a cache contiguous from the sim start — never slice it per-frame.
        self.assertIsNone(bridge_local_bake.fluid_cache_frame("fluid_data_0042.vdb", is_liquid=True))

    def test_liquid_surface_mesh_is_global(self):
        self.assertIsNone(bridge_local_bake.fluid_cache_frame("fluid_mesh_0042.bobj.gz", is_liquid=True))

    def test_gas_non_vdb_is_global(self):
        self.assertIsNone(bridge_local_bake.fluid_cache_frame("fluid_data_0042.bobj.gz", is_liquid=False))

    def test_config_is_global(self):
        self.assertIsNone(bridge_local_bake.fluid_cache_frame("config.uni", is_liquid=False))


class BuildFluidCacheAttachmentTests(unittest.TestCase):
    def test_gas_density_attachment(self):
        attachment = bridge_local_bake.build_fluid_cache_attachment(
            "cache_0_domain/data/fluid_data_0042.vdb", is_liquid=False, blob_id="blob-1")

        self.assertEqual(attachment["Kind"], "FluidCache")
        self.assertEqual(attachment["BlobId"], "blob-1")
        self.assertEqual(attachment["RelativePath"], "cache_0_domain/data/fluid_data_0042.vdb")
        self.assertEqual(attachment["OriginalPath"], "//cache_0_domain/data/fluid_data_0042.vdb")
        self.assertEqual(attachment["PackagingStrategy"], "SceneAttachmentBlob")
        self.assertEqual(attachment["Frame"], 42)

    def test_liquid_attachment_is_global(self):
        attachment = bridge_local_bake.build_fluid_cache_attachment(
            "cache_0_domain/mesh/fluid_mesh_0042.bobj.gz", is_liquid=True)

        self.assertEqual(attachment["Kind"], "FluidCache")
        self.assertEqual(attachment["BlobId"], "")
        self.assertIsNone(attachment["Frame"])

    def test_normalises_backslashes(self):
        attachment = bridge_local_bake.build_fluid_cache_attachment(
            "cache_0_domain\\data\\fluid_data_0007.vdb", is_liquid=False)

        self.assertEqual(attachment["RelativePath"], "cache_0_domain/data/fluid_data_0007.vdb")
        self.assertEqual(attachment["OriginalPath"], "//cache_0_domain/data/fluid_data_0007.vdb")
        self.assertEqual(attachment["Frame"], 7)


if __name__ == "__main__":
    unittest.main()
