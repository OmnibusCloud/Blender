from __future__ import annotations

from typing import NamedTuple

DEPENDENCY_PORTABILITY_BLOCK_PREFIX = (
    "Current v1 policy blocks scenes with unresolved external dependencies unless they are transferred through the supported packed-image or attachment-backed dependency paths."
)

CACHE_PORTABILITY_BLOCK_PREFIX = (
    "Current v1 policy blocks scenes with unresolved external cache dependencies unless they are transferred through the supported attachment-backed cache-file path."
)

SIMULATION_CACHE_BLOCK_PREFIX = (
    "Current v1 policy blocks scenes that depend on unsupported or non-portable simulation/cache state."
)

FLUID_CACHE_DIRECTORY_BLOCK_PREFIX = (
    "Current v1 policy blocks fluid simulations that depend on external cache directories because this workflow is not yet portable to remote nodes."
)

MISSING_BAKED_SIMULATION_BLOCK_PREFIX = (
    "Current v1 policy blocks simulations that still require baked data before remote rendering."
)

MISSING_BAKED_MESH_CACHE_BLOCK_PREFIX = (
    "Current v1 policy blocks simulations that still require baked mesh cache before remote rendering."
)


def _summary_items(summary: str) -> list[str]:
    return [me.strip() for me in summary.split("|") if me.strip()]


def _is_external_dependency_warning(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False

    return (
        "uses linked library" in normalized
        or "uses external " in normalized
        or "uses vse " in normalized
    )


def _blocking_prefix_for_warning(message: str) -> str:
    normalized = message.strip().lower()
    if "external cache file" in normalized:
        return CACHE_PORTABILITY_BLOCK_PREFIX

    return DEPENDENCY_PORTABILITY_BLOCK_PREFIX


def get_dependency_portability_blocking_issue(summary: str) -> str:
    for item in _summary_items(summary):
        if _is_external_dependency_warning(item):
            return f"{_blocking_prefix_for_warning(item)} {item}"

    return ""


def _is_simulation_cache_issue(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False

    return (
        "fluid domain" in normalized
        or "cloth simulation" in normalized
        or "particle simulation" in normalized
        # Rigid body bakes through the same embedded point-cache path as cloth (both bake paths run
        # ptcache.bake_all over the scene's rigidbody_world), so its issue is resolvable by a bake plan.
        # Matching the sim NAME keeps this true for both the 1.23.18+ validator wording ("requires baked
        # simulation data", matched below) and the old hard-block wording from a pre-1.23.18 server.
        or "rigid body simulation" in normalized
        or "geometry cache" in normalized
        or "requires baked simulation data" in normalized
        or "requires baked mesh cache" in normalized
    )


def _simulation_cache_blocking_prefix(message: str) -> str:
    normalized = message.strip().lower()
    if "uses external cache directory" in normalized:
        return FLUID_CACHE_DIRECTORY_BLOCK_PREFIX

    if "requires baked mesh cache" in normalized:
        return MISSING_BAKED_MESH_CACHE_BLOCK_PREFIX

    if "requires baked simulation data" in normalized:
        return MISSING_BAKED_SIMULATION_BLOCK_PREFIX

    return SIMULATION_CACHE_BLOCK_PREFIX


def get_simulation_cache_blocking_issue(summary: str) -> str:
    for item in _summary_items(summary):
        if _is_simulation_cache_issue(item):
            return f"{_simulation_cache_blocking_prefix(item)} {item}"

    return ""


def get_non_simulation_validation_issue(summary: str) -> str:
    """The first hard validation issue that is NOT a bakeable simulation/cache block.

    The launch gate may bypass a simulation-cache block when the artist has chosen a bake plan
    (the bake produces the missing cache), but ANY other validation failure — a missing engine,
    an unsupported feature — must still block. This isolates "is the scene invalid for a reason a
    bake won't fix?" from the summary the cloud validator returned.
    """
    for item in _summary_items(summary):
        if not _is_simulation_cache_issue(item):
            return item

    return ""


# How the artist's bake strategy resolves (or fails to resolve) an unbaked simulation, computed
# without bpy so it is headless-testable. The launch gate and the panel both read this verdict.
class BakePlan(NamedTuple):
    should_delegate: bool  # bake on the fastest node (Render.BakeSimulation via Grid.Delegate)
    should_local: bool     # bake here, in the artist's Blender, before upload
    block: str             # non-empty = the chosen plan cannot bake the sim; launch must refuse


LOCAL_BAKE_UNAVAILABLE_MESSAGE = (
    "Local baking is not available yet — choose “On render farm” to bake the "
    "simulation before rendering."
)

# Feature gate for the LOCAL bake strategy ("On this computer"): the modal bake driver +
# fluid-cache collector in bridge_operators. Now shipped, so the flag is True and ``resolve_bake_plan``
# lets a LOCAL choice cover an unbaked simulation. Kept as a flag (rather than removed) so the path can
# be disabled if a platform regression is found, and so the unit tests can exercise both states via the
# explicit ``local_bake_available`` parameter. Lives here (not in bridge_simulation) so the bpy-free gate
# in operators/status/panel can read it without importing the bpy-adjacent scan module.
LOCAL_BAKE_AVAILABLE = True


def resolve_bake_plan(
    has_unbaked_simulation: bool,
    bake_strategy: str,
    local_bake_available: bool,
) -> BakePlan:
    """Decide how an unbaked simulation is handled before a distributed render.

    The single source of truth for the launch gate's "may this scene render, and how?" question:

    * no unbaked simulation -> render directly, no bake (``BakePlan(False, False, "")``);
    * ``DELEGATED`` (the default, and anything other than ``LOCAL``) -> the farm bakes on the
      fastest node, then renders the baked scene;
    * ``LOCAL`` while local baking is available -> bake here, then render the baked scene;
    * ``LOCAL`` while it is NOT available yet -> ``block`` set: the launch must refuse rather than
      silently delegate or render the simulation unbaked.

    ``has_unbaked_simulation`` is the gate's authoritative signal — at launch it comes from the cloud
    validator's simulation-cache block; in the panel it comes from the local scene scan.
    """
    if not has_unbaked_simulation:
        return BakePlan(False, False, "")

    if (bake_strategy or "").strip().upper() == "LOCAL":
        if local_bake_available:
            return BakePlan(False, True, "")
        return BakePlan(False, False, LOCAL_BAKE_UNAVAILABLE_MESSAGE)

    # DELEGATED (default) — also the safe fallback for an unexpected/corrupt value, since delegated
    # baking is always available and never silently produces a wrong result.
    return BakePlan(True, False, "")
