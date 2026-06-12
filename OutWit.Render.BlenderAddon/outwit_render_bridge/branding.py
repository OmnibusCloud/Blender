from __future__ import annotations

from pathlib import Path

import bpy
import bpy.utils.previews

PREVIEW_COLLECTION = None
DARK_LOGO_KEY = "omnibuscloud_logo_dark"
LIGHT_LOGO_KEY = "omnibuscloud_logo_light"
DARK_MARK_KEY = "omnibuscloud_mark_dark"
LIGHT_MARK_KEY = "omnibuscloud_mark_light"

# Tray-style connection badges (the desktop client's tray states, small undetailed mark).
_TRAY_KEYS = {
    "online": "omnibuscloud_tray_online",
    "offline": "omnibuscloud_tray_offline",
    "issue": "omnibuscloud_tray_issue",
}
_TRAY_FILES = {
    "online": "tray_online_32.png",
    "offline": "tray_offline_32.png",
    "issue": "tray_issue_32.png",
}


def _get_assets_directory() -> Path:
    return Path(__file__).resolve().parent / "assets"


def _resolve_preference_variant(context) -> str:
    preferences = context.preferences.addons[__package__].preferences
    return preferences.logo_variant


def _is_dark_theme(context) -> bool:
    try:
        theme = context.preferences.themes[0]
        color = getattr(theme.view_3d.space.gradients, "high_gradient", None)
        if color is None:
            return True

        components = list(color)[:3]
        if not components:
            return True

        average = sum(float(me) for me in components) / len(components)
        return average < 0.5
    except Exception:
        return True


def _resolve_logo_key(context) -> str:
    variant = _resolve_preference_variant(context)
    if variant == "Dark":
        return DARK_LOGO_KEY

    if variant == "Light":
        return LIGHT_LOGO_KEY

    return DARK_LOGO_KEY if _is_dark_theme(context) else LIGHT_LOGO_KEY


def register_branding() -> None:
    global PREVIEW_COLLECTION

    if PREVIEW_COLLECTION is not None:
        return

    previews = bpy.utils.previews.new()
    assets = _get_assets_directory()

    for key, file_name in (
        (DARK_LOGO_KEY, "omnibuscloud_logo_dark_256.png"),
        (LIGHT_LOGO_KEY, "omnibuscloud_logo_light_256.png"),
        (DARK_MARK_KEY, "omnibuscloud_mark_dark_256.png"),
        (LIGHT_MARK_KEY, "omnibuscloud_mark_light_256.png"),
    ):
        path = assets / file_name
        if path.exists():
            previews.load(key, str(path), "IMAGE")

    for status, file_name in _TRAY_FILES.items():
        path = assets / file_name
        if path.exists():
            previews.load(_TRAY_KEYS[status], str(path), "IMAGE")

    PREVIEW_COLLECTION = previews


def unregister_branding() -> None:
    global PREVIEW_COLLECTION

    if PREVIEW_COLLECTION is None:
        return

    bpy.utils.previews.remove(PREVIEW_COLLECTION)
    PREVIEW_COLLECTION = None


def get_logo_icon_id(context) -> int:
    if PREVIEW_COLLECTION is None:
        return 0

    key = _resolve_logo_key(context)
    icon = PREVIEW_COLLECTION.get(key)
    return icon.icon_id if icon is not None else 0


def get_mark_icon_id(context) -> int:
    """The detailed brand MARK (no wordmark) used for the signed-out lockup; theme-aware."""
    if PREVIEW_COLLECTION is None:
        return 0

    variant = _resolve_preference_variant(context)
    dark = variant == "Dark" or (variant != "Light" and _is_dark_theme(context))
    icon = PREVIEW_COLLECTION.get(DARK_MARK_KEY if dark else LIGHT_MARK_KEY)
    return icon.icon_id if icon is not None else 0


def get_tray_icon_id(status: str) -> int:
    """Connection badge for the identity row: 'online' / 'offline' / 'issue' (the desktop client's
    tray states). Returns 0 when the asset is missing — callers fall back to the plain logo."""
    if PREVIEW_COLLECTION is None:
        return 0

    key = _TRAY_KEYS.get(status)
    icon = PREVIEW_COLLECTION.get(key) if key else None
    return icon.icon_id if icon is not None else 0
