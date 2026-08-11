from __future__ import annotations

import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
FBX = ROOT / "assets" / "lod1.fbx"
OUT = ROOT / "artifacts" / "mhr-eye-topology-probe"
OUT.mkdir(parents=True, exist_ok=True)


def v3(v):
    return [float(v.x), float(v.y), float(v.z)]


def bone_head_world(arm, name):
    bone = arm.data.bones.get(name)
    if bone is None:
        raise RuntimeError(f"missing bone {name}")
    return arm.matrix_world @ bone.head_local


def eye_local_vertex_sets(obj, eye_point):
    mw = obj.matrix_world
    upper, lower, all_local = [], [], []
    for vertex in obj.data.vertices:
        p = mw @ vertex.co
        # Compact eyelid/eye neighborhood around the native eye-null marker.
        if abs(p.x - eye_point.x) <= 0.024 and abs(p.y - eye_point.y) <= 0.018 and abs(p.z - eye_point.z) <= 0.016:
            all_local.append(vertex.index)
            if p.z >= eye_point.z + 0.0010:
                upper.append(vertex.index)
            elif p.z <= eye_point.z - 0.0010:
                lower.append(vertex.index)
    return {"all": all_local, "upper": upper, "lower": lower}


def world_delta(obj, basis_co, shape_co):
    return obj.matrix_world.to_3x3() @ (shape_co - basis_co)


def mean(values):
    return sum(values) / len(values) if values else 0.0


def shape_metrics(obj, basis, shape, eye_sets):
    per_eye = {}
    opening_scores = []
    local_magnitudes = []
    for eye_name, sets in eye_sets.items():
        upper_dz = [world_delta(obj, basis.data[i].co, shape.data[i].co).z for i in sets["upper"]]
        lower_dz = [world_delta(obj, basis.data[i].co, shape.data[i].co).z for i in sets["lower"]]
        local_mag = [world_delta(obj, basis.data[i].co, shape.data[i].co).length for i in sets["all"]]
        opening = mean(upper_dz) - mean(lower_dz)
        per_eye[eye_name] = {
            "upper_vertex_count": len(sets["upper"]),
            "lower_vertex_count": len(sets["lower"]),
            "local_vertex_count": len(sets["all"]),
            "opening_score_at_plus_one_m": opening,
            "mean_local_displacement_m": mean(local_mag),
            "max_local_displacement_m": max(local_mag, default=0.0),
        }
        opening_scores.append(opening)
        local_magnitudes.extend(local_mag)

    global_sample = []
    step = max(1, len(obj.data.vertices) // 1500)
    for i in range(0, len(obj.data.vertices), step):
        global_sample.append(world_delta(obj, basis.data[i].co, shape.data[i].co).length)

    bilateral_opening = mean(opening_scores)
    return {
        "bilateral_opening_score_at_plus_one_m": bilateral_opening,
        "recommended_test_value": 1.0 if bilateral_opening >= 0 else -1.0,
        "predicted_opening_at_recommended_value_m": abs(bilateral_opening),
        "mean_eye_local_displacement_m": mean(local_magnitudes),
        "max_eye_local_displacement_m": max(local_magnitudes, default=0.0),
        "mean_global_sample_displacement_m": mean(global_sample),
        "eyes": per_eye,
    }


def make_material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.70
    return mat


def setup_render(body, target):
    body.data.materials.clear()
    body.data.materials.append(make_material("ShapeProbeSkin", (0.36, 0.19, 0.13)))
    for poly in body.data.polygons:
        poly.material_index = 0

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 520
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.012, 0.014, 0.018)

    cam_data = bpy.data.cameras.new("ShapeProbeCamera")
    cam = bpy.data.objects.new("ShapeProbeCamera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens = 88
    cam.location = Vector((0.0, -0.44, target.z + 0.002))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()

    def area(name, loc, energy, size):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()

    area("Key", target + Vector((-0.22, -0.34, 0.20)), 260, 0.50)
    area("Fill", target + Vector((0.25, -0.26, 0.06)), 150, 0.45)
    area("Top", target + Vector((0.0, 0.05, 0.34)), 110, 0.55)


def reset_shape_values(keys):
    for key in keys.key_blocks[1:]:
        key.value = 0.0


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True, automatic_bone_orientation=False)

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if len(meshes) != 1 or not arms:
        raise RuntimeError(f"Unexpected MHR import: meshes={len(meshes)} arms={len(arms)}")
    body, arm = meshes[0], arms[0]
    keys = body.data.shape_keys
    if keys is None or len(keys.key_blocks) < 2:
        raise RuntimeError("MHR body has no shape keys")

    left = bone_head_world(arm, "l_eye_null")
    right = bone_head_world(arm, "r_eye_null")
    target = (left + right) * 0.5
    eye_sets = {
        "left": eye_local_vertex_sets(body, left),
        "right": eye_local_vertex_sets(body, right),
    }

    basis = keys.key_blocks[0]
    metrics = []
    for shape in keys.key_blocks[1:]:
        item = {"name": shape.name, **shape_metrics(body, basis, shape, eye_sets)}
        metrics.append(item)

    ranked = sorted(metrics, key=lambda item: item["predicted_opening_at_recommended_value_m"], reverse=True)
    top = ranked[:10]

    setup_render(body, target)
    rendered = []

    reset_shape_values(keys)
    basis_path = OUT / "eye_shape_basis.png"
    bpy.context.scene.render.filepath = str(basis_path)
    bpy.ops.render.render(write_still=True)
    rendered.append({"name": "Basis", "value": 0.0, "image": basis_path.name})

    for rank, item in enumerate(top[:8], start=1):
        reset_shape_values(keys)
        key = keys.key_blocks[item["name"]]
        key.slider_min = -1.0
        key.slider_max = 1.0
        value = item["recommended_test_value"]
        key.value = value
        path = OUT / f"eye_shape_rank_{rank:02d}_{item['name']}_{'plus' if value > 0 else 'minus'}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        rendered.append({"rank": rank, "name": item["name"], "value": value, "image": path.name})

    reset_shape_values(keys)
    result = {
        "left_eye_null": v3(left),
        "right_eye_null": v3(right),
        "eye_vertex_sets": {name: {k: len(v) for k, v in sets.items()} for name, sets in eye_sets.items()},
        "shape_count": len(metrics),
        "ranking_metric": "bilateral vertical lid separation inferred from eye-local vertices; positive means upper neighborhood moves up relative to lower neighborhood",
        "top_opening_candidates": top,
        "all_shape_metrics": metrics,
        "rendered_candidates": rendered,
        "topology_mutated": False,
    }
    out = OUT / "mhr_eye_shape_response_probe.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({
        "eye_vertex_sets": result["eye_vertex_sets"],
        "top_opening_candidates": top,
        "rendered_candidates": rendered,
    }, indent=2))


if __name__ == "__main__":
    main()
