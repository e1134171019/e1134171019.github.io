from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUT = ROOT / "artifacts" / "mhr-cinematic-appearance-gate"
OUT.mkdir(parents=True, exist_ok=True)
FBX = ROOT / "assets" / "lod1.fbx"


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


def world_vertices(obj):
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def world_bounds(objects):
    pts = []
    for obj in objects:
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    if not pts:
        raise RuntimeError("No mesh geometry found after FBX import")
    return (
        Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
        Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))),
    )


def anatomical_head_bounds(meshes, body_center, bmax, extent):
    z_floor = bmax.z - extent.z * 0.145
    x_limit = extent.z * 0.085
    pts = []
    for obj in meshes:
        for p in world_vertices(obj):
            if p.z >= z_floor and abs(p.x - body_center.x) <= x_limit:
                pts.append(p)
    if len(pts) < 100:
        raise RuntimeError(f"Insufficient anatomical head samples: {len(pts)}")
    return (
        Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
        Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))),
    )


def principled_input(bsdf, name, value):
    socket = bsdf.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def make_skin_material():
    mat = bpy.data.materials.new("CinematicSkin")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    principled_input(bsdf, "Base Color", (0.285, 0.112, 0.060, 1.0))
    principled_input(bsdf, "Roughness", 0.52)
    principled_input(bsdf, "IOR", 1.42)
    principled_input(bsdf, "Subsurface Weight", 0.07)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 140.0
    noise.inputs["Detail"].default_value = 5.0
    noise.inputs["Roughness"].default_value = 0.70
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.085
    bump.inputs["Distance"].default_value = 0.0010
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_simple_material(name, base_color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    principled_input(bsdf, "Base Color", (*base_color, 1.0))
    principled_input(bsdf, "Roughness", roughness)
    principled_input(bsdf, "Metallic", metallic)
    return mat


def make_hair_material():
    mat = make_simple_material("HairDarkBrown", (0.010, 0.004, 0.002), 0.50)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 190.0
    noise.inputs["Detail"].default_value = 3.5
    noise.inputs["Roughness"].default_value = 0.78
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 0.0013
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def assign_material(objects, mat):
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def add_uv_sphere(name, location, scale, material, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def find_head_bone(armature):
    if not armature:
        return None
    names = [b.name for b in armature.data.bones]
    for n in ["c_head", "head", "Head", "HEAD", "b_head", "joint_head"]:
        if n in names:
            return n
    for n in names:
        low = n.lower()
        if "head" in low and "end" not in low:
            return n
    return None


def parent_to_bone_keep_world(obj, armature, bone_name):
    if not armature or not bone_name:
        return False
    mw = obj.matrix_world.copy()
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = mw
    return True


def add_eye_from_head_bounds(side, hmin, hmax, armature, head_bone, mats):
    hsize = hmax - hmin
    sx = 1 if side == "L" else -1
    x = (hmin.x + hmax.x) * 0.5 + sx * hsize.x * 0.145
    z = hmax.z - hsize.z * 0.360
    # Front is -Y. Place the globe well inside the skull volume; only its front shell should meet the eyelid opening.
    cy = hmin.y + hsize.y * 0.170
    rx = hsize.x * 0.055
    ry = hsize.y * 0.043
    rz = hsize.z * 0.047

    sclera = add_uv_sphere(f"Eye_{side}_Sclera", (x, cy, z), (rx, ry, rz), mats["sclera"])
    iris_y = cy - ry * 0.94
    iris = add_uv_sphere(f"Eye_{side}_Iris", (x, iris_y, z), (rx * 0.37, ry * 0.12, rz * 0.43), mats["iris"], 40, 20)
    pupil = add_uv_sphere(f"Eye_{side}_Pupil", (x, iris_y - ry * 0.10, z), (rx * 0.15, ry * 0.06, rz * 0.18), mats["pupil"], 32, 16)
    highlight = add_uv_sphere(
        f"Eye_{side}_Catchlight",
        (x - sx * rx * 0.18, iris_y - ry * 0.15, z + rz * 0.22),
        (rx * 0.060, ry * 0.035, rz * 0.070),
        mats["catchlight"], 24, 12,
    )
    for obj in (sclera, iris, pupil, highlight):
        parent_to_bone_keep_world(obj, armature, head_bone)
    return [sclera, iris, pupil, highlight], Vector((x, cy, z)), Vector((rx, ry, rz))


def add_poly_curve(name, points, material, bevel_depth):
    curve_data = bpy.data.curves.new(name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = 3
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="MESH")
    return obj


def add_eyebrows(hmin, hmax, armature, head_bone, hair_mat):
    hsize = hmax - hmin
    center_x = (hmin.x + hmax.x) * 0.5
    y = hmin.y + hsize.y * 0.070
    z = hmax.z - hsize.z * 0.235
    brows = []
    for side, sx in (("L", 1), ("R", -1)):
        cx = center_x + sx * hsize.x * 0.145
        pts = [
            (cx - sx * hsize.x * 0.072, y + 0.0010, z - 0.002),
            (cx - sx * hsize.x * 0.024, y - 0.0005, z + 0.004),
            (cx + sx * hsize.x * 0.030, y, z + 0.003),
            (cx + sx * hsize.x * 0.082, y + 0.0015, z - 0.003),
        ]
        obj = add_poly_curve(f"Brow_{side}", pts, hair_mat, hsize.x * 0.0032)
        parent_to_bone_keep_world(obj, armature, head_bone)
        brows.append(obj)
    return brows


def add_hair_cap(hmin, hmax, bmax, extent, armature, head_bone, hair_mat):
    hcenter = (hmin + hmax) * 0.5
    hsize = hmax - hmin
    center = Vector((hcenter.x, hcenter.y + hsize.y * 0.015, hcenter.z + hsize.z * 0.020))
    radii = Vector((hsize.x * 0.500, hsize.y * 0.500, hsize.z * 0.505))

    bpy.ops.mesh.primitive_uv_sphere_add(segments=72, ring_count=36, location=center)
    cap = bpy.context.object
    cap.name = "CloseCroppedHairCap"
    cap.scale = radii
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    mesh = cap.data
    bpy.context.view_layer.objects.active = cap
    cap.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")

    lower_back = bmax.z - extent.z * 0.075
    front_hairline = bmax.z - extent.z * 0.044
    front_split_y = hcenter.y - hsize.y * 0.035
    for v in mesh.vertices:
        wp = cap.matrix_world @ v.co
        remove = wp.z < lower_back
        if wp.y < front_split_y and wp.z < front_hairline:
            remove = True
        if remove:
            v.select = True

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")

    solid = cap.modifiers.new("HairThickness", "SOLIDIFY")
    solid.thickness = 0.0018
    solid.offset = 0.0
    bevel = cap.modifiers.new("HairSoftEdge", "BEVEL")
    bevel.width = 0.0007
    bevel.segments = 2
    cap.data.materials.append(hair_mat)
    bpy.ops.object.shade_smooth()
    parent_to_bone_keep_world(cap, armature, head_bone)
    return cap


def setup_render_scene(center, extent):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 800
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scene.world.color = (0.010, 0.012, 0.018)

    camera_data = bpy.data.cameras.new("CinematicCamera")
    camera = bpy.data.objects.new("CinematicCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "PERSP"
    camera_data.lens = 72

    def area(name, loc, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
        return obj

    area("Key", center + Vector((-2.4, -3.2, 2.2)), 900, 2.3, (1.0, 0.80, 0.69))
    area("Fill", center + Vector((2.3, -2.2, 1.2)), 410, 2.0, (0.61, 0.75, 1.0))
    area("Rim", center + Vector((1.4, 2.7, 2.5)), 780, 1.7, (0.75, 0.84, 1.0))
    area("TopSoft", center + Vector((0.0, 0.2, 3.8)), 310, 2.7, (1.0, 0.94, 0.88))
    return camera


def point_camera(camera, location, target):
    camera.location = location
    camera.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()


def render_ring(camera, center, extent, prefix, target_z, radius_factor, angles):
    paths = []
    radius = max(extent.x, extent.y) * radius_factor
    target = Vector((center.x, center.y - 0.015, target_z))
    for deg in angles:
        a = math.radians(deg)
        loc = Vector((center.x + radius * math.sin(a), center.y - radius * math.cos(a), target_z + extent.z * 0.015))
        point_camera(camera, loc, target)
        path = OUT / f"{prefix}_{deg:03d}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        paths.append(path.name)
    return paths


def export_glb():
    path = OUT / "mhr_v1.0.1_cinematic_appearance_prototype.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", export_apply=False,
        export_animations=True, export_skins=True, export_morph=True,
    )
    return path


def main():
    if not FBX.exists():
        raise FileNotFoundError(FBX)
    reset_scene()
    bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True, automatic_bone_orientation=False)

    meshes = mesh_objects()
    if not meshes:
        raise RuntimeError("MHR lod1.fbx imported without mesh objects")
    bmin, bmax = world_bounds(meshes)
    center = (bmin + bmax) * 0.5
    extent = bmax - bmin
    hmin, hmax = anatomical_head_bounds(meshes, center, bmax, extent)

    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    armature = armatures[0] if armatures else None
    head_bone = find_head_bone(armature)

    mats = {
        "skin": make_skin_material(),
        "sclera": make_simple_material("Sclera", (0.76, 0.77, 0.73), 0.22),
        "iris": make_simple_material("IrisBrown", (0.050, 0.016, 0.006), 0.31),
        "pupil": make_simple_material("Pupil", (0.0025, 0.0025, 0.0025), 0.08),
        "catchlight": make_simple_material("Catchlight", (0.96, 0.96, 0.96), 0.04),
        "hair": make_hair_material(),
    }
    assign_material(meshes, mats["skin"])

    left_parts, left_center, eye_radii = add_eye_from_head_bounds("L", hmin, hmax, armature, head_bone, mats)
    right_parts, right_center, _ = add_eye_from_head_bounds("R", hmin, hmax, armature, head_bone, mats)
    brows = add_eyebrows(hmin, hmax, armature, head_bone, mats["hair"])
    hair = add_hair_cap(hmin, hmax, bmax, extent, armature, head_bone, mats["hair"])

    camera = setup_render_scene(center, extent)
    full_views = render_ring(camera, center, extent, "view", center.z + extent.z * 0.03, 2.85, [0, 45, 90, 135, 180, 225, 270, 315])
    face_views = render_ring(camera, center, extent, "face", bmax.z - extent.z * 0.09, 0.48, [0, 45, 90, 180, 270, 315])

    glb = export_glb()
    copied_fbx = OUT / "mhr_v1.0.1_lod1_source_rigged.fbx"
    shutil.copy2(FBX, copied_fbx)

    shapekey_count = 0
    for obj in meshes:
        if obj.data.shape_keys and obj.data.shape_keys.key_blocks:
            shapekey_count += max(0, len(obj.data.shape_keys.key_blocks) - 1)

    metrics = {
        "model": "Meta Momentum Human Rig (MHR)",
        "source_version": "v1.0.1",
        "prototype": "cinematic_appearance_v3",
        "source_asset": "assets/lod1.fbx",
        "mesh_object_count_source": len(meshes),
        "armature_object_count": len(armatures),
        "bone_count": sum(len(a.data.bones) for a in armatures),
        "shape_key_count": shapekey_count,
        "head_bone": head_bone,
        "estimated_head_bounds_min": list(hmin),
        "estimated_head_bounds_max": list(hmax),
        "left_eye_center": list(left_center),
        "right_eye_center": list(right_center),
        "eye_radii": list(eye_radii),
        "added_objects": [o.name for o in left_parts + right_parts + brows + [hair]],
        "materials": [m.name for m in mats.values()],
        "full_body_views": full_views,
        "face_views": face_views,
        "glb": glb.name,
        "source_fbx_copy": copied_fbx.name,
        "gate_status": "READY_FOR_GPT_CINEMATIC_APPEARANCE_REVIEW",
        "formal_final_character": False,
        "limitations": [
            "No identity/reference face fitting was performed because no target identity image was provided.",
            "Hair remains a procedural close-cropped scalp prototype, not production groom strands/cards.",
            "Procedural skin/hair microdetail is Blender-render evidence; glTF cannot preserve every procedural node.",
            "Full facial/body animation deformation acceptance remains a later gate.",
        ],
    }
    (OUT / "appearance_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (OUT / "README.txt").write_text(
        "MHR v1.0.1 Cinematic Appearance Prototype Gate v3\n"
        "Eyes and scalp are derived from measured anatomical head bounds; source topology/rig/morphs remain intact.\n"
        "This is not a final cinematic identity or production groom.\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
