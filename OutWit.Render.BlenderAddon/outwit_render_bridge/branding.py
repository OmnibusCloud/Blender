from __future__ import annotations

from pathlib import Path

import bpy
import bpy.utils.previews

PREVIEW_COLLECTION = None
DARK_LOGO_KEY = "omnibuscloud_logo_dark"
LIGHT_LOGO_KEY = "omnibuscloud_logo_light"


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

    dark_path = assets / "omnibuscloud_logo_dark_256.png"
    light_path = assets / "omnibuscloud_logo_light_256.png"

    if dark_path.exists():
        previews.load(DARK_LOGO_KEY, str(dark_path), "IMAGE")

    if light_path.exists():
        previews.load(LIGHT_LOGO_KEY, str(light_path), "IMAGE")

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
