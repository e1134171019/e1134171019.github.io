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
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    return Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))


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
    principled_input(bsdf, "Base Color", (0.30, 0.125, 0.070, 1.0))
    principled_input(bsdf, "Roughness", 0.50)
    principled_input(bsdf, "IOR", 1.42)
    principled_input(bsdf, "Subsurface Weight", 0.075)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 125.0
    noise.inputs["Detail"].default_value = 4.5
    noise.inputs["Roughness"].default_value = 0.67

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.10
    bump.inputs["Distance"].default_value = 0.0012
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


def assign_material(objects, mat):
    for obj in objects:
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def local_front_y(meshes, x, z, dx=0.021, dz=0.018):
    ys = []
    for obj in meshes:
        for p in world_vertices(obj):
            if abs(p.x - x) <= dx and abs(p.z - z) <= dz:
                ys.append(p.y)
    if not ys:
        raise RuntimeError(f"Could not estimate face surface near eye x={x:.4f} z={z:.4f}")
    return min(ys)


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
    for n in ["head", "Head", "HEAD", "b_head", "joint_head", "c_head"]:
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


def add_eye(meshes, side_x, eye_z, armature, head_bone, mats):
    surface_y = local_front_y(meshes, side_x, eye_z)
    center_y = surface_y + 0.0108
    sclera = add_uv_sphere(
        f"Eye_{'L' if side_x > 0 else 'R'}_Sclera",
        (side_x, center_y, eye_z),
        (0.0162, 0.0120, 0.0132),
        mats["sclera"],
    )
    iris_y = surface_y - 0.0010
    iris = add_uv_sphere(
        f"Eye_{'L' if side_x > 0 else 'R'}_Iris",
        (side_x, iris_y, eye_z),
        (0.0060, 0.0018, 0.0060),
        mats["iris"], 40, 20,
    )
    pupil = add_uv_sphere(
        f"Eye_{'L' if side_x > 0 else 'R'}_Pupil",
        (side_x, iris_y - 0.0012, eye_z),
        (0.0025, 0.0008, 0.0025),
        mats["pupil"], 32, 16,
    )
    highlight = add_uv_sphere(
        f"Eye_{'L' if side_x > 0 else 'R'}_Catchlight",
        (side_x - 0.0033, iris_y - 0.0018, eye_z + 0.0033),
        (0.0010, 0.00055, 0.0010),
        mats["catchlight"], 24, 12,
    )
    for obj in (sclera, iris, pupil, highlight):
        parent_to_bone_keep_world(obj, armature, head_bone)
    return [sclera, iris, pupil, highlight], surface_y


def add_poly_curve(name, points, material, bevel_depth=0.0018):
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


def add_eyebrows(eye_x, eye_z, eye_surface_y, armature, head_bone, hair_mat):
    brows = []
    for sx in (-1, 1):
        cx = eye_x * sx
        y = eye_surface_y - 0.0028
        pts = [
            (cx - 0.020 * sx, y + 0.0005, eye_z + 0.024),
            (cx - 0.006 * sx, y - 0.0004, eye_z + 0.029),
            (cx + 0.010 * sx, y, eye_z + 0.028),
            (cx + 0.025 * sx, y + 0.0010, eye_z + 0.023),
        ]
        obj = add_poly_curve(f"Brow_{'L' if sx > 0 else 'R'}", pts, hair_mat, 0.00145)
        parent_to_bone_keep_world(obj, armature, head_bone)
        brows.append(obj)
    return brows


def anatomical_head_bounds(meshes, body_center, bmax, extent):
    # Restrict to the central upper skull so shoulders/raised arms cannot inflate hair width.
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


def add_hair_cap(meshes, body_center, bmax, extent, armature, head_bone, hair_mat):
    hmin, hmax = anatomical_head_bounds(meshes, body_center, bmax, extent)
    hcenter = (hmin + hmax) * 0.5
    hsize = hmax - hmin

    # Slightly enlarge the actual skull rather than deriving width from the upper torso.
    center = Vector((hcenter.x, hcenter.y + hsize.y * 0.03, hcenter.z + hsize.z * 0.10))
    radii = Vector((hsize.x * 0.54, hsize.y * 0.55, hsize.z * 0.61))

    bpy.ops.mesh.primitive_uv_sphere_add(segments=72, ring_count=36, location=center)
    cap = bpy.context.object
    cap.name = "ShortHairCap"
    cap.scale = radii
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    mesh = cap.data
    bpy.context.view_layer.objects.active = cap
    cap.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")

    # Back/sides may extend lower; the front hairline stays well above the eyes.
    lower_back = bmax.z - extent.z * 0.105
    front_hairline = bmax.z - extent.z * 0.050
    front_split_y = hcenter.y - hsize.y * 0.10
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
    solid.thickness = 0.0028
    solid.offset = 0.0
    bevel = cap.modifiers.new("HairSoftEdge", "BEVEL")
    bevel.width = 0.0010
    bevel.segments = 2
    cap.data.materials.append(hair_mat)
    bpy.ops.object.shade_smooth()
    parent_to_bone_keep_world(cap, armature, head_bone)
    return cap, hmin, hmax


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
    scene.render.image_settings.color_mode = "RGBA"
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

    area("Key", center + Vector((-2.4, -3.2, 2.2)), 940, 2.3, (1.0, 0.80, 0.68))
    area("Fill", center + Vector((2.3, -2.2, 1.2)), 430, 2.0, (0.60, 0.74, 1.0))
    area("Rim", center + Vector((1.4, 2.7, 2.5)), 820, 1.7, (0.74, 0.84, 1.0))
    area("TopSoft", center + Vector((0.0, 0.2, 3.8)), 330, 2.7, (1.0, 0.94, 0.88))
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
        filepath=str(path),
        export_format="GLB",
        export_apply=False,
        export_animations=True,
        export_skins=True,
        export_morph=True,
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

    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    armature = armatures[0] if armatures else None
    head_bone = find_head_bone(armature)

    mats = {
        "skin": make_skin_material(),
        "sclera": make_simple_material("Sclera", (0.76, 0.77, 0.73), 0.20),
        "iris": make_simple_material("IrisBrown", (0.060, 0.021, 0.008), 0.30),
        "pupil": make_simple_material("Pupil", (0.003, 0.003, 0.003), 0.08),
        "catchlight": make_simple_material("Catchlight", (0.96, 0.96, 0.96), 0.04),
        "hair": make_simple_material("HairDarkBrown", (0.014, 0.006, 0.003), 0.42),
    }
    assign_material(meshes, mats["skin"])

    eye_x = extent.x * 0.0275
    eye_z = bmax.z - extent.z * 0.073
    left_parts, left_surface_y = add_eye(meshes, eye_x, eye_z, armature, head_bone, mats)
    right_parts, right_surface_y = add_eye(meshes, -eye_x, eye_z, armature, head_bone, mats)
    brows = add_eyebrows(eye_x, eye_z, min(left_surface_y, right_surface_y), armature, head_bone, mats["hair"])
    hair, head_min, head_max = add_hair_cap(meshes, center, bmax, extent, armature, head_bone, mats["hair"])

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
        "prototype": "cinematic_appearance_v2",
        "source_asset": "assets/lod1.fbx",
        "source_license_file": "assets/LICENSE.txt",
        "mesh_object_count_source": len(meshes),
        "armature_object_count": len(armatures),
        "bone_count": sum(len(a.data.bones) for a in armatures),
        "shape_key_count": shapekey_count,
        "head_bone": head_bone,
        "eye_center_x": eye_x,
        "eye_center_z": eye_z,
        "estimated_head_bounds_min": list(head_min),
        "estimated_head_bounds_max": list(head_max),
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
            "Hair is a constrained procedural scalp-cap prototype, not production groom strands/cards.",
            "Procedural skin microdetail is Blender-render evidence; glTF export keeps portable PBR values but cannot preserve all Blender procedural nodes.",
            "Added eye/hair/brow objects are parented to the head bone; full deformation/animation acceptance remains a later gate.",
        ],
    }
    (OUT / "appearance_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (OUT / "README.txt").write_text(
        "MHR v1.0.1 Cinematic Appearance Prototype Gate v2\n"
        "Purpose: validate a traced MHR carrier with corrected anatomical hair bounds, eyes, brows and procedural skin.\n"
        "This remains an appearance prototype, not the final cinematic identity or production groom.\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
