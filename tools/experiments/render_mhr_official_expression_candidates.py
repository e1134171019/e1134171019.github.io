from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUT = ROOT / "artifacts" / "mhr-official-expression-gate"
PROBE = OUT / "mhr_official_expression_probe.json"


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def parse_obj(path):
    vertices = []
    faces = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()[:4]
                vertices.append((float(x), float(y), float(z)))
            elif line.startswith("f "):
                parts = line.split()[1:4]
                faces.append(tuple(int(p.split("/")[0]) - 1 for p in parts))
    return vertices, faces


def make_material(name, rgb, roughness=0.52):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if bsdf.inputs.get("Subsurface Weight"):
        bsdf.inputs["Subsurface Weight"].default_value = 0.045
    return mat


def create_mesh(name, obj_path, material):
    vertices, faces = parse_obj(obj_path)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def setup_scene(target):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 880
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.008, 0.010, 0.014)
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

    cd = bpy.data.cameras.new("ExpressionCamera")
    cam = bpy.data.objects.new("ExpressionCamera", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cd.lens = 82

    def area(name, loc, energy, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = loc
        obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()

    # MHR TorchScript coordinates are X left/right, Y up, Z forward.
    area("Key", target + Vector((-0.28, 0.20, 0.38)), 230, 0.55, (1.0, 0.80, 0.68))
    area("Fill", target + Vector((0.25, 0.05, 0.32)), 120, 0.50, (0.62, 0.76, 1.0))
    area("Top", target + Vector((0.0, 0.36, 0.15)), 85, 0.60, (1.0, 0.94, 0.88))
    return cam


def point_camera(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()


def render_candidate(name, obj_path, target):
    reset_scene()
    skin = make_material("DiagnosticSkin", (0.30, 0.125, 0.078), 0.54)
    create_mesh(name, obj_path, skin)
    cam = setup_scene(target)
    views = {
        "front": target + Vector((0.0, 0.005, 0.42)),
        "three_quarter": target + Vector((0.24, 0.035, 0.36)),
        "side": target + Vector((0.40, 0.015, 0.12)),
    }
    images = []
    for label, loc in views.items():
        point_camera(cam, loc, target)
        path = OUT / f"render_{name}_{label}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        images.append(path.name)
    return images


def main():
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    left = Vector([v / 100.0 for v in probe["left_eye_locator"]["position_cm"]])
    right = Vector([v / 100.0 for v in probe["right_eye_locator"]["position_cm"]])
    target = (left + right) * 0.5

    results = []
    for item in probe["candidate_meshes"]:
        path = OUT / item["obj"]
        images = render_candidate(item["name"], path, target)
        results.append({"name": item["name"], "images": images, "meta": item["meta"]})

    payload = {
        "target_eye_midpoint_m": list(target),
        "candidate_count": len(results),
        "candidates": results,
        "formal_final_character": False,
        "gate_status": "READY_FOR_GPT_OFFICIAL_EXPRESSION_VISUAL_REVIEW",
    }
    (OUT / "mhr_official_expression_render_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
