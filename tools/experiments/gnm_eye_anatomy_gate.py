import bpy
import json
import os
from pathlib import Path

import numpy as np
from mathutils import Vector

MODEL_PATH = Path(os.environ.get("GNM_MODEL", "/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz"))
OUT = Path("artifacts/gnm-eye-anatomy-gate")
OUT.mkdir(parents=True, exist_ok=True)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

with np.load(MODEL_PATH, allow_pickle=False) as data:
    vertices = np.asarray(data["template_vertex_positions"], dtype=np.float64)
    triangles = np.asarray(data["triangles"], dtype=np.int64)
    vertex_groups = np.asarray(data["vertex_groups"], dtype=np.float64)
    group_names = [str(x) for x in data["vertex_group_names"]]

lookup = {name: i for i, name in enumerate(group_names)}
required = ["skin", "scleras", "irises", "pupils", "eye_exteriors"]
missing = [n for n in required if n not in lookup]
if missing:
    raise RuntimeError(f"Missing expected GNM eye groups: {missing}")

# Eye-specific groups are deliberately more specific than the broad eye_interiors
# group used in the first gate, so iris/pupil anatomy cannot be hidden by one material.
classes = ["skin", "scleras", "irises", "pupils", "eye_exteriors"]
weights = np.stack([vertex_groups[lookup[n]] for n in classes], axis=0)
face_scores = weights[:, triangles].mean(axis=2)
face_class = np.argmax(face_scores, axis=0)
face_strength = face_scores.max(axis=0)
face_class = np.where(face_strength > 1e-6, face_class, 0)

# Diagnostic materials: high contrast, moderate roughness, no photographic claim.
def make_principled(name, rgba, rough=0.45, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        mat.surface_render_method = 'DITHERED' if hasattr(mat, 'surface_render_method') else None
    return mat

materials = {
    "skin": make_principled("skin", (0.20, 0.11, 0.085, 1.0), 0.62),
    "scleras": make_principled("scleras", (0.72, 0.72, 0.68, 1.0), 0.38),
    "irises": make_principled("irises", (0.045, 0.30, 0.21, 1.0), 0.24),
    "pupils": make_principled("pupils", (0.003, 0.003, 0.003, 1.0), 0.20),
    "eye_exteriors": make_principled("cornea", (0.10, 0.32, 0.48, 1.0), 0.08),
}

objects = {}
counts = {}
for cid, name in enumerate(classes):
    faces = triangles[face_class == cid]
    counts[name] = int(len(faces))
    if not len(faces):
        continue
    mesh = bpy.data.meshes.new(f"GNM_{name}_mesh")
    mesh.from_pydata(vertices.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(f"GNM_{name}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(materials[name])
    for poly in obj.data.polygons:
        poly.use_smooth = True
    objects[name] = obj

for critical in ("scleras", "irises", "pupils", "eye_exteriors"):
    if counts.get(critical, 0) <= 0:
        raise RuntimeError(f"No classified faces for critical eye component: {critical}")

# Geometry metrics for each eye layer.
def bounds(group):
    w = vertex_groups[lookup[group]]
    ids = np.flatnonzero(w > 0.5)
    if len(ids) == 0:
        ids = np.flatnonzero(w > 1e-6)
    p = vertices[ids]
    return {
        "vertices": int(len(ids)),
        "min": p.min(axis=0).tolist(),
        "max": p.max(axis=0).tolist(),
        "center": p.mean(axis=0).tolist(),
    }

vmin, vmax = vertices.min(axis=0), vertices.max(axis=0)
center = (vmin + vmax) / 2.0
extent = vmax - vmin
metrics = {
    "vertices": int(len(vertices)),
    "triangles": int(len(triangles)),
    "classified_faces": counts,
    "scleras": bounds("scleras"),
    "irises": bounds("irises"),
    "pupils": bounds("pupils"),
    "cornea": bounds("eye_exteriors"),
    "source_commit": "98450b3c943101d5859ac1ceb7331ec918ebc321",
    "interpretation": "Diagnostic geometry/material split only; not final cinematic shading.",
}
(OUT / "gnm_eye_anatomy_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 960
scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world.color = (0.012, 0.012, 0.016)
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = -1.3

max_extent = float(max(extent))
# Controlled key/fill/rim, intentionally lower-energy than first gate.
for name, direction, energy, size in [
    ("Key", (1.2, -1.5, 1.0), 45.0, 0.14),
    ("Fill", (-1.4, -0.8, 0.4), 18.0, 0.18),
    ("Rim", (0.2, 1.5, 1.2), 30.0, 0.12),
]:
    ld = bpy.data.lights.new(name, type="AREA")
    lo = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = Vector(center) + Vector(direction).normalized() * max_extent * 2.3
    ld.energy = energy
    ld.size = size

cam_data = bpy.data.cameras.new("EyeGateCamera")
cam = bpy.data.objects.new("EyeGateCamera", cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"

def aim(location, target):
    cam.location = Vector(location)
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()

# GNM neutral front was established as +Z in the six-axis gate.
front = np.array([0.0, 0.0, 1.0])
right = np.array([1.0, 0.0, 0.0])
threeq = (front + right * 0.52)
threeq /= np.linalg.norm(threeq)
side = right

eye_center = np.asarray(metrics["scleras"]["center"])
eye_min = np.asarray(metrics["scleras"]["min"])
eye_max = np.asarray(metrics["scleras"]["max"])
eye_extent = eye_max - eye_min

# First render without cornea so iris/pupil geometry is unambiguously visible.
objects["eye_exteriors"].hide_render = True
for view_name, axis in [("front", front), ("three_quarter", threeq), ("side", side)]:
    cam.data.ortho_scale = float(max(eye_extent[0], eye_extent[1], eye_extent[2]) * (2.25 if view_name != "side" else 2.5))
    aim(eye_center + axis * max_extent * 2.0, eye_center)
    scene.render.filepath = str((OUT / f"gnm_eye_layers_no_cornea_{view_name}.png").resolve())
    bpy.ops.render.render(write_still=True)

# Then show cornea as its own blue diagnostic shell.
objects["eye_exteriors"].hide_render = False
for view_name, axis in [("front", front), ("three_quarter", threeq)]:
    cam.data.ortho_scale = float(max(eye_extent) * 2.25)
    aim(eye_center + axis * max_extent * 2.0, eye_center)
    scene.render.filepath = str((OUT / f"gnm_eye_layers_with_cornea_{view_name}.png").resolve())
    bpy.ops.render.render(write_still=True)

# Full head front/3Q in calmer lighting to judge eyelid opening and silhouette.
for view_name, axis in [("front", front), ("three_quarter", threeq), ("side", side)]:
    cam.data.ortho_scale = float(max(extent[0], extent[1]) * 1.12)
    aim(center + axis * max_extent * 2.5, center)
    scene.render.filepath = str((OUT / f"gnm_head_anatomy_{view_name}.png").resolve())
    bpy.ops.render.render(write_still=True)

# Diagnostic GLB contains geometry layers, not final shaders.
bpy.ops.export_scene.gltf(
    filepath=str((OUT / "gnm_v3_eye_anatomy_diagnostic.glb").resolve()),
    export_format="GLB",
    use_selection=False,
)

print(json.dumps(metrics, indent=2))
