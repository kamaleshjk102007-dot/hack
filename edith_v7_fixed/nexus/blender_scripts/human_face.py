"""Procedural human face scene for the NEXUS Blender connector."""
import bpy, math, os, sys
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
output_dir = args[args.index("--output-dir") + 1] if "--output-dir" in args else os.getcwd()
os.makedirs(output_dir, exist_ok=True)
blend_path = os.path.join(output_dir, "nexus_human_face.blend")
render_path = os.path.join(output_dir, "nexus_human_face.png")

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

def material(name, color, metallic=0.0, roughness=0.45):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat

skin = material("Skin", (0.48, 0.22, 0.12), roughness=.58)
white = material("Eye White", (.92, .94, .96), roughness=.25)
iris = material("Iris", (.05, .18, .22), roughness=.2)
dark = material("Pupil", (.006, .008, .01), roughness=.18)
lip = material("Lips", (.32, .055, .045), roughness=.5)

def uv(name, location, scale, mat, segments=64, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object; obj.name = name; obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_smooth(); obj.data.materials.append(mat)
    bev = obj.modifiers.new("Surface Smooth", "SUBSURF"); bev.levels = 1; bev.render_levels = 1
    return obj

head = uv("Head", (0, 0, 0.15), (1.52, 1.18, 1.9), skin)
for side in (-1, 1):
    x = .56 * side
    uv("Eye_L" if side < 0 else "Eye_R", (x, -1.02, .48), (.39, .19, .25), white, 48, 24)
    uv("Iris_L" if side < 0 else "Iris_R", (x, -1.205, .48), (.145, .045, .145), iris, 40, 20)
    uv("Pupil_L" if side < 0 else "Pupil_R", (x, -1.247, .48), (.055, .022, .06), dark, 32, 16)
    uv("Ear_L" if side < 0 else "Ear_R", (1.49*side, -.02, .12), (.28, .20, .55), skin, 40, 20)

nose = uv("Nose", (0, -1.23, .02), (.23, .42, .55), skin, 48, 24)
nose.rotation_euler.x = math.radians(-8)
uv("Nostril_L", (-.105, -1.58, -.12), (.045, .018, .028), dark, 24, 12)
uv("Nostril_R", (.105, -1.58, -.12), (.045, .018, .028), dark, 24, 12)

curve = bpy.data.curves.new("MouthCurve", "CURVE"); curve.dimensions = "3D"; curve.bevel_depth = .055; curve.bevel_resolution = 5
spline = curve.splines.new("BEZIER"); spline.bezier_points.add(4)
for p, co in zip(spline.bezier_points, [(-.52,-1.19,-.55),(-.27,-1.30,-.61),(0,-1.34,-.63),(.27,-1.30,-.61),(.52,-1.19,-.55)]):
    p.co = co; p.handle_left_type = "AUTO"; p.handle_right_type = "AUTO"
mouth = bpy.data.objects.new("Mouth", curve); bpy.context.collection.objects.link(mouth); curve.materials.append(lip)
uv("Chin", (0, -.93, -1.05), (.58, .28, .35), skin, 48, 24)
uv("Neck", (0, .05, -1.72), (.66, .62, .85), skin, 48, 24)

bpy.ops.object.camera_add(location=(0, -8.7, .25), rotation=(math.radians(90), 0, 0))
camera = bpy.context.object; camera.name = "Portrait Camera"; bpy.context.scene.camera = camera
def point_camera(obj, target=(0,0,.1)):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
point_camera(camera); camera.data.lens = 58

for name, location, energy, size, color in [
    ("Key", (-3.8,-4.8,4.5), 1050, 4.0, (1.0,.78,.65)),
    ("Fill", (4.0,-2.5,2.0), 650, 3.0, (.55,.7,1.0)),
    ("Rim", (0,2.8,4.2), 900, 2.5, (.45,.62,1.0))]:
    bpy.ops.object.light_add(type="AREA", location=location)
    light=bpy.context.object; light.name=name; light.data.energy=energy; light.data.shape="DISK"; light.data.size=size; light.data.color=color; point_camera(light)

scene=bpy.context.scene
try:
    scene.render.engine="BLENDER_EEVEE_NEXT"
except Exception:
    scene.render.engine="BLENDER_EEVEE"
scene.render.resolution_x=700; scene.render.resolution_y=700; scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"; scene.render.filepath=render_path
scene.world.color=(.008,.012,.025)
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print("NEXUS_OUTPUT=" + blend_path)
print("NEXUS_RENDER=" + render_path)
