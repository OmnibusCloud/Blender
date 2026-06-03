from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager

import bpy


class ScenePackagingError(Exception):
    pass


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
