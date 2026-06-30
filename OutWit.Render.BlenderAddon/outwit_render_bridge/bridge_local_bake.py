"""Local simulation bake — the bpy-free decision logic.

When the artist chooses the "On this computer" bake strategy, the addon bakes the scene's simulations in
the running Blender before upload, then renders the BAKED scene through the plain ``Render*`` path (no
delegated bake on the farm). The bpy bake driver and the fluid-cache collector live in
``bridge_operators``; this module holds the pure pieces they rely on — chiefly the fluid-cache frame
tagging, which MUST match the controller's ``Render.BakeSimulation`` so the distributed ``Render*`` path
slices the baked caches identically.

The critical, hard-won rule (mirrors ``BlenderBakeScript`` in the controller): only a GAS domain's
self-contained density grids (data ``*.vdb``, not ``noise``) are per-frame addressable; a LIQUID domain's
surface mesh, noise grids and config files must ship WHOLE (``Frame=None``), because a liquid mesh only
displays from a cache that is contiguous from the simulation start — a lone sliced frame falls back to the
domain bounding box (the "liquid renders as a glowing box" bug). bpy-free by design (mirrors
``bridge_simulation`` / ``bridge_dependency_policy``) so it is headless-testable.
"""

from __future__ import annotations

import re
from typing import Any

# Must equal bridge_scene_attachments.PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB — duplicated here so this
# module stays bpy-free (bridge_scene_attachments imports bpy).
_PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB = "SceneAttachmentBlob"

# Attachment kind for baked fluid cache files — must equal the controller's
# WitActivityAdapterRenderBakeSimulation.FluidCacheKind so the node materializes them correctly.
FLUID_CACHE_KIND = "FluidCache"

# Frame number embedded in a baked cache filename, e.g. "fluid_data_0042.vdb" -> 42. Mirrors the
# controller's frame_of(name) = re.search(r'_(\d+)\.', name).
_FRAME_RE = re.compile(r"_(\d+)\.")


def parse_cache_frame(filename: str) -> "int | None":
    """The frame number embedded in a baked cache filename, or None when there is none."""
    match = _FRAME_RE.search(filename)
    return int(match.group(1)) if match else None


def fluid_cache_frame(filename: str, is_liquid: bool) -> "int | None":
    """The ``Frame`` tag for one baked fluid cache file, EXACTLY mirroring the controller.

    Per-frame slicing is safe ONLY for a gas domain's self-contained density grids (data ``*.vdb``,
    excluding ``noise``); liquid surface meshes, noise grids and config files ship whole (``Frame=None``)
    so every node receives the contiguous cache it needs.
    """
    lowered = filename.lower()
    if (not is_liquid) and lowered.endswith(".vdb") and "noise" not in lowered:
        return parse_cache_frame(filename)

    return None


def build_fluid_cache_attachment(relative_path: str, is_liquid: bool, blob_id: str = "") -> dict[str, Any]:
    """An attachment-manifest entry for one baked fluid cache file, matching the controller's
    ``RenderSceneAttachmentRefData`` (Kind / BlobId / OriginalPath / RelativePath / PackagingStrategy /
    Frame). ``relative_path`` is the cache file's path relative to the .blend directory; it is normalised
    to forward slashes, and ``OriginalPath`` is its ``//``-prefixed blend-relative form (how Blender
    stores the cache reference). ``blob_id`` is filled by the bpy collector after the file is uploaded.
    """
    rel = relative_path.replace("\\", "/")
    filename = rel.rsplit("/", 1)[-1]
    return {
        "Kind": FLUID_CACHE_KIND,
        "BlobId": blob_id,
        "OriginalPath": "//" + rel,
        "RelativePath": rel,
        "PackagingStrategy": _PACKAGING_STRATEGY_SCENE_ATTACHMENT_BLOB,
        "Frame": fluid_cache_frame(filename, is_liquid),
    }
