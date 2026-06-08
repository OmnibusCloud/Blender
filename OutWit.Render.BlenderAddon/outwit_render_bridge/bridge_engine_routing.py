from __future__ import annotations

import bpy

BLENDER_ENGINE_TOKEN_CYCLES = "CYCLES"
BLENDER_ENGINE_TOKEN_EEVEE = "BLENDER_EEVEE"
BLENDER_ENGINE_TOKEN_EEVEE_NEXT = "BLENDER_EEVEE_NEXT"

ENGINE_FAMILY_CYCLES = "Cycles"
ENGINE_FAMILY_EEVEE = "Eevee"
ENGINE_FAMILY_GREASE_PENCIL = "GreasePencil"
ENGINE_FAMILY_UNSUPPORTED = "Unsupported"

ENGINE_ENUM_CYCLES = 0
ENGINE_ENUM_EEVEE = 1
ENGINE_ENUM_GREASE_PENCIL = 2


class SceneEngineRoutingError(Exception):
    pass


def detect_scene_engine_family(scene: bpy.types.Scene) -> tuple[str, int]:
    engine_token = str(getattr(scene.render, "engine", "") or "")

    if engine_token == BLENDER_ENGINE_TOKEN_CYCLES:
        return ENGINE_FAMILY_CYCLES, ENGINE_ENUM_CYCLES

    if engine_token in {BLENDER_ENGINE_TOKEN_EEVEE, BLENDER_ENGINE_TOKEN_EEVEE_NEXT}:
        if _scene_uses_grease_pencil(scene):
            return ENGINE_FAMILY_GREASE_PENCIL, ENGINE_ENUM_GREASE_PENCIL

        return ENGINE_FAMILY_EEVEE, ENGINE_ENUM_EEVEE

    raise SceneEngineRoutingError(
        f"Unsupported Blender render engine '{engine_token}'. Supported engines: Cycles, Eevee/Eevee Next, Grease Pencil."
    )


def get_scene_engine_token(scene: bpy.types.Scene) -> str:
    return str(getattr(scene.render, "engine", "") or "")


# Blender output formats that produce a video container (vs. a still image).
_VIDEO_FILE_FORMATS = {"FFMPEG", "AVI_JPEG", "AVI_RAW"}


def recommended_render_mode(scene: bpy.types.Scene) -> str:
    """The render mode that best fits the scene's output settings, so the addon doesn't default to
    Video for a single still (or Still for an animation):
      - a video output format -> "Video";
      - otherwise a single frame (start == end) -> "Still";
      - otherwise a frame range -> "Frames".
    Tiled-still is an opt-in specialization and is never auto-recommended.
    """
    render = getattr(scene, "render", None)
    image_settings = getattr(render, "image_settings", None) if render is not None else None
    file_format = (getattr(image_settings, "file_format", "") or "") if image_settings is not None else ""

    if file_format in _VIDEO_FILE_FORMATS:
        return "Video"

    if int(getattr(scene, "frame_start", 1)) == int(getattr(scene, "frame_end", 1)):
        return "Still"

    return "Frames"


def render_mode_matches_recommendation(current_mode: str, recommended_mode: str) -> bool:
    """Whether the selected mode is an acceptable fit for the recommendation (tiled-still counts as a
    valid specialization of Still, so picking it doesn't trigger a 'wrong mode' hint)."""
    if current_mode == recommended_mode:
        return True
    return recommended_mode == "Still" and current_mode == "StillTiled"


def _scene_uses_grease_pencil(scene: bpy.types.Scene) -> bool:
    for obj in getattr(scene, "objects", []):
        obj_type = str(getattr(obj, "type", "") or "")
        if obj_type in {"GREASEPENCIL", "GPENCIL"}:
            return True

    return False
