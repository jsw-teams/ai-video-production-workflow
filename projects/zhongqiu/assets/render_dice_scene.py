import bpy
import math
import random
import os
from mathutils import Vector
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dice_frames"
OUT.mkdir(parents=True, exist_ok=True)
random.seed(31)

# Clear the default scene and set a compact, repeatable NPR render.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.materials, bpy.data.curves, bpy.data.meshes, bpy.data.cameras, bpy.data.lights):
    for item in list(datablocks):
        if item.users == 0:
            datablocks.remove(item)
scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = 960
scene.render.resolution_y = 540
scene.render.resolution_percentage = 100
scene.render.fps = 24
shading = scene.display.shading
shading.light = "STUDIO"
shading.studio_light = "paint.sl"
shading.color_type = "MATERIAL"
shading.background_type = "WORLD"
shading.show_shadows = False
shading.show_cavity = True
shading.cavity_type = "BOTH"
shading.cavity_ridge_factor = 1.6
shading.cavity_valley_factor = 1.4
shading.show_object_outline = True
shading.object_outline_color = (0.09, 0.13, 0.17)
shading.show_specular_highlight = False
shading.show_xray = False
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_percentage = 100
scene.render.film_transparent = False
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = str(OUT / "frame_")
scene.render.use_file_extension = True
scene.view_settings.view_transform = "Standard"
if "Medium High Contrast" in {entry.name for entry in scene.view_settings.bl_rna.properties["look"].enum_items}:
    scene.view_settings.look = "Medium High Contrast"
scene.view_settings.exposure = -0.6
scene.view_settings.gamma = 1
scene.render.image_settings.color_depth = "8"
scene.render.use_motion_blur = False

def mat(name, color, rough=0.72, noise=0.0, bump=0.0, metallic=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    nodes = m.node_tree.nodes
    bsdf = nodes.get("Principled BSDF") or nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.get("Material Output") or nodes.new("ShaderNodeOutputMaterial")
    if not any(link.from_node == bsdf and link.to_node == output for link in m.node_tree.links):
        m.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if noise or bump:
        n = nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 80 if noise > 0 else 26
        n.inputs["Detail"].default_value = 2
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.2
        ramp.color_ramp.elements[0].color = (*[c * (1-noise) for c in color], 1)
        ramp.color_ramp.elements[1].position = 0.8
        ramp.color_ramp.elements[1].color = (*[min(1,c * (1+noise)) for c in color], 1)
        m.node_tree.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
        m.node_tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if bump:
            b = nodes.new("ShaderNodeBump")
            b.inputs["Strength"].default_value = bump
            b.inputs["Distance"].default_value = 0.025
            m.node_tree.links.new(n.outputs["Fac"], b.inputs["Height"])
            m.node_tree.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    return m

paper = mat("Warm cotton paper", (0.77, 0.67, 0.53), noise=0.045, bump=0.12)
wood = mat("Hand-painted walnut table", (0.30, 0.17, 0.10), noise=0.11, bump=0.2)
porcelain = mat("Rice-glaze porcelain", (0.84, 0.79, 0.67), rough=0.55, noise=0.035, bump=0.035)
cobalt = mat("Indigo brushwork", (0.055, 0.16, 0.29), rough=0.72, noise=0.09)
ivory = mat("Ivory dice", (0.94, 0.80, 0.60), rough=0.68, noise=0.035)
ink = mat("Ink pips", (0.08, 0.14, 0.19), rough=0.75)
vermillion = mat("Vermilion pips and paper flecks", (0.70, 0.19, 0.10), rough=0.72)

def add_rigidbody(obj, typ, shape, mass=1.0, friction=0.7, restitution=0.2):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.rigidbody.object_add()
    obj.rigid_body.type = typ
    obj.rigid_body.collision_shape = shape
    obj.rigid_body.mass = mass
    obj.rigid_body.friction = friction
    obj.rigid_body.restitution = restitution
    obj.rigid_body.use_margin = True
    obj.rigid_body.collision_margin = 0.008
    obj.select_set(False)

# A deep, closed, lathed bowl: dice collide against the actual inner surface.
profile = [
    (0.00, 0.16), (0.68, 0.16), (1.32, 0.22), (1.82, 0.49),
    (2.12, 0.88), (2.28, 1.28), (2.30, 1.40), (2.19, 1.42),
    (2.08, 1.20), (1.90, 0.84), (1.58, 0.55), (1.20, 0.42), (0.58, 0.36), (0.00, 0.36),
]
verts, faces = [], []
segments = 96
for radius, z in profile:
    for i in range(segments):
        a = math.tau * i / segments
        verts.append((radius * math.cos(a), radius * math.sin(a), z))
for j in range(len(profile)-1):
    for i in range(segments):
        a = j*segments+i
        b = j*segments+(i+1)%segments
        c = (j+1)*segments+(i+1)%segments
        d = (j+1)*segments+i
        faces.append((a,b,c,d))
mesh = bpy.data.meshes.new("Wheel-thrown bowl shell")
mesh.from_pydata(verts, [], faces)
mesh.materials.append(porcelain)
mesh.materials.append(cobalt)
mesh.update()
bowl = bpy.data.objects.new("Porcelain bowl (passive collision mesh)", mesh)
bpy.context.collection.objects.link(bowl)
for poly in mesh.polygons:
    poly.use_smooth = True
    if 6*segments <= poly.index < 7*segments:
        poly.material_index = 1
solid = bowl.modifiers.new("Kiln-thin wall", "SOLIDIFY")
solid.thickness = 0.055
bevel = bowl.modifiers.new("Soft rim", "BEVEL")
bevel.width = 0.025
bevel.segments = 3
add_rigidbody(bowl, "PASSIVE", "MESH", friction=0.78, restitution=0.12)

# Cobalt rim, brush-painted bands and floral marks give the bowl a ceramic, not default-CG, read.
bpy.ops.mesh.primitive_torus_add(major_radius=2.25, minor_radius=0.038, major_segments=96, minor_segments=12, location=(0,0,1.405))
rim = bpy.context.object
rim.name = "Hand-painted cobalt rim"
rim.data.materials.append(cobalt)
for i in range(18):
    a = math.tau*i/18
    x, y = 2.04*math.cos(a), 2.04*math.sin(a)
    z = 0.82 + (i%3)*0.035
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.12, location=(x,y,z))
    leaf = bpy.context.object
    leaf.name = "Blue glaze brush petal"
    leaf.scale = (0.11,0.045,0.055)
    leaf.rotation_euler[2] = a
    leaf.data.materials.append(cobalt)
    for p in leaf.data.polygons: p.use_smooth = True
for radius, z in ((1.93,0.65),(2.10,0.90)):
    bpy.ops.curve.primitive_bezier_circle_add(radius=radius, location=(0,0,z))
    band=bpy.context.object; band.name="Hand-painted blue bowl band"; band.data.dimensions="3D"; band.data.bevel_depth=0.018; band.data.bevel_resolution=2; band.data.materials.append(cobalt)
for fx in (-0.52,0.0,0.52):
    # Small blue flower decals lie on the camera-facing outer wall of the bowl.
    fy=-math.sqrt(max(0,2.13**2-fx**2))
    for p in range(5):
        a=math.tau*p/5
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.10, location=(fx+math.cos(a)*0.12,fy,0.78+math.sin(a)*0.12))
        petal=bpy.context.object; petal.name="Blue flower on porcelain"; petal.scale=(0.10,0.025,0.055); petal.data.materials.append(cobalt)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.048, location=(fx,fy-0.01,0.78))
    center=bpy.context.object; center.name="Cobalt flower center"; center.scale=(1,0.4,1); center.data.materials.append(vermillion)

# Table and floor.
bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,-0.03))
table = bpy.context.object
table.name = "Tabletop"
table.dimensions = (200,200,0.28)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
table.data.materials.append(wood)
be = table.modifiers.new("Rounded table edge", "BEVEL"); be.width=0.09; be.segments=3
add_rigidbody(table, "PASSIVE", "BOX", friction=0.72, restitution=0.1)

# Six rounded, physically simulated dice. Pips are child detail; the collision hull remains a beveled die.
pip_patterns = {
    1:[(0,0)],
    2:[(-1,-1),(1,1)],
    3:[(-1,-1),(0,0),(1,1)],
    4:[(-1,-1),(-1,1),(1,-1),(1,1)],
    5:[(-1,-1),(-1,1),(0,0),(1,-1),(1,1)],
    6:[(-1,-1),(-1,0),(-1,1),(1,-1),(1,0),(1,1)],
}
face_defs = [
    ((0,0,1),(1,0,0),(0,1,0),1),
    ((0,0,-1),(1,0,0),(0,-1,0),6),
    ((1,0,0),(0,1,0),(0,0,1),2),
    ((-1,0,0),(0,-1,0),(0,0,1),5),
    ((0,1,0),(-1,0,0),(0,0,1),3),
    ((0,-1,0),(1,0,0),(0,0,1),4),
]
dice = []
start_positions = [(0.92*math.cos(math.tau*i/6),0.92*math.sin(math.tau*i/6),3.90) for i in range(6)]
for i, (sx, sy, sz) in enumerate(start_positions):
    size = 0.48
    bpy.ops.mesh.primitive_cube_add(size=size, location=(sx,sy,sz))
    die = bpy.context.object
    die.name = f"Die {i+1} — rigid body"
    die.rotation_euler = (random.uniform(-0.16,0.16),random.uniform(-0.16,0.16),random.uniform(0,math.tau))
    die.data.materials.append(ivory)
    bevel = die.modifiers.new("Soft worn corners", "BEVEL"); bevel.width=0.052; bevel.segments=4
    bevel.profile=0.5
    weighted = die.modifiers.new("Broad ceramic facets", "WEIGHTED_NORMAL")
    add_rigidbody(die,"ACTIVE","CONVEX_HULL",mass=0.065,friction=0.78,restitution=0.15)
    die.rigid_body.linear_damping = 0.30
    die.rigid_body.angular_damping = 0.46
    for normal, u, v, value in face_defs:
        for dx,dy in pip_patterns[value]:
            local = Vector(normal)*(size/2+0.004) + Vector(u)*(dx*0.105) + Vector(v)*(dy*0.105)
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.043)
            pip=bpy.context.object
            pip.name=f"Die pip {value}"
            pip.parent=die
            pip.location=local
            pip.scale=(1,1,0.28)
            pip.rotation_euler = Vector((0,0,1)).rotation_difference(Vector(normal)).to_euler()
            pip.data.materials.append(vermillion)
            for p in pip.data.polygons: p.use_smooth=True
    dice.append(die)

# Parchment sweep behind the tabletop.
bpy.ops.mesh.primitive_plane_add(size=200, location=(0,0,-0.20))
backdrop=bpy.context.object; backdrop.name="Cotton paper ground"; backdrop.data.materials.append(paper)

# Illustration-like lighting: a warm window key with cool moonlit fill.
world=bpy.data.worlds.new("Paper studio") if not bpy.data.worlds else bpy.data.worlds[0]
scene.world=world; world.use_nodes=True
world.node_tree.nodes["Background"].inputs["Color"].default_value=(0.36,0.31,0.24,1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value=0.22
def area(name, loc, color, power, size):
    bpy.ops.object.light_add(type="AREA", location=loc)
    light=bpy.context.object; light.name=name; light.data.energy=power; light.data.color=color; light.data.shape="DISK"; light.data.size=size
    light.rotation_euler=(Vector((0,0,0.55))-light.location).to_track_quat("-Z","Y").to_euler()
area("Warm window light",(-4,-4,8),(1.0,.78,.52),190,6)
area("Cool moon fill",(4,2,6),(.58,.72,1.0),100,5)
area("Soft overhead",(0,0,10),(1.0,.92,.78),70,7)

bpy.ops.object.camera_add(location=(0,-12.7,13.5))
camera=bpy.context.object
camera.name="Tabletop camera"
camera.rotation_euler=(Vector((0,0,2.9))-camera.location).to_track_quat("-Z","Y").to_euler()
camera.data.lens=42
scene.camera=camera
camera.data.dof.use_dof=False

# Rigid-body simulation is baked before rendering so every frame has the same tested collision outcome.
scene.frame_start=1
scene.frame_end=int(os.environ.get("ZHONGQIU_TEST_FRAMES", "96"))
rw=scene.rigidbody_world
rw.substeps_per_frame=120
rw.solver_iterations=24
rw.point_cache.frame_start=1
rw.point_cache.frame_end=scene.frame_end
scene.frame_set(1)
bpy.context.view_layer.update()

# Render a diagnostic frame, then the complete six-dice drop and settling action.
scene.render.filepath=str(OUT / "frame_")
for frame in range(scene.frame_start, scene.frame_end+1):
    scene.frame_set(frame)
    scene.render.filepath=str(OUT / f"frame_{frame:04d}.png")
    bpy.ops.render.render(write_still=True)
    if frame % 24 == 0:
        print(f"Rendered {frame}/{scene.frame_end}", flush=True)
print("DICE_RENDER_OK", scene.frame_end, str(OUT), flush=True)
