from __future__ import annotations

import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "outwit_render_bridge" / "bridge_dependency_policy.py"
SPEC = importlib.util.spec_from_file_location("bridge_dependency_policy", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Failed to load bridge dependency policy module from {MODULE_PATH}")

bridge_dependency_policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge_dependency_policy)


class BridgeDependencyPolicyTests(unittest.TestCase):
    def test_get_dependency_portability_blocking_issue_returns_message_for_external_image_warning(self) -> None:
        summary = "Scene uses external image asset 'Texture' from '/tmp/texture.png'."

        result = bridge_dependency_policy.get_dependency_portability_blocking_issue(summary)

        self.assertIn("Current v1 policy blocks scenes with unresolved external dependencies", result)
        self.assertIn("supported packed-image or attachment-backed dependency paths", result)
        self.assertIn("Scene uses external image asset 'Texture'", result)

    def test_get_dependency_portability_blocking_issue_returns_message_for_vse_warning(self) -> None:
        summary = "Scene 'Edit' uses VSE image strip 'Plate' from '/tmp/sequence'. Ensure these media files are transferred for remote rendering."

        result = bridge_dependency_policy.get_dependency_portability_blocking_issue(summary)

        self.assertIn("Current v1 policy blocks scenes with unresolved external dependencies", result)
        self.assertIn("VSE image strip 'Plate'", result)

    def test_get_dependency_portability_blocking_issue_returns_cache_specific_message_for_external_cache_warning(self) -> None:
        summary = "Scene uses external cache file 'SimCache' from '/tmp/sim.abc'. Ensure this cache remains portable for remote rendering."

        result = bridge_dependency_policy.get_dependency_portability_blocking_issue(summary)

        self.assertIn("unresolved external cache dependencies", result)
        self.assertIn("supported attachment-backed cache-file path", result)
        self.assertIn("Scene uses external cache file 'SimCache'", result)

    def test_get_dependency_portability_blocking_issue_returns_empty_for_non_dependency_warning(self) -> None:
        summary = "Render backend selection may use CPU fallback on this node."

        result = bridge_dependency_policy.get_dependency_portability_blocking_issue(summary)

        self.assertEqual("", result)

    def test_get_simulation_cache_blocking_issue_returns_message_for_fluid_cache_issue(self) -> None:
        summary = "Fluid domain 'Domain' uses external cache directory '/tmp/cache', which is not portable to remote nodes in the current v1 flow."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("fluid simulations that depend on external cache directories", result)
        self.assertIn("Fluid domain 'Domain' uses external cache directory", result)

    def test_get_simulation_cache_blocking_issue_returns_message_for_missing_baked_simulation_data(self) -> None:
        summary = "Fluid domain 'Domain' requires baked simulation data before remote rendering."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("require baked data before remote rendering", result)
        self.assertIn("requires baked simulation data before remote rendering", result)

    def test_get_simulation_cache_blocking_issue_returns_message_for_missing_baked_mesh_cache(self) -> None:
        summary = "Fluid domain 'Domain' requires baked mesh cache before remote rendering."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("require baked mesh cache before remote rendering", result)
        self.assertIn("requires baked mesh cache before remote rendering", result)

    def test_get_simulation_cache_blocking_issue_returns_message_for_cloth_simulation_issue(self) -> None:
        summary = "Cloth simulation 'Pillow' is not yet portable to remote rendering in the current v1 flow."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Cloth simulation 'Pillow'", result)

    def test_get_simulation_cache_blocking_issue_returns_message_for_particle_simulation_issue(self) -> None:
        summary = "Particle simulation 'Emitter' is not yet portable to remote rendering in the current v1 flow."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Particle simulation 'Emitter'", result)

    def test_get_simulation_cache_blocking_issue_returns_message_for_geometry_cache_issue(self) -> None:
        summary = "Geometry cache 'AlembicCharacter' is not yet portable to remote rendering in the current v1 flow."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Geometry cache 'AlembicCharacter'", result)

    def test_get_simulation_cache_blocking_issue_returns_empty_for_non_simulation_issue(self) -> None:
        summary = "Scene uses external image asset 'Texture' from '/tmp/texture.png'."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertEqual("", result)


if __name__ == "__main__":
    unittest.main()
