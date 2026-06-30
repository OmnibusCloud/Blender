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
    """The safe default render mode for a scene's output settings:
      - a video output format -> "Video" (the artist clearly wants a movie);
      - otherwise -> "Still".

    We deliberately do NOT auto-pick Frames from a frame range: a .blend often carries a wide default
    range (e.g. 1-10000) that the artist never intends to render, and Frames/Video are the expensive
    modes. Defaulting to the cheap single-frame Still avoids accidentally launching thousands of frames;
    rendering an animation is always an explicit choice (the panel still nudges toward Frames when the
    scene has a real range — see has_multi_frame_range)."""
    render = getattr(scene, "render", None)
    image_settings = getattr(render, "image_settings", None) if render is not None else None
    file_format = (getattr(image_settings, "file_format", "") or "") if image_settings is not None else ""

    if file_format in _VIDEO_FILE_FORMATS:
        return "Video"

    return "Still"


def scene_frame_count(scene: bpy.types.Scene) -> int:
    start = int(getattr(scene, "frame_start", 1))
    end = int(getattr(scene, "frame_end", 1))
    return max(1, end - start + 1)


def has_multi_frame_range(scene: bpy.types.Scene) -> bool:
    return scene_frame_count(scene) > 1


def suggested_render_mode(scene: bpy.types.Scene) -> str:
    """The mode to NUDGE the artist toward (panel hint + 'Use recommended mode' button) — unlike
    recommended_render_mode, this is FRAME-COUNT aware:
      - a video output format -> "Video";
      - a multi-frame image scene -> "Frames" (render the range as an image sequence);
      - otherwise -> "Still".

    Kept SEPARATE from recommended_render_mode (the safe auto-default applied on open) on purpose: the
    auto-default must never auto-pick an expensive Frames run from a wide default range (the 0.4.1
    lesson), but the artist SHOULD be nudged toward Frames for a real animation/simulation that would
    otherwise silently render a single frame. The nudge is one click away, and the large-frame launch
    confirmation still guards against an accidental huge range."""
    render = getattr(scene, "render", None)
    image_settings = getattr(render, "image_settings", None) if render is not None else None
    file_format = (getattr(image_settings, "file_format", "") or "") if image_settings is not None else ""

    if file_format in _VIDEO_FILE_FORMATS:
        return "Video"

    if has_multi_frame_range(scene):
        return "Frames"

    return "Still"


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
