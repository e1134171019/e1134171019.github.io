from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUT = ROOT / "artifacts" / "mhr-human-carrier-gate"
OUT.mkdir(parents=True, exist_ok=True)
FBX = ROOT / "assets" / "lod1.fbx"


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        pass


def mesh_objects():
    return [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]


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


def setup_material(objects):
    mat = bpy.data.materials.new("GateNeutralGray")
    mat.diffuse_color = (0.42, 0.42, 0.42, 1.0)
    mat.roughness = 0.72
    for obj in objects:
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            for i in range(len(obj.data.materials)):
                obj.data.materials[i] = mat


def setup_scene(center: Vector, extent: Vector):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.display.shading.light = "STUDIO"
    scene.display.shading.studio_light = "rim.sl"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.curvature_ridge_factor = 1.4
    scene.display.shading.curvature_valley_factor = 1.0
    scene.world.color = (0.93, 0.93, 0.93)

    camera_data = bpy.data.cameras.new("GateCamera")
    camera = bpy.data.objects.new("GateCamera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera_data.type = "ORTHO"
    camera_data.lens = 70

    # Leave margin around the tallest/widest dimension.
    camera_data.ortho_scale = max(extent.z * 1.08, extent.x * 1.30, extent.y * 1.30)
    return camera


def point_camera(camera, location: Vector, target: Vector):
    camera.location = location
    direction = target - location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_views(camera, center: Vector, extent: Vector):
    radius = max(extent.x, extent.y) * 4.0 + extent.z * 0.3
    z = center.z
    views = []
    for deg in range(0, 360, 45):
        a = math.radians(deg)
        # 0° = camera on -Y; angles increase clockwise around +Z.
        loc = Vector((center.x + radius * math.sin(a), center.y - radius * math.cos(a), z))
        point_camera(camera, loc, center)
        path = OUT / f"view_{deg:03d}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        views.append(path.name)
    return views


def render_detail_ring(camera, center: Vector, extent: Vector, name: str, z_center: float, ortho_scale: float):
    original_scale = camera.data.ortho_scale
    camera.data.ortho_scale = ortho_scale
    radius = max(extent.x, extent.y) * 4.0 + extent.z * 0.3
    files = []
    target = Vector((center.x, center.y, z_center))
    for deg in range(0, 360, 90):
        a = math.radians(deg)
        loc = Vector((center.x + radius * math.sin(a), center.y - radius * math.cos(a), z_center))
        point_camera(camera, loc, target)
        path = OUT / f"{name}_{deg:03d}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        files.append(path.name)
    camera.data.ortho_scale = original_scale
    return files


def export_glb():
    path = OUT / "mhr_v1.0.1_lod1_official.glb"
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
    setup_material(meshes)
    camera = setup_scene(center, extent)

    full_views = render_views(camera, center, extent)
    face_views = render_detail_ring(
        camera,
        center,
        extent,
        "face",
        bmax.z - extent.z * 0.105,
        max(extent.z * 0.25, extent.x * 0.32),
    )
    feet_views = render_detail_ring(
        camera,
        center,
        extent,
        "feet",
        bmin.z + extent.z * 0.075,
        max(extent.z * 0.20, extent.x * 0.55),
    )

    glb = export_glb()
    copied_fbx = OUT / "mhr_v1.0.1_lod1_official_rigged.fbx"
    shutil.copy2(FBX, copied_fbx)

    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    shapekey_count = 0
    for obj in meshes:
        if obj.data.shape_keys and obj.data.shape_keys.key_blocks:
            shapekey_count += max(0, len(obj.data.shape_keys.key_blocks) - 1)

    metrics = {
        "model": "Meta Momentum Human Rig (MHR)",
        "version": "v1.0.1",
        "asset": "assets/lod1.fbx",
        "source": "official GitHub release v1.0.1 assets.zip",
        "execution_path": "official FBX -> Blender CPU import/render/export; PyMomentum bypassed for carrier gate",
        "mesh_object_count": len(meshes),
        "armature_object_count": len(armatures),
        "bone_count": sum(len(a.data.bones) for a in armatures),
        "shape_key_count": shapekey_count,
        "bounds_min": [bmin.x, bmin.y, bmin.z],
        "bounds_max": [bmax.x, bmax.y, bmax.z],
        "extents": [extent.x, extent.y, extent.z],
        "full_body_views": full_views,
        "face_views": face_views,
        "feet_views": feet_views,
        "glb": glb.name,
        "rigged_fbx": copied_fbx.name,
        "gate_status": "READY_FOR_GPT_VISUAL_REVIEW",
        "note": "View angle labels are camera orbit angles, not pre-assigned anatomical front/back. GPT must identify anatomy from rendered evidence.",
    }
    (OUT / "gate_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (OUT / "README.txt").write_text(
        "MHR v1.0.1 LOD1 Human Carrier Gate\n"
        "Uses the official Apache-licensed v1.0.1 release FBX directly.\n"
        "PyMomentum is intentionally bypassed because pymomentum-cpu was unavailable on the runner.\n"
        "This validates carrier geometry/rig assets, not the final cinematic appearance.\n",
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
