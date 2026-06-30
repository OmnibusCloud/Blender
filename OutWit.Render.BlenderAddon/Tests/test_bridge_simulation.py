"""Headless unit tests for the bpy-free simulation-detection logic.

bridge_simulation is bpy-free by design (mirrors bridge_render_settings) — the classification of
per-modifier descriptors into a SimulationSummary loads and runs WITHOUT Blender. The thin bpy scan
that produces the descriptors lives in bridge_operators and is not under test here.

Run: python -m unittest discover -s Tests -p "test_*.py" (from OutWit.Render.BlenderAddon).
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import sys
import types
import unittest

_PKG = "owrb_simulation_test"


def _exec_module(spec, module) -> None:
    """exec the module, shimming dataclass(slots=True) away on Python < 3.10.

    bridge_simulation targets Blender's bundled Python (3.11+, slots supported); the headless test
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


def _load_module():
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = []
    sys.modules[_PKG] = pkg

    base = os.path.join(os.path.dirname(__file__), "..", "outwit_render_bridge")
    path = os.path.abspath(os.path.join(base, "bridge_simulation.py"))
    spec = importlib.util.spec_from_file_location(f"{_PKG}.bridge_simulation", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    _exec_module(spec, module)
    return module


_SIM = _load_module()
Descriptor = _SIM.SimulationDescriptor
summarize = _SIM.summarize_simulations


class SummarizeTests(unittest.TestCase):
    def test_no_descriptors_is_empty(self):
        summary = summarize([])
        self.assertFalse(summary.has_simulation)
        self.assertFalse(summary.has_unbaked)
        self.assertEqual(summary.kinds, ())
        self.assertEqual(summary.summary_text(), "")

    def test_single_unbaked_sim(self):
        summary = summarize([Descriptor(_SIM.SIM_FLUID, is_baked=False)])
        self.assertTrue(summary.has_simulation)
        self.assertTrue(summary.has_unbaked)
        self.assertEqual(summary.kinds, (_SIM.SIM_FLUID,))
        self.assertEqual(summary.unbaked_kinds, (_SIM.SIM_FLUID,))

    def test_baked_sim_still_counts_as_present_but_not_unbaked(self):
        # Presence (not bake-state) drives the gate; bake-state only refines the wording.
        summary = summarize([Descriptor(_SIM.SIM_CLOTH, is_baked=True)])
        self.assertTrue(summary.has_simulation)
        self.assertFalse(summary.has_unbaked)
        self.assertEqual(summary.kinds, (_SIM.SIM_CLOTH,))
        self.assertEqual(summary.unbaked_kinds, ())

    def test_distinct_kinds_deduped_and_ordered(self):
        # Mixed iteration order + duplicates -> distinct kinds in canonical display order.
        summary = summarize([
            Descriptor(_SIM.SIM_GEOMETRY_NODES, is_baked=False),
            Descriptor(_SIM.SIM_CLOTH, is_baked=True),
            Descriptor(_SIM.SIM_CLOTH, is_baked=False),
            Descriptor(_SIM.SIM_FLUID, is_baked=True),
        ])
        self.assertEqual(summary.kinds, (_SIM.SIM_FLUID, _SIM.SIM_CLOTH, _SIM.SIM_GEOMETRY_NODES))
        # Only cloth (one unbaked instance) and GN are unbaked; fluid is baked.
        self.assertEqual(summary.unbaked_kinds, (_SIM.SIM_CLOTH, _SIM.SIM_GEOMETRY_NODES))
        self.assertEqual(summary.summary_text(), "Fluid, Cloth, Geometry Nodes")
        self.assertEqual(summary.unbaked_summary_text(), "Cloth, Geometry Nodes")

    def test_unknown_kind_sorts_last(self):
        summary = summarize([
            Descriptor("Zzz Custom", is_baked=False),
            Descriptor(_SIM.SIM_FLUID, is_baked=False),
        ])
        self.assertEqual(summary.kinds, (_SIM.SIM_FLUID, "Zzz Custom"))

    def test_empty_summary_constant(self):
        self.assertFalse(_SIM.EMPTY_SUMMARY.has_simulation)


if __name__ == "__main__":
    unittest.main()
