from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
FBX = ROOT / "assets" / "lod1.fbx"
OUT = ROOT / "artifacts" / "mhr-eye-aperture-gate"
OUT.mkdir(parents=True, exist_ok=True)

PROFILES = {
    "narrow": {"dx": 0.0125, "dz": 0.0048, "dy": 0.0045, "normal_y_max": -0.80},
    "strict": {"dx": 0.0135, "dz": 0.0062, "dy": 0.0055, "normal_y_max": -0.78},
}


def v3(v):
    return [float(v.x), float(v.y), float(v.z)]


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_mhr():
    bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True, automatic_bone_orientation=False)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if len(meshes) != 1 or not arms:
        raise RuntimeError(f"Unexpected import meshes={len(meshes)} armatures={len(arms)}")
    return meshes[0], arms[0]


def bone_head_world(arm, name):
    bone = arm.data.bones.get(name)
    if bone is None:
        raise RuntimeError(f"Missing bone {name}")
    return arm.matrix_world @ bone.head_local


def make_material(name, rgb, roughness=0.5, specular_ior=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    if bsdf.inputs.get("Roughness"):
        bsdf.inputs["Roughness"].default_value = roughness
    if bsdf.inputs.get("Specular IOR Level"):
        bsdf.inputs["Specular IOR Level"].default_value = specular_ior
    return mat


def apply_skin(body):
    skin = make_material("DiagnosticSkin", (0.31, 0.135, 0.085), 0.52, 0.30)
    body.data.materials.clear()
    body.data.materials.append(skin)
    for poly in body.data.polygons:
        poly.material_index = 0
    return skin


def candidate_polygons(body, eye_null, profile):
    mw = body.matrix_world
    nm = mw.to_3x3()
    out = []
    for poly in body.data.polygons:
        c = mw @ poly.center
        nx = (c.x - eye_null.x) / profile["dx"]
        nz = (c.z - eye_null.z) / profile["dz"]
        if nx * nx + nz * nz > 1.0:
            continue
        if abs(c.y - eye_null.y) > profile["dy"]:
            continue
        n = (nm @ poly.normal).normalized()
        if n.y > profile["normal_y_max"]:
            continue
        out.append(poly.index)
    return out


def delete_faces_only(body, polygon_indices):
    wanted = set(polygon_indices)
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for poly in body.data.polygons:
        poly.select = poly.index in wanted
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="ONLY_FACE")
    bpy.ops.object.mode_set(mode="OBJECT")


def add_uv_sphere(name, location, scale, material, segments=64, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def parent_to_bone_keep_world(obj, arm, bone_name):
    mw = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = mw


def add_eye_system(side, arm, eye_bone, eye_null, mats):
    center = bone_head_world(arm, eye_bone)
    # Native MHR eye-bone centers are ~64 mm apart. A ~12 mm globe radius is anatomically plausible.
    globe_r = 0.0120
    globe = add_uv_sphere(f"{side}_EyeGlobe", center, (globe_r, globe_r, globe_r), mats["sclera"])

    # Front is -Y in this asset. Keep iris nearly tangent to the globe front.
    iris_y = center.y - globe_r * 0.985
    iris = add_uv_sphere(
        f"{side}_Iris",
        Vector((center.x, iris_y, center.z)),
        (0.0052, 0.00075, 0.0052),
        mats["iris"], 48, 24,
    )
    pupil = add_uv_sphere(
        f"{side}_Pupil",
        Vector((center.x, iris_y - 0.00055, center.z)),
        (0.0022, 0.00035, 0.0022),
        mats["pupil"], 40, 20,
    )
    catch = add_uv_sphere(
        f"{side}_Catchlight",
        Vector((center.x - (0.0016 if side == "L" else -0.0016), iris_y - 0.0008, center.z + 0.0018)),
        (0.00070, 0.00025, 0.00070),
        mats["catch"], 24, 12,
    )
    for obj in (globe, iris, pupil, catch):
        parent_to_bone_keep_world(obj, arm, eye_bone)
    return {
        "center": v3(center),
        "null": v3(eye_null),
        "globe_radius": globe_r,
        "front_y": center.y - globe_r,
    }


def setup_render(target):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 920
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.008, 0.010, 0.014)
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

    cd = bpy.data.cameras.new("ApertureCamera")
    cam = bpy.data.objects.new("ApertureCamera", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cd.lens = 78

    def area(name, loc, energy, size, color):
        d = bpy.data.lights.new(name, "AREA")
        d.energy = energy
        d.size = size
        d.color = color
        o = bpy.data.objects.new(name, d)
        scene.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()

    area("Key", target + Vector((-0.30, -0.42, 0.25)), 260, 0.58, (1.0, 0.80, 0.68))
    area("Fill", target + Vector((0.28, -0.32, 0.07)), 125, 0.48, (0.62, 0.76, 1.0))
    area("Top", target + Vector((0.0, 0.04, 0.42)), 95, 0.60, (1.0, 0.94, 0.88))
    return cam


def point_camera(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()


def render_views(cam, target, prefix):
    views = {
        "front": Vector((0.0, -0.45, target.z + 0.002)),
        "three_quarter": Vector((0.24, -0.39, target.z + 0.012)),
        "side": Vector((0.40, -0.14, target.z + 0.010)),
    }
    images = []
    for label, loc in views.items():
        point_camera(cam, loc, target)
        path = OUT / f"{prefix}_{label}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        images.append(path.name)
    return images


def run_profile(name, profile):
    reset_scene()
    body, arm = import_mhr()
    source_vertices = len(body.data.vertices)
    source_polygons = len(body.data.polygons)
    source_shape_keys = max(0, len(body.data.shape_keys.key_blocks) - 1) if body.data.shape_keys else 0
    source_bones = len(arm.data.bones)

    left_null = bone_head_world(arm, "l_eye_null")
    right_null = bone_head_world(arm, "r_eye_null")
    target = (left_null + right_null) * 0.5

    apply_skin(body)
    left_faces = candidate_polygons(body, left_null, profile)
    right_faces = candidate_polygons(body, right_null, profile)
    delete_faces_only(body, left_faces + right_faces)

    after_vertices = len(body.data.vertices)
    after_polygons = len(body.data.polygons)
    after_shape_keys = max(0, len(body.data.shape_keys.key_blocks) - 1) if body.data.shape_keys else 0
    after_bones = len(arm.data.bones)

    if after_vertices != source_vertices:
        raise RuntimeError(f"Vertex count changed: {source_vertices} -> {after_vertices}")
    if after_shape_keys != source_shape_keys:
        raise RuntimeError(f"Shape key regression: {source_shape_keys} -> {after_shape_keys}")
    if after_bones != source_bones:
        raise RuntimeError(f"Bone regression: {source_bones} -> {after_bones}")

    mats = {
        "sclera": make_material("Sclera", (0.76, 0.76, 0.70), 0.22, 0.55),
        "iris": make_material("IrisBrown", (0.055, 0.018, 0.006), 0.28, 0.48),
        "pupil": make_material("Pupil", (0.002, 0.002, 0.002), 0.16, 0.45),
        "catch": make_material("Catchlight", (0.95, 0.95, 0.95), 0.06, 0.60),
    }
    left_eye = add_eye_system("L", arm, "l_eye", left_null, mats)
    right_eye = add_eye_system("R", arm, "r_eye", right_null, mats)

    cam = setup_render(target)
    images = render_views(cam, target, f"eye_aperture_{name}")

    return {
        "profile": profile,
        "left_removed_faces": len(left_faces),
        "right_removed_faces": len(right_faces),
        "source_vertex_count": source_vertices,
        "after_vertex_count": after_vertices,
        "source_polygon_count": source_polygons,
        "after_polygon_count": after_polygons,
        "source_shape_key_count": source_shape_keys,
        "after_shape_key_count": after_shape_keys,
        "source_bone_count": source_bones,
        "after_bone_count": after_bones,
        "left_eye": left_eye,
        "right_eye": right_eye,
        "images": images,
    }


def main():
    if not FBX.exists():
        raise FileNotFoundError(FBX)
    results = {name: run_profile(name, profile) for name, profile in PROFILES.items()}
    payload = {
        "model": "MHR v1.0.1 lod1.fbx",
        "gate": "controlled_eye_aperture_diagnostic",
        "formal_final_character": False,
        "topology_contract": "faces-only deletion; vertices, shape keys and armature must remain numerically unchanged",
        "profiles": results,
    }
    path = OUT / "mhr_eye_aperture_gate.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
