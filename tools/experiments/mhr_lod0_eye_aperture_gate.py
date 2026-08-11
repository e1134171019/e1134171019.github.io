from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
FBX = ROOT / "assets" / "lod0.fbx"
OUT = ROOT / "artifacts" / "mhr-lod0-eye-gate"
OUT.mkdir(parents=True, exist_ok=True)

PROFILES = {
    "micro": {"dx": 0.0130, "dz": 0.0042, "depth": 0.0070},
    "natural": {"dx": 0.0155, "dz": 0.0055, "depth": 0.0075},
    "open": {"dx": 0.0170, "dz": 0.0065, "depth": 0.0080},
}


def v3(v):
    return [float(v.x), float(v.y), float(v.z)]


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_lod0():
    bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True, automatic_bone_orientation=False)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    if not meshes or not arms:
        raise RuntimeError(f"Unexpected LOD0 import meshes={len(meshes)} armatures={len(arms)}")
    body = max(meshes, key=lambda o: len(o.data.vertices))
    return body, arms[0], meshes, arms


def bone_head_world(arm, name):
    b = arm.data.bones.get(name)
    if b is None:
        raise RuntimeError(f"Missing bone {name}")
    return arm.matrix_world @ b.head_local


def make_material(name, rgb, roughness=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    if bsdf.inputs.get("Subsurface Weight"):
        bsdf.inputs["Subsurface Weight"].default_value = 0.04
    return m


def apply_skin(body):
    body.data.materials.clear()
    body.data.materials.append(make_material("LOD0DiagnosticSkin", (0.30, 0.125, 0.078), 0.54))
    for p in body.data.polygons:
        p.material_index = 0
        p.use_smooth = True


def almond_selected_faces(body, eye_null, profile):
    mw = body.matrix_world
    nm = mw.to_3x3()
    indices = []
    centers = []
    for poly in body.data.polygons:
        c = mw @ poly.center
        nx = abs((c.x - eye_null.x) / profile["dx"])
        if nx >= 1.0:
            continue
        # Pointed almond profile: maximum vertical opening at center, tapering to zero at canthi.
        half_height = profile["dz"] * (1.0 - nx ** 1.65) ** 0.70
        if abs(c.z - eye_null.z) > half_height:
            continue
        if abs(c.y - eye_null.y) > profile["depth"]:
            continue
        normal = (nm @ poly.normal).normalized()
        if normal.y > -0.15:
            continue
        indices.append(poly.index)
        centers.append(c)
    return indices, centers


def delete_faces_only(body, indices):
    selected = set(indices)
    bpy.context.view_layer.objects.active = body
    body.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for poly in body.data.polygons:
        poly.select = poly.index in selected
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="ONLY_FACE")
    bpy.ops.object.mode_set(mode="OBJECT")


def add_uv_sphere(name, loc, scale, material, segments=72, rings=36):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


def add_eye(side, eye_bone, eye_null, mats):
    # Place a spherical globe so its corneal front sits almost exactly at the native eye-null surface.
    radius = 0.0120
    center = Vector((eye_null.x, eye_null.y + radius * 0.96, eye_null.z))
    globe = add_uv_sphere(f"{side}_EyeGlobe", center, (radius, radius, radius), mats["sclera"])
    front_y = center.y - radius
    iris = add_uv_sphere(
        f"{side}_Iris",
        Vector((eye_null.x, front_y - 0.00020, eye_null.z)),
        (0.0051, 0.00065, 0.0051), mats["iris"], 56, 28,
    )
    pupil = add_uv_sphere(
        f"{side}_Pupil",
        Vector((eye_null.x, front_y - 0.00058, eye_null.z)),
        (0.00215, 0.00030, 0.00215), mats["pupil"], 40, 20,
    )
    catch = add_uv_sphere(
        f"{side}_Catchlight",
        Vector((eye_null.x + (-0.0016 if side == "L" else 0.0016), front_y - 0.00078, eye_null.z + 0.0017)),
        (0.00070, 0.00022, 0.00070), mats["catch"], 24, 12,
    )
    return {
        "eye_bone": v3(eye_bone),
        "eye_null": v3(eye_null),
        "visual_globe_center": v3(center),
        "radius": radius,
        "front_y": float(front_y),
        "objects": [globe.name, iris.name, pupil.name, catch.name],
    }


def setup_render(target):
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except Exception:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 980
    scene.render.resolution_y = 760
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.008, 0.010, 0.014)
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass

    cd = bpy.data.cameras.new("LOD0EyeCamera")
    cam = bpy.data.objects.new("LOD0EyeCamera", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cd.lens = 82

    def area(name, loc, energy, size, color):
        d = bpy.data.lights.new(name, "AREA")
        d.energy = energy
        d.size = size
        d.color = color
        o = bpy.data.objects.new(name, d)
        scene.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = (target - o.location).to_track_quat("-Z", "Y").to_euler()

    area("Key", target + Vector((-0.30, -0.42, 0.24)), 250, 0.58, (1.0, 0.80, 0.68))
    area("Fill", target + Vector((0.28, -0.30, 0.07)), 120, 0.50, (0.62, 0.76, 1.0))
    area("Top", target + Vector((0.0, 0.04, 0.42)), 90, 0.60, (1.0, 0.94, 0.88))
    return cam


def point_camera(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()


def render_views(cam, target, prefix):
    views = {
        "front": Vector((0.0, -0.46, target.z + 0.002)),
        "three_quarter": Vector((0.24, -0.40, target.z + 0.012)),
        "side": Vector((0.40, -0.15, target.z + 0.010)),
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
    body, arm, meshes, arms = import_lod0()
    source = {
        "mesh_object_count": len(meshes),
        "armature_object_count": len(arms),
        "body_vertex_count": len(body.data.vertices),
        "body_edge_count": len(body.data.edges),
        "body_polygon_count": len(body.data.polygons),
        "body_shape_key_count": max(0, len(body.data.shape_keys.key_blocks) - 1) if body.data.shape_keys else 0,
        "bone_count": len(arm.data.bones),
    }

    left_null = bone_head_world(arm, "l_eye_null")
    right_null = bone_head_world(arm, "r_eye_null")
    left_eye_bone = bone_head_world(arm, "l_eye")
    right_eye_bone = bone_head_world(arm, "r_eye")
    target = (left_null + right_null) * 0.5

    apply_skin(body)
    left_faces, left_centers = almond_selected_faces(body, left_null, profile)
    right_faces, right_centers = almond_selected_faces(body, right_null, profile)
    if len(left_faces) < 20 or len(right_faces) < 20:
        raise RuntimeError(f"Profile {name} selected too few faces L={len(left_faces)} R={len(right_faces)}")
    delete_faces_only(body, left_faces + right_faces)

    after = {
        "body_vertex_count": len(body.data.vertices),
        "body_polygon_count": len(body.data.polygons),
        "body_shape_key_count": max(0, len(body.data.shape_keys.key_blocks) - 1) if body.data.shape_keys else 0,
        "bone_count": len(arm.data.bones),
    }
    if after["body_vertex_count"] != source["body_vertex_count"]:
        raise RuntimeError("LOD0 vertex count changed during faces-only aperture")
    if after["body_shape_key_count"] != source["body_shape_key_count"]:
        raise RuntimeError("LOD0 shape key count changed during faces-only aperture")
    if after["bone_count"] != source["bone_count"]:
        raise RuntimeError("LOD0 bone count changed during aperture")

    mats = {
        "sclera": make_material("Sclera", (0.77, 0.77, 0.72), 0.20),
        "iris": make_material("IrisBrown", (0.052, 0.017, 0.006), 0.28),
        "pupil": make_material("Pupil", (0.002, 0.002, 0.002), 0.12),
        "catch": make_material("Catchlight", (0.96, 0.96, 0.96), 0.04),
    }
    left_eye = add_eye("L", left_eye_bone, left_null, mats)
    right_eye = add_eye("R", right_eye_bone, right_null, mats)
    cam = setup_render(target)
    images = render_views(cam, target, f"lod0_eye_{name}")

    def point_bounds(points):
        if not points:
            return None
        return {
            "min": v3(Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))),
            "max": v3(Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))),
        }

    return {
        "profile": profile,
        "source": source,
        "after": after,
        "left_removed_faces": len(left_faces),
        "right_removed_faces": len(right_faces),
        "left_aperture_bounds": point_bounds(left_centers),
        "right_aperture_bounds": point_bounds(right_centers),
        "left_eye": left_eye,
        "right_eye": right_eye,
        "images": images,
    }


def main():
    if not FBX.is_file():
        raise FileNotFoundError(FBX)
    results = {name: run_profile(name, profile) for name, profile in PROFILES.items()}
    payload = {
        "model": "MHR v1.0.1 lod0.fbx",
        "gate": "high_density_eye_aperture_diagnostic",
        "formal_final_character": False,
        "profiles": results,
        "decision_rule": "Visual front + 3/4 + side must show smooth anatomical eyelid boundary; otherwise MHR head is rejected as cinematic appearance carrier.",
    }
    (OUT / "mhr_lod0_eye_gate.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
