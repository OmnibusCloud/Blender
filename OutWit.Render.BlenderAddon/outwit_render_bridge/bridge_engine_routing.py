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


def _scene_uses_grease_pencil(scene: bpy.types.Scene) -> bool:
    for obj in getattr(scene, "objects", []):
        obj_type = str(getattr(obj, "type", "") or "")
        if obj_type in {"GREASEPENCIL", "GPENCIL"}:
            return True

    return False
