"""Render settings storage in Blender's AddonPreferences.

Blender keeps AddonPreferences in the user's preferences file keyed by the
addon package id, OUTSIDE the extension directory — so remembered render
settings survive addon updates and reinstalls, exactly like the sign-in
session survives in the SDK's own store. The panel's bpy props remain the
transient UI binding; ``bridge_render_settings`` remains the pure decision
logic; this module is only the storage backend behind it.

History: the 1.x bridge persisted these per OS user via OutWit.Common.Settings
in its own process; the first embedded builds wrote ``render-settings.json``
next to the session store. The first load migrates that JSON's values into
the preferences once (``render_settings_version`` 0 → 1) so nothing the user
configured is lost, then the JSON is no longer consulted.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .bridge_models import RenderSettingsResponse

_CURRENT_STORE_VERSION = 1

# (pref attribute, payload key) — the storage fields behind RenderSettingsResponse;
# the master toggle lives on the long-standing `remember_render_settings` preference.
_FIELDS = (
    ("rs_split_frame", "SplitFrame"),
    ("rs_tiles_x", "TilesX"),
    ("rs_tiles_y", "TilesY"),
    ("rs_tile_overlap", "TileOverlap"),
    ("rs_anim_result", "AnimResult"),
    ("rs_video_container", "VideoContainer"),
    ("rs_video_codec", "VideoCodec"),
    ("rs_video_crf", "VideoCrf"),
    ("rs_last_target_id", "LastGroupId"),
    ("rs_last_target_name", "LastGroupName"),
    ("rs_bake_strategy", "BakeStrategy"),
)


def _preferences(context):
    return context.preferences.addons[__package__].preferences


def _legacy_json_path() -> str:
    """The embedded client's pre-preferences settings file (per-user data root)."""
    from .bridge_embedded import user_data_root

    return str(user_data_root() / "render-settings.json")


def _mark_dirty(context) -> None:
    """Ask Blender to save the preferences file; harmless where unsupported."""
    try:
        context.preferences.is_dirty = True
    except Exception:
        pass


def load_render_settings(context) -> RenderSettingsResponse:
    """The persisted snapshot, migrating the legacy JSON once on first read."""
    prefs = _preferences(context)

    if int(getattr(prefs, "render_settings_version", 0) or 0) < _CURRENT_STORE_VERSION:
        _migrate_legacy_json(context, prefs)

    return RenderSettingsResponse(
        remember_render_settings=bool(getattr(prefs, "remember_render_settings", True)),
        split_frame=bool(prefs.rs_split_frame),
        tiles_x=int(prefs.rs_tiles_x),
        tiles_y=int(prefs.rs_tiles_y),
        tile_overlap=int(prefs.rs_tile_overlap),
        anim_result=str(prefs.rs_anim_result or "Sequence"),
        video_container=str(prefs.rs_video_container or ""),
        video_codec=str(prefs.rs_video_codec or ""),
        video_crf=int(prefs.rs_video_crf),
        last_group_id=str(prefs.rs_last_target_id or ""),
        last_group_name=str(prefs.rs_last_target_name or ""),
        bake_strategy=str(prefs.rs_bake_strategy or "DELEGATED"),
    )


def save_render_settings(context, payload: dict[str, Any]) -> None:
    """Persist a settings payload (the PascalCase ``to_payload`` shape) into the preferences."""
    prefs = _preferences(context)
    settings = RenderSettingsResponse.from_json(payload)

    prefs.remember_render_settings = bool(settings.remember_render_settings)
    prefs.rs_split_frame = bool(settings.split_frame)
    prefs.rs_tiles_x = max(1, int(settings.tiles_x))
    prefs.rs_tiles_y = max(1, int(settings.tiles_y))
    prefs.rs_tile_overlap = max(0, int(settings.tile_overlap))
    prefs.rs_anim_result = settings.anim_result or "Sequence"
    prefs.rs_video_container = settings.video_container or ""
    prefs.rs_video_codec = settings.video_codec or ""
    prefs.rs_video_crf = min(51, max(0, int(settings.video_crf)))
    prefs.rs_last_target_id = settings.last_group_id or ""
    prefs.rs_last_target_name = settings.last_group_name or ""
    prefs.rs_bake_strategy = settings.bake_strategy or "DELEGATED"
    prefs.render_settings_version = _CURRENT_STORE_VERSION

    _mark_dirty(context)


def _migrate_legacy_json(context, prefs) -> None:
    """One-time import of the embedded client's ``render-settings.json`` values."""
    path = None
    try:
        path = _legacy_json_path()
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if isinstance(payload, dict):
                save_render_settings(context, payload)
                return
    except Exception:
        pass

    # Nothing to import (fresh machine / unreadable file): just stamp the version so
    # the defaults declared on the preference properties become the stored values.
    prefs.render_settings_version = _CURRENT_STORE_VERSION
    _mark_dirty(context)
