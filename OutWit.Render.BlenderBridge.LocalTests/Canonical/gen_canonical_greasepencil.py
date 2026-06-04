"""
Generates the canonical Grease Pencil scene for the distributed-render integration tests
(CanonicalRenderLiveDistributedIntegrationTests) and as a worked example for plugin authors.

Uses Grease Pencil v3 (Blender 4.3+/5.x): a Grease Pencil "monkey" (Suzanne drawn as strokes)
that spins over 120 frames via two linear keyframes. Fully procedural, no textures, no Python
drivers → a tiny git-committable .blend that renders a real animated 2D/GP effect.

Rendered with the GreasePencil engine path of the render controller (engine/resolution/samples
are overridden per job).

Regenerate (from the WitCloud repo root):
    <render.module>/blender/<os>/blender -b --python-exit-code 1 \
        --python Cloud/OutWit.Cloud.Tests/Canonical/gen_canonical_greasepencil.py -- @Data/canonical/canonical_greasepencil.blend
"""
import bpy, math, sys, os

out_path = sys.argv[-1]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = 120

# --- Grease Pencil monkey (GPv3): Suzanne rendered as strokes. Created facing the front
#     (-Y) view, so a front camera sees it face-on. ---
bpy.ops.object.grease_pencil_add(type='MONKEY')
gp = bpy.context.active_object
gp.location = (0.0, 0.0, 0.0)

# Pinwheel spin about the Y view axis = in-plane rotation toward the camera, so Suzanne stays
# fully face-on for the whole sequence (spinning about Z would go edge-on at the half-way frame).
# Two LINEAR keyframes = constant rotation, tiny on disk.
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
gp.rotation_euler = (0.0, 0.0, 0.0)
gp.keyframe_insert("rotation_euler", frame=1)
gp.rotation_euler = (0.0, math.radians(360), 0.0)
gp.keyframe_insert("rotation_euler", frame=120)

# --- Front camera looking along +Y straight at the monkey ---
bpy.ops.object.camera_add(location=(0.0, -6.0, 0.0))
cam = bpy.context.active_object
cam.rotation_euler = (math.radians(90), 0.0, 0.0)
cam.data.lens = 50
scene.camera = cam

# A light (cheap; GP shading is mostly flat but keeps the scene well-formed).
bpy.ops.object.light_add(type='AREA', location=(2, -4, 4))
bpy.context.active_object.data.energy = 400

# Light world background so the strokes read clearly.
world = bpy.data.worlds.new("CanonicalGpWorld")
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.9, 0.92, 0.95, 1.0)

scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.image_settings.file_format = 'PNG'

os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out_path)
print("SAVED", out_path, os.path.getsize(out_path), "bytes")
