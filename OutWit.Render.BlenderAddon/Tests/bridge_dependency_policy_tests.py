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

    def test_get_simulation_cache_blocking_issue_classifies_rigid_body_requires_baked_message(self) -> None:
        # The 1.23.18+ validator wording — must resolve to a bake plan (delegated/local), not a hard block.
        summary = "Rigid body simulation requires baked simulation data before remote rendering."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("require baked data before remote rendering", result)
        self.assertIn("Rigid body simulation requires baked simulation data", result)

    def test_get_simulation_cache_blocking_issue_classifies_legacy_rigid_body_message(self) -> None:
        # A pre-1.23.18 server still emits the old hard-block wording; the addon must classify it as a
        # bake-resolvable simulation issue so mixed fleets keep working.
        summary = ("Rigid body simulation 'CellFracture_Breaker' is not yet portable to remote rendering "
                   "in the current v1 flow. Bake it to keyframes or Alembic and re-submit.")

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertIn("unsupported or non-portable simulation/cache state", result)
        self.assertIn("Rigid body simulation 'CellFracture_Breaker'", result)

    def test_get_simulation_cache_blocking_issue_returns_empty_for_non_simulation_issue(self) -> None:
        summary = "Scene uses external image asset 'Texture' from '/tmp/texture.png'."

        result = bridge_dependency_policy.get_simulation_cache_blocking_issue(summary)

        self.assertEqual("", result)


class NonSimulationValidationIssueTests(unittest.TestCase):
    def test_returns_empty_when_only_simulation_issues_present(self) -> None:
        summary = "Cloth simulation 'Pillow' is not yet portable. | Fluid domain 'Domain' requires baked simulation data before remote rendering."

        self.assertEqual("", bridge_dependency_policy.get_non_simulation_validation_issue(summary))

    def test_returns_the_non_simulation_issue_when_mixed(self) -> None:
        summary = "Cloth simulation 'Pillow' is not yet portable. | Scene uses an unsupported render engine 'OCTANE'."

        result = bridge_dependency_policy.get_non_simulation_validation_issue(summary)

        self.assertEqual("Scene uses an unsupported render engine 'OCTANE'.", result)

    def test_returns_empty_for_empty_summary(self) -> None:
        self.assertEqual("", bridge_dependency_policy.get_non_simulation_validation_issue(""))


class ResolveBakePlanTests(unittest.TestCase):
    def test_no_simulation_renders_directly(self) -> None:
        plan = bridge_dependency_policy.resolve_bake_plan(False, "DELEGATED", local_bake_available=True)

        self.assertEqual((False, False, ""), tuple(plan))

    def test_delegated_bakes_on_the_farm(self) -> None:
        plan = bridge_dependency_policy.resolve_bake_plan(True, "DELEGATED", local_bake_available=False)

        self.assertTrue(plan.should_delegate)
        self.assertFalse(plan.should_local)
        self.assertEqual("", plan.block)

    def test_local_bakes_here_when_available(self) -> None:
        plan = bridge_dependency_policy.resolve_bake_plan(True, "LOCAL", local_bake_available=True)

        self.assertFalse(plan.should_delegate)
        self.assertTrue(plan.should_local)
        self.assertEqual("", plan.block)

    def test_local_blocks_when_not_available(self) -> None:
        plan = bridge_dependency_policy.resolve_bake_plan(True, "LOCAL", local_bake_available=False)

        self.assertFalse(plan.should_delegate)
        self.assertFalse(plan.should_local)
        self.assertEqual(bridge_dependency_policy.LOCAL_BAKE_UNAVAILABLE_MESSAGE, plan.block)

    def test_unknown_strategy_falls_back_to_delegated(self) -> None:
        # A corrupt/empty stored value must never block or silently render unbaked: delegated baking
        # is always available and safe, so it is the fallback.
        for strategy in ("", "bogus", None):
            plan = bridge_dependency_policy.resolve_bake_plan(True, strategy, local_bake_available=False)
            self.assertTrue(plan.should_delegate, strategy)
            self.assertEqual("", plan.block, strategy)

    def test_strategy_is_case_insensitive(self) -> None:
        plan = bridge_dependency_policy.resolve_bake_plan(True, "local", local_bake_available=True)

        self.assertTrue(plan.should_local)


if __name__ == "__main__":
    unittest.main()
