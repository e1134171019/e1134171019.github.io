import bpy
import json
import os
from pathlib import Path

import numpy as np
from mathutils import Vector

MODEL = Path(os.environ.get("GNM_MODEL", "/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz"))
OUT = Path("artifacts/gnm-eye-overlap-gate")
OUT.mkdir(parents=True, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

with np.load(MODEL, allow_pickle=False) as d:
    verts = np.asarray(d["template_vertex_positions"], dtype=np.float64)
    tris = np.asarray(d["triangles"], dtype=np.int64)
    vg = np.asarray(d["vertex_groups"], dtype=np.float64)
    names = [str(x) for x in d["vertex_group_names"]]

idx = {n: i for i, n in enumerate(names)}
needed = ["skin", "eye_interiors", "eye_exteriors", "scleras", "irises", "pupils"]
missing = [n for n in needed if n not in idx]
if missing:
    raise RuntimeError(f"Missing GNM groups: {missing}")

# GNM eye labels are nested/overlapping semantic masks. Measure them explicitly.
def vertex_mask(name, t=0.5):
    return vg[idx[name]] > t

def face_any(name, t=0.5):
    return vertex_mask(name, t)[tris].any(axis=1)

def face_all(name, t=0.5):
    return vertex_mask(name, t)[tris].all(axis=1)

def group_stats(name):
    w = vg[idx[name]]
    vm = w > 0.5
    return {
        "vertices_gt_0_5": int(vm.sum()),
        "faces_any_gt_0_5": int(face_any(name).sum()),
        "faces_all_gt_0_5": int(face_all(name).sum()),
        "weight_min": float(w.min()),
        "weight_max": float(w.max()),
        "weight_nonzero": int((w > 1e-8).sum()),
    }

raw_stats = {n: group_stats(n) for n in needed}
for n in ("scleras", "irises", "pupils", "eye_exteriors"):
    if raw_stats[n]["vertices_gt_0_5"] == 0:
        raise RuntimeError(f"GNM group exists but has no active vertices: {n}")

# Build a priority partition ONLY inside the eye interior. Pupil > iris > sclera.
# This respects nested masks without allowing the larger iris mask to erase the pupil.
eye_faces = face_any("eye_interiors")
sclera_faces = eye_faces.copy()
iris_faces = eye_faces & face_any("irises")
pupil_faces = eye_faces & face_any("pupils")
sclera_faces &= ~iris_faces
iris_faces &= ~pupil_faces

# Cornea is a distinct exterior shell. Skin stays separate and excludes the broad eye surfaces.
cornea_faces = face_any("eye_exteriors")
skin_faces = face_any("skin") & ~eye_faces & ~cornea_faces

part_masks = {
    "skin": skin_faces,
    "sclera": sclera_faces,
    "iris": iris_faces,
    "pupil": pupil_faces,
    "cornea": cornea_faces,
}
part_counts = {k: int(v.sum()) for k, v in part_masks.items()}
for n in ("sclera", "iris", "pupil", "cornea"):
    if part_counts[n] <= 0:
        raise RuntimeError(f"Priority partition still produced zero {n} faces: stats={raw_stats}")

# Diagnostic PBR materials, intentionally not final skin/eye shading.
def mat(name, color, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    return m

mats = {
    "skin": mat("GNM_Skin_Diagnostic", (0.18, 0.07, 0.045, 1), 0.62),
    "sclera": mat("GNM_Sclera_Diagnostic", (0.72, 0.68, 0.62, 1), 0.36),
    "iris": mat("GNM_Iris_Diagnostic", (0.02, 0.22, 0.10, 1), 0.25),
    "pupil": mat("GNM_Pupil_Diagnostic", (0.002, 0.002, 0.002, 1), 0.18),
    "cornea": mat("GNM_Cornea_Diagnostic", (0.03, 0.20, 0.42, 1), 0.08),
}

objects = {}
for name, mask in part_masks.items():
    faces = tris[mask]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(f"GNM_{name}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mats[name])
    for p in obj.data.polygons:
        p.use_smooth = True
    objects[name] = obj

# Bounds from semantic eye-interior active vertices.
eye_ids = np.flatnonzero(vertex_mask("eye_interiors"))
eye_pts = verts[eye_ids]
eye_center = eye_pts.mean(axis=0)
eye_min, eye_max = eye_pts.min(axis=0), eye_pts.max(axis=0)
eye_extent = eye_max - eye_min
vmin, vmax = verts.min(axis=0), verts.max(axis=0)
center = (vmin + vmax) / 2
extent = vmax - vmin
max_extent = float(max(extent))

metrics = {
    "source": {
        "repository": "google/GNM",
        "commit": "98450b3c943101d5859ac1ceb7331ec918ebc321",
        "npz_sha256": "868075bbb172fc6574ece89338e21fdc0efe0be91ca4e6e5c3166a1a97840055",
    },
    "vertices": int(len(verts)),
    "triangles": int(len(tris)),
    "raw_group_overlap_stats": raw_stats,
    "priority_partition_face_counts": part_counts,
    "eye_center": eye_center.tolist(),
    "eye_extent": eye_extent.tolist(),
    "method": "Nested semantic masks; pupil overrides iris, iris overrides sclera; cornea kept as separate exterior shell.",
}
(OUT / "gnm_eye_overlap_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world.color = (0.006, 0.007, 0.010)
scene.view_settings.exposure = -0.9

# Lower, controlled studio lighting.
for lname, direction, energy, size in [
    ("Key", (1.1, -1.4, 1.0), 22.0, 0.16),
    ("Fill", (-1.2, -0.6, 0.3), 8.0, 0.20),
    ("Rim", (0.0, 1.2, 1.0), 12.0, 0.13),
]:
    ld = bpy.data.lights.new(lname, type="AREA")
    lo = bpy.data.objects.new(lname, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = Vector(center) + Vector(direction).normalized() * max_extent * 2.2
    ld.energy = energy
    ld.size = size

camd = bpy.data.cameras.new("GateCamera")
cam = bpy.data.objects.new("GateCamera", camd)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"

def aim(axis, target, distance, scale):
    axis = Vector(axis).normalized()
    target = Vector(target)
    cam.location = target + axis * distance
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = scale

# First gate established +Z as the neutral front direction.
front = (0.0, 0.0, 1.0)
threeq = (0.46, 0.0, 1.0)
side = (1.0, 0.0, 0.0)

# Primary eye anatomy: hide cornea so sclera/iris/pupil are directly visible.
objects["cornea"].hide_render = True
for label, axis in [("front", front), ("three_quarter", threeq), ("side", side)]:
    aim(axis, eye_center, max_extent * 2.1, float(max(eye_extent) * (2.1 if label != "side" else 2.4)))
    scene.render.filepath = str((OUT / f"eye_interior_{label}.png").resolve())
    bpy.ops.render.render(write_still=True)

# Cornea shell diagnostic by itself over the intact head.
objects["cornea"].hide_render = False
objects["sclera"].hide_render = True
objects["iris"].hide_render = True
objects["pupil"].hide_render = True
for label, axis in [("front", front), ("three_quarter", threeq)]:
    aim(axis, eye_center, max_extent * 2.1, float(max(eye_extent) * 2.1))
    scene.render.filepath = str((OUT / f"cornea_shell_{label}.png").resolve())
    bpy.ops.render.render(write_still=True)

# Full head with eye interiors shown and cornea hidden for eyelid/opening judgment.
objects["cornea"].hide_render = True
objects["sclera"].hide_render = False
objects["iris"].hide_render = False
objects["pupil"].hide_render = False
for label, axis in [("front", front), ("three_quarter", threeq), ("side", side)]:
    aim(axis, center, max_extent * 2.6, float(max(extent[0], extent[1]) * 1.12))
    scene.render.filepath = str((OUT / f"head_with_eye_anatomy_{label}.png").resolve())
    bpy.ops.render.render(write_still=True)

bpy.ops.export_scene.gltf(
    filepath=str((OUT / "gnm_v3_eye_overlap_diagnostic.glb").resolve()),
    export_format="GLB",
    use_selection=False,
)

print(json.dumps(metrics, indent=2))
