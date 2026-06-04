"""
Generates the canonical "wave" scene used by the distributed-render integration tests
(CanonicalRenderLiveDistributedIntegrationTests) and as a worked example for plugin authors.

It is fully procedural — no external textures, no Python drivers (which render nodes block
for untrusted files) — so the resulting .blend is tiny (~0.5 MB, git-committable) yet renders
a real animated effect: a rippling metallic surface (Wave modifier, animates with the frame)
under a slowly spinning emissive torus (two linear keyframes).

The scene works under BOTH Cycles and Eevee — the render engine, resolution and sample count
are overridden per job by the render controller, so this file only carries geometry, materials,
animation and a 120-frame range.

Regenerate (from the WitCloud repo root), using the Blender bundled with the render controller:
    <render.module>/blender/<os>/blender -b --python-exit-code 1 \
        --python Cloud/OutWit.Cloud.Tests/Canonical/gen_canonical_wave.py -- @Data/canonical/canonical_wave.blend
"""
import bpy, math, sys, os

out_path = sys.argv[-1]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# A real animated sequence — many frames so the distributed split is meaningful.
scene.frame_start = 1
scene.frame_end = 120

# --- Rippling metallic surface. The Wave modifier animates with the current frame on its own
#     (no keyframes, no Python driver), so every node renders an identical deterministic ripple. ---
bpy.ops.mesh.primitive_grid_add(x_subdivisions=120, y_subdivisions=120, size=14, location=(0, 0, 0))
surf = bpy.context.active_object
wave = surf.modifiers.new(name="Wave", type='WAVE')
wave.use_x = True
wave.use_y = True
wave.height = 0.8
wave.width = 1.4
wave.narrowness = 2.0
wave.speed = 0.25
surf.modifiers.new(name="Subsurf", type='SUBSURF').levels = 1
surf_mat = bpy.data.materials.new("CanonicalSurface")
surf_mat.use_nodes = True
sb = surf_mat.node_tree.nodes['Principled BSDF']
sb.inputs['Base Color'].default_value = (0.05, 0.35, 0.8, 1.0)
sb.inputs['Metallic'].default_value = 0.9
sb.inputs['Roughness'].default_value = 0.18
surf.data.materials.append(surf_mat)

# --- Spinning emissive torus. Two LINEAR keyframes = constant spin, tiny on disk. ---
bpy.ops.mesh.primitive_torus_add(location=(0, 0, 2.2), major_radius=1.3, minor_radius=0.45)
torus = bpy.context.active_object
bpy.ops.object.shade_smooth()
glow = bpy.data.materials.new("CanonicalGlow")
glow.use_nodes = True
gb = glow.node_tree.nodes['Principled BSDF']
gb.inputs['Base Color'].default_value = (1.0, 0.5, 0.15, 1.0)
gb.inputs['Emission Color'].default_value = (1.0, 0.45, 0.1, 1.0)
gb.inputs['Emission Strength'].default_value = 14.0
torus.data.materials.append(glow)
# Set LINEAR as the default for newly inserted keys (Blender 5.x hides Action.fcurves).
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
torus.rotation_euler = (0.0, 0.0, 0.0)
torus.keyframe_insert("rotation_euler", frame=1)
torus.rotation_euler = (math.radians(180), 0.0, math.radians(360))
torus.keyframe_insert("rotation_euler", frame=120)

# --- Three-point area lighting ---
for lx, ly, energy in [(6, -6, 1200), (-7, 5, 800), (0, 9, 600)]:
    bpy.ops.object.light_add(type='AREA', location=(lx, ly, 8))
    light = bpy.context.active_object
    light.data.energy = energy
    light.data.size = 5

# --- Camera framing the whole surface ---
bpy.ops.object.camera_add(location=(11, -11, 8))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(62), 0.0, math.radians(45))
cam.data.lens = 40
scene.camera = cam

# --- Subtle dark ambient world ---
world = bpy.data.worlds.new("CanonicalWorld")
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.02, 0.02, 0.03, 1.0)

# Baseline render settings (overridden per job by the controller; kept for standalone opens).
scene.render.engine = 'CYCLES'
scene.cycles.samples = 128
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.image_settings.file_format = 'PNG'

os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out_path)
print("SAVED", out_path, os.path.getsize(out_path), "bytes")
