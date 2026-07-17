"""Phase 5: persisted render preferences — the pure decision logic.

The BRIDGE owns the storage (per-OS-user render-settings.json via OutWit.Common.Settings); the
addon's bpy props are a TRANSIENT UI binding. This module is bpy-free (its only import is the
bpy-free bridge_models) so the seed/sticky decisions are headless-testable; the thin appliers
that touch bpy state live in bridge_operators.

Flow: seed once per Blender session when the bridge becomes reachable (values → state props,
master flag → addon preferences), target-seed once when the execution scope (groups) is known,
sticky-write the actually-used values back after a successful submit — all under the
"Remember last render settings" master toggle.
"""

from __future__ import annotations

from typing import Any

from .bridge_models import RenderSettingsResponse
from .bridge_targets import group_target_id, project_target_id, split_target_id

_ANIM_RESULTS = {"Sequence", "Video"}
_BAKE_STRATEGIES = {"DELEGATED", "LOCAL"}
_DEFAULT_BAKE_STRATEGY = "DELEGATED"

# Video preset identifier (the bpy EnumProperty) <-> the stored Container/Codec pair (bucket 1).
_VIDEO_FORMAT_TO_STORE = {
    "MP4_H264": ("MP4", "H264"),
    "MP4_H265": ("MP4", "H265"),
    "WEBM_VP9": ("WEBM", "VP9"),
    "MOV_PRORES_422HQ": ("MOV", "PRORES422HQ"),
    "MOV_PRORES_4444": ("MOV", "PRORES4444"),
}
_STORE_TO_VIDEO_FORMAT = {pair: preset for preset, pair in _VIDEO_FORMAT_TO_STORE.items()}
_DEFAULT_VIDEO_FORMAT = "MP4_H264"


def video_format_from_store(container: str, codec: str) -> str:
    """The preset identifier for a stored container/codec pair; unknown/legacy-empty pairs fall
    back to the default (MP4/H.264 — the farm's legacy behaviour)."""
    return _STORE_TO_VIDEO_FORMAT.get(((container or "").upper(), (codec or "").upper()), _DEFAULT_VIDEO_FORMAT)


def video_store_from_format(video_format: str) -> tuple[str, str]:
    """The container/codec pair persisted for a preset identifier."""
    return _VIDEO_FORMAT_TO_STORE.get(video_format or "", _VIDEO_FORMAT_TO_STORE[_DEFAULT_VIDEO_FORMAT])


def seed_prop_values(settings: RenderSettingsResponse) -> dict[str, Any]:
    """The bucket-1 runtime-state props to apply on seed; empty when the master toggle is off.

    Values are sanitized against the bpy prop constraints (tiles >= 1, overlap >= 0, anim_result
    a known enum identifier) so a hand-edited/corrupt store cannot raise inside a prop write.
    """
    if not settings.remember_render_settings:
        return {}

    anim_result = settings.anim_result if settings.anim_result in _ANIM_RESULTS else "Sequence"
    bake_strategy = settings.bake_strategy if settings.bake_strategy in _BAKE_STRATEGIES else _DEFAULT_BAKE_STRATEGY
    return {
        "split_frame": bool(settings.split_frame),
        "tiles_x": max(1, int(settings.tiles_x)),
        "tiles_y": max(1, int(settings.tiles_y)),
        "tile_overlap_px": max(0, int(settings.tile_overlap)),
        "anim_result": anim_result,
        "video_format": video_format_from_store(settings.video_container, settings.video_codec),
        "video_constant_rate_factor": min(51, max(0, int(settings.video_crf))),
        "bake_strategy": bake_strategy,
    }


def resolve_target_seed(
    settings: RenderSettingsResponse,
    groups: list[dict[str, Any]],
    can_run_on_all_clients: bool,
    projects: list[dict[str, Any]] | None = None,
) -> tuple[str, bool] | None:
    """Resolves the remembered render target against the CURRENT scope.

    Returns ``(unified_target_id_to_select, run_on_all_nodes)`` or ``None`` when nothing should
    change: master toggle off, the remembered target no longer exists (fallback = leave the
    defaults), or "all nodes" was remembered but the account lost that right. The store's
    ``LastGroupId`` field carries the UNIFIED prefixed id since projects joined the dropdown —
    a legacy bare guid still reads as a group (split_target_id's back-compat).
    """
    if not settings.remember_render_settings:
        return None

    last_id = (settings.last_group_id or "").strip()
    if not last_id:
        # Empty id = the last run targeted all nodes; only restore while that is still allowed.
        return ("", True) if can_run_on_all_clients else None

    kind, raw_id = split_target_id(last_id)

    if kind == "project":
        for project in projects or []:
            if str(project.get("id", "")).strip() == raw_id:
                return (project_target_id(raw_id), False)
        return None

    for group in groups:
        if str(group.get("id", "")).strip() == raw_id:
            return (group_target_id(raw_id), False)

    return None


def target_name_for(
    groups: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    target_id: str,
) -> str:
    """Display name for a unified target id ("" when not found / all nodes)."""
    kind, raw_id = split_target_id(target_id)
    if not raw_id:
        return ""

    entries = projects if kind == "project" else groups
    for entry in entries:
        if str(entry.get("id", "")).strip() == raw_id:
            return str(entry.get("name", "")).strip()

    return ""


def compose_sticky_payload(
    current: RenderSettingsResponse,
    *,
    remember: bool,
    split_frame: bool,
    tiles_x: int,
    tiles_y: int,
    tile_overlap: int,
    anim_result: str,
    video_format: str,
    video_crf: int,
    target_id: str,
    target_name: str,
    bake_strategy: str,
) -> dict[str, Any]:
    """Read-modify-write: overlay the addon-owned bucket-1 values on the bridge's CURRENT snapshot.
    ``remember`` comes from the live UI toggle — the authoritative intent even if a previous toggle
    push is still pending. ``target_id`` is the UNIFIED prefixed id (or "" for all nodes); it lands
    in the store's historically named ``LastGroupId`` field, which the bridge round-trips opaquely."""
    container, codec = video_store_from_format(video_format)
    payload = current.to_payload()
    payload.update({
        "RememberRenderSettings": bool(remember),
        "SplitFrame": bool(split_frame),
        "TilesX": int(tiles_x),
        "TilesY": int(tiles_y),
        "TileOverlap": int(tile_overlap),
        "AnimResult": anim_result or "",
        "VideoContainer": container,
        "VideoCodec": codec,
        "VideoCrf": int(video_crf),
        "LastGroupId": target_id or "",
        "LastGroupName": target_name or "",
        "BakeStrategy": bake_strategy or _DEFAULT_BAKE_STRATEGY,
    })
    return payload


def compose_remember_payload(current: RenderSettingsResponse, remember: bool) -> dict[str, Any]:
    """Toggle-only write: flip the master flag, keep every stored value as-is."""
    payload = current.to_payload()
    payload["RememberRenderSettings"] = bool(remember)
    return payload
