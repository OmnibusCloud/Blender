"""Local detection of bakeable simulations — the bpy-free decision logic.

A scene that contains a *sequential* simulation (Mantaflow fluid/smoke, cloth, soft body, dynamic
paint, dynamic particles, rigid body, or a Geometry-Nodes simulation zone) cannot be rendered
distributed as-is: frame N depends on frames 1…N-1, which a render node never sees. The render farm
resolves this by baking the simulation into a frame-addressable cache first — either delegated to the
fastest node (``Render.BakeSimulation`` via ``Grid.Delegate``) or locally in this Blender before
upload (see ``bake_strategy``).

This module turns a list of lightweight per-modifier descriptors (extracted from the scene by the bpy
scan in ``bridge_operators``) into a :class:`SimulationSummary` so the panel can offer the
bake-strategy choice and the launch gate can refuse to render an unbaked simulation. It is bpy-free
by design (mirrors ``bridge_render_settings`` / ``bridge_dependency_policy``) so the whole decision
surface is headless-testable; the thin bpy scan that produces the descriptors lives in the operators.
"""

from __future__ import annotations

from dataclasses import dataclass

# Feature gate for the LOCAL bake strategy. Delegated baking (on the fastest node, via
# ``Render.BakeSimulation`` + ``Grid.Delegate``) is the shipped default and is always available; the
# local-bake driver (a modal bake in the artist's Blender with native progress, plus a fluid-cache
# collector) lands in a later step. Until then the launch gate must refuse a LOCAL choice for an
# unbaked simulation rather than silently delegate or — worse — render it unbaked. Flip to ``True``
# once the local driver ships. See ``bridge_dependency_policy.resolve_bake_plan``.
LOCAL_BAKE_AVAILABLE = False

# Bakeable simulation kinds, as user-facing labels. Keep these stable — they appear in the panel and
# in the launch-gate message.
SIM_FLUID = "Fluid"
SIM_CLOTH = "Cloth"
SIM_SOFT_BODY = "Soft Body"
SIM_DYNAMIC_PAINT = "Dynamic Paint"
SIM_PARTICLES = "Particles"
SIM_RIGID_BODY = "Rigid Body"
SIM_GEOMETRY_NODES = "Geometry Nodes"

# Stable display order for the kinds above (anything unknown sorts last, alphabetically).
_KIND_ORDER = (
    SIM_FLUID,
    SIM_CLOTH,
    SIM_SOFT_BODY,
    SIM_DYNAMIC_PAINT,
    SIM_PARTICLES,
    SIM_RIGID_BODY,
    SIM_GEOMETRY_NODES,
)


@dataclass(slots=True, frozen=True)
class SimulationDescriptor:
    """One bakeable simulation found in the scene.

    ``kind`` is one of the ``SIM_*`` labels. ``is_baked`` is the simulation's current bake state
    (cloth/particle/etc point caches, a fluid domain's baked-data flag, a GN zone's bake). It informs
    the panel message ("2 of 3 baked") but does NOT change the gate: rebaking an already-baked sim on
    the farm is harmless and guarantees the cache reaches every node, so the gate keys on presence.
    """

    kind: str
    is_baked: bool


@dataclass(slots=True, frozen=True)
class SimulationSummary:
    """The result of classifying a scene's simulations.

    ``kinds`` — distinct kinds present (any bake state), in display order.
    ``unbaked_kinds`` — distinct kinds with at least one not-yet-baked instance, in display order.
    """

    kinds: tuple[str, ...]
    unbaked_kinds: tuple[str, ...]

    @property
    def has_simulation(self) -> bool:
        """True when the scene contains any bakeable simulation — the trigger for the strategy UI and
        the launch gate (an unbaked sim must never go to a plain ``Render*`` script)."""
        return bool(self.kinds)

    @property
    def has_unbaked(self) -> bool:
        """True when at least one simulation is not baked yet (drives the panel wording only)."""
        return bool(self.unbaked_kinds)

    def summary_text(self) -> str:
        """Comma-separated list of present kinds, e.g. ``"Fluid, Cloth"`` (empty when none)."""
        return ", ".join(self.kinds)

    def unbaked_summary_text(self) -> str:
        """Comma-separated list of unbaked kinds (empty when all are baked / none present)."""
        return ", ".join(self.unbaked_kinds)


# A canonical "no simulation" summary, reused so callers never special-case ``None``.
EMPTY_SUMMARY = SimulationSummary(kinds=(), unbaked_kinds=())


def summarize_simulations(descriptors: "list[SimulationDescriptor]") -> SimulationSummary:
    """Classify per-modifier descriptors into a :class:`SimulationSummary`.

    Distinct kinds are reported in :data:`_KIND_ORDER` (unknown kinds last, alphabetically) so the UI
    is deterministic regardless of object/modifier iteration order.
    """
    present: set[str] = set()
    unbaked: set[str] = set()
    for descriptor in descriptors:
        present.add(descriptor.kind)
        if not descriptor.is_baked:
            unbaked.add(descriptor.kind)

    return SimulationSummary(
        kinds=_in_display_order(present),
        unbaked_kinds=_in_display_order(unbaked),
    )


def _in_display_order(kinds: "set[str]") -> tuple[str, ...]:
    def sort_key(kind: str) -> tuple[int, str]:
        try:
            return (_KIND_ORDER.index(kind), "")
        except ValueError:
            return (len(_KIND_ORDER), kind)

    return tuple(sorted(kinds, key=sort_key))
