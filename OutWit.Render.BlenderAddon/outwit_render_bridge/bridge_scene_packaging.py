from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager

import bpy


class ScenePackagingError(Exception):
    pass


def scene_output_signature(scene) -> str:
    """Fingerprint of the Output Properties facets that travel INSIDE the uploaded .blend rather
    than as explicit render options: image format family, color mode/depth, film transparency,
    and the video container/codec (which have no explicit wire fields yet). The upload cache must
    be invalidated when it changes — reusing the cached blob after, e.g., a PNG→EXR or container
    switch would silently render with the stale baked-in settings."""
    render = getattr(scene, "render", None)
    image = getattr(render, "image_settings", None)
    ffmpeg = getattr(render, "ffmpeg", None)
    return "|".join((
        str(getattr(image, "file_format", "") or ""),
        str(getattr(image, "color_mode", "") or ""),
        str(getattr(image, "color_depth", "") or ""),
        "T" if getattr(render, "film_transparent", False) else "O",
        str(getattr(ffmpeg, "format", "") or ""),
        str(getattr(ffmpeg, "codec", "") or ""),
    ))


@contextmanager
def create_packed_upload_copy(source_blend_path: str):
    if not source_blend_path:
        raise ScenePackagingError("Blend file path is required to create a packed upload copy.")

    blender_binary = str(getattr(bpy.app, "binary_path", "") or "")
    if not blender_binary or not os.path.isfile(blender_binary):
        raise ScenePackagingError("The current Blender executable path is not available for dependency packing.")

    temp_directory = tempfile.mkdtemp(prefix="outwit_blend_upload_")
    packed_blend_path = os.path.join(temp_directory, os.path.basename(source_blend_path))
    script_path = os.path.join(temp_directory, "pack_blend.py")

    try:
        shutil.copy2(source_blend_path, packed_blend_path)
        with open(script_path, "w", encoding="utf-8") as stream:
            stream.write(
                "import bpy\n"
                "bpy.ops.file.pack_all()\n"
                "\n"
                # Strip flow/effector (non-DOMAIN) fluid modifiers ONLY when the domain is already baked
                # (the local-bake path): their effect is captured in the baked cache, and their live
                # source->domain relations can crash a node rendering an isolated frame from the sliced
                # cache (mirrors the controller's post-bake strip). An UNbaked scene (delegated path) still
                # needs them for the farm bake, so it is left untouched. Runs on the upload COPY, so the
                # artist's live scene keeps its modifiers either way.
                "def _domain_is_baked(mod):\n"
                "    ds = getattr(mod, 'domain_settings', None)\n"
                "    if ds is None:\n"
                "        return False\n"
                "    return bool(getattr(ds, 'has_cache_baked_data', getattr(ds, 'is_cache_baked_data', False)))\n"
                "\n"
                "_has_baked_domain = any(\n"
                "    getattr(m, 'type', '') == 'FLUID' and getattr(m, 'fluid_type', '') == 'DOMAIN' and _domain_is_baked(m)\n"
                "    for o in bpy.data.objects for m in getattr(o, 'modifiers', []))\n"
                "if _has_baked_domain:\n"
                "    for o in list(bpy.data.objects):\n"
                "        for m in list(getattr(o, 'modifiers', [])):\n"
                "            if getattr(m, 'type', '') == 'FLUID' and getattr(m, 'fluid_type', '') != 'DOMAIN':\n"
                "                try:\n"
                "                    o.modifiers.remove(m)\n"
                "                except Exception:\n"
                "                    pass\n"
                "\n"
                "bpy.ops.wm.save_mainfile()\n"
            )

        result = subprocess.run(
            [blender_binary, "-b", packed_blend_path, "--python-exit-code", "1", "--python", script_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            raise ScenePackagingError(
                "Failed to create a packed upload copy for dependency collection. "
                f"Stdout: {stdout} Stderr: {stderr}"
            )

        yield packed_blend_path, "Blend uploaded from a packed temporary copy with Blender-packable dependencies included."
    finally:
        shutil.rmtree(temp_directory, ignore_errors=True)
