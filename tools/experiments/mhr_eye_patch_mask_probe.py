from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
FBX = ROOT / "assets" / "lod1.fbx"
OUT = ROOT / "artifacts" / "mhr-eye-topology-probe"
OUT.mkdir(parents=True, exist_ok=True)


def material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.62
    return mat


def bone_head_world(arm, name):
    b = arm.data.bones.get(name)
    if b is None:
        raise RuntimeError(f"Missing bone: {name}")
    return arm.matrix_world @ b.head_local


def reset_materials(obj, base_index=0):
    for poly in obj.data.polygons:
        poly.material_index = base_index


def candidate_polygons(obj, eye_point, dx, dz, dy, normal_y_max):
    mw = obj.matrix_world
    normal_m = mw.to_3x3()
    selected = []
    centers = []
    for poly in obj.data.polygons:
        c = mw @ poly.center
        nx = (c.x - eye_point.x) / dx
        nz = (c.z - eye_point.z) / dz
        if nx * nx + nz * nz > 1.0:
            continue
        if abs(c.y - eye_point.y) > dy:
            continue
        n = (normal_m @ poly.normal).normalized()
        if n.y > normal_y_max:
            continue
        selected.append(poly.index)
        centers.append(c)
    return selected, centers


def bounds(points):
    if not points:
        return None
    return {
        "min": [min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)],
        "max": [max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)],
    }


def apply_mask(obj, left_indices, right_indices):
    reset_materials(obj, 0)
    for i in left_indices:
        obj.data.polygons[i].material_index = 1
    for i in right_indices:
        obj.data.polygons[i].material_index = 2


def setup_render(target):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 760
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.018, 0.018, 0.022)

    cam_data = bpy.data.cameras.new("MaskCamera")
    cam = bpy.data.objects.new("MaskCamera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens = 82

    def area(name, loc, energy, size):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()

    area("Key", target + Vector((-0.25, -0.45, 0.22)), 700, 0.55)
    area("Fill", target + Vector((0.30, -0.30, 0.08)), 420, 0.50)
    area("Top", target + Vector((0.0, 0.0, 0.42)), 320, 0.60)
    return cam


def point_camera(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()


def render_pair(cam, target, prefix):
    views = {
        "front": Vector((0.0, -0.44, target.z + 0.005)),
        "three_quarter": Vector((0.24, -0.39, target.z + 0.015)),
    }
    names = []
    for label, loc in views.items():
        point_camera(cam, loc, target)
        path = OUT / f"{prefix}_{label}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        names.append(path.name)
    return names


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True, automatic_bone_orientation=False)

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if len(meshes) != 1 or not arms:
        raise RuntimeError(f"Unexpected MHR import: meshes={len(meshes)} arms={len(arms)}")
    body = meshes[0]
    arm = arms[0]

    left = bone_head_world(arm, "l_eye_null")
    right = bone_head_world(arm, "r_eye_null")
    target = (left + right) * 0.5

    body.data.materials.clear()
    body.data.materials.append(material("MaskBase", (0.23, 0.23, 0.25)))
    body.data.materials.append(material("LeftEyeCandidate", (0.02, 0.95, 0.95)))
    body.data.materials.append(material("RightEyeCandidate", (0.95, 0.03, 0.62)))

    profiles = {
        "strict": {"dx": 0.0135, "dz": 0.0062, "dy": 0.0055, "normal_y_max": -0.78},
        "broad": {"dx": 0.0175, "dz": 0.0090, "dy": 0.0075, "normal_y_max": -0.45},
    }

    cam = setup_render(target)
    result = {
        "left_eye_null": list(left),
        "right_eye_null": list(right),
        "profiles": {},
        "topology_mutated": False,
    }

    for name, p in profiles.items():
        left_idx, left_centers = candidate_polygons(body, left, **p)
        right_idx, right_centers = candidate_polygons(body, right, **p)
        apply_mask(body, left_idx, right_idx)
        images = render_pair(cam, target, f"eye_mask_{name}")
        result["profiles"][name] = {
            **p,
            "left_polygon_count": len(left_idx),
            "right_polygon_count": len(right_idx),
            "left_polygon_indices": left_idx,
            "right_polygon_indices": right_idx,
            "left_bounds": bounds(left_centers),
            "right_bounds": bounds(right_centers),
            "images": images,
        }

    out = OUT / "mhr_eye_patch_mask_probe.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
