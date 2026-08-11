import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Vector

MODEL_PATH = Path(os.environ.get("GNM_MODEL", "/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz"))
OUT = Path("artifacts/gnm-head-eye-gate")
OUT.mkdir(parents=True, exist_ok=True)

# Clean scene.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

with np.load(MODEL_PATH, allow_pickle=False) as data:
    vertices = np.asarray(data["template_vertex_positions"], dtype=np.float64)
    triangles = np.asarray(data["triangles"], dtype=np.int64)
    vertex_groups = np.asarray(data["vertex_groups"], dtype=np.float64)
    group_names = [str(x) for x in data["vertex_group_names"]]
    joint_names = [str(x) for x in data["joint_names"]]
    expression_names = [str(x) for x in data["expression_names"]]
    identity_names = [str(x) for x in data["identity_names"]]
    skinning_weights = np.asarray(data["skinning_weights"], dtype=np.float64)

assert vertices.ndim == 2 and vertices.shape[1] == 3
assert triangles.ndim == 2 and triangles.shape[1] == 3
assert np.isfinite(vertices).all()
assert triangles.min() >= 0 and triangles.max() < len(vertices)
assert vertex_groups.ndim == 2 and vertex_groups.shape[1] == len(vertices)
assert skinning_weights.ndim == 2 and skinning_weights.shape[1] == len(vertices)

wanted = [
    "skin",
    "eye_interiors",
    "eye_exteriors",
    "upper_teeth_and_gums",
    "lower_teeth_and_gums",
    "tongue",
]
lookup = {name: i for i, name in enumerate(group_names)}
missing = [name for name in wanted if name not in lookup]
if missing:
    raise RuntimeError(f"GNM expected logical vertex groups missing: {missing}; available={group_names}")

# Classify each triangle by average logical vertex-group weight. This does not alter topology.
logical_weights = np.stack([vertex_groups[lookup[name]] for name in wanted], axis=0)
face_scores = logical_weights[:, triangles].mean(axis=2)  # [groups, faces]
face_class = np.argmax(face_scores, axis=0)
face_strength = np.max(face_scores, axis=0)

# Ensure low-confidence faces remain skin rather than becoming arbitrary internal parts.
skin_i = wanted.index("skin")
face_class = np.where(face_strength >= 1e-6, face_class, skin_i)

material_specs = {
    "skin": ((0.55, 0.30, 0.22, 1.0), 0.52, 0.0),
    "eye_interiors": ((0.92, 0.95, 1.00, 1.0), 0.18, 0.0),
    "eye_exteriors": ((0.35, 0.72, 0.95, 1.0), 0.08, 0.0),
    "upper_teeth_and_gums": ((0.93, 0.88, 0.78, 1.0), 0.30, 0.0),
    "lower_teeth_and_gums": ((0.93, 0.88, 0.78, 1.0), 0.30, 0.0),
    "tongue": ((0.52, 0.08, 0.10, 1.0), 0.48, 0.0),
}

materials = {}
for name, (base, rough, metallic) in material_specs.items():
    mat = bpy.data.materials.new(name=f"GNM_{name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = base
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    materials[name] = mat

objects = []
face_counts = {}
for class_id, name in enumerate(wanted):
    f = triangles[face_class == class_id]
    face_counts[name] = int(len(f))
    if not len(f):
        continue
    mesh = bpy.data.meshes.new(f"GNM_{name}_mesh")
    mesh.from_pydata(vertices.tolist(), [], f.tolist())
    mesh.update()
    obj = bpy.data.objects.new(f"GNM_{name}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(materials[name])
    for poly in obj.data.polygons:
        poly.use_smooth = True
    objects.append(obj)

# Bounding boxes and diagnostic region bounds.
vmin = vertices.min(axis=0)
vmax = vertices.max(axis=0)
center = (vmin + vmax) * 0.5
extent = vmax - vmin

def group_bounds(name):
    w = vertex_groups[lookup[name]]
    ids = np.flatnonzero(w > 0.5)
    if len(ids) == 0:
        ids = np.flatnonzero(w > 1e-6)
    if len(ids) == 0:
        return {"count": 0, "min": None, "max": None, "center": None}
    pts = vertices[ids]
    return {
        "count": int(len(ids)),
        "min": pts.min(axis=0).tolist(),
        "max": pts.max(axis=0).tolist(),
        "center": pts.mean(axis=0).tolist(),
    }

metrics = {
    "source": {
        "repository": "google/GNM",
        "commit": "98450b3c943101d5859ac1ceb7331ec918ebc321",
        "model": "gnm/shape/data/versions/v3_0/gnm_head.npz",
        "license": "Apache-2.0",
    },
    "vertices": int(len(vertices)),
    "triangles": int(len(triangles)),
    "joints": int(len(joint_names)),
    "identity_dimensions": int(len(identity_names)),
    "expression_dimensions": int(len(expression_names)),
    "bbox_min": vmin.tolist(),
    "bbox_max": vmax.tolist(),
    "bbox_extent": extent.tolist(),
    "logical_face_counts": face_counts,
    "eye_interiors": group_bounds("eye_interiors"),
    "eye_exteriors": group_bounds("eye_exteriors"),
    "vertex_group_names": group_names,
    "joint_names": joint_names,
    "expression_name_prefix_counts": {
        "left_eye": sum(n.startswith("left_eye") for n in expression_names),
        "right_eye": sum(n.startswith("right_eye") for n in expression_names),
        "lower_face": sum(n.startswith("lower_face") for n in expression_names),
        "tongue": sum(n.startswith("tongue") for n in expression_names),
        "pupil_or_iris": sum(("pupil" in n or "iris" in n) for n in expression_names),
    },
}
(OUT / "gnm_head_gate_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

# Lighting.
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT" if hasattr(bpy.types, "ShaderNodeBsdfPrincipled") else "BLENDER_EEVEE"
scene.render.resolution_x = 820
scene.render.resolution_y = 820
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
scene.world.color = (0.035, 0.035, 0.045)

max_extent = float(max(extent))
for idx, direction in enumerate(((1, -1, 1), (-1, -0.4, 0.6), (0.2, 1, 0.8))):
    light_data = bpy.data.lights.new(name=f"Key{idx}", type="AREA")
    light_obj = bpy.data.objects.new(name=f"Key{idx}", object_data=light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.location = Vector(center) + Vector(direction).normalized() * max_extent * (1.7 + idx * 0.25)
    light_data.energy = 700.0 * max(max_extent, 0.1)
    light_data.shape = "DISK"
    light_data.size = max_extent * 0.8

camera_data = bpy.data.cameras.new("GateCamera")
camera = bpy.data.objects.new("GateCamera", camera_data)
bpy.context.collection.objects.link(camera)
scene.camera = camera
camera.data.type = "ORTHO"

def point_camera(location, target):
    camera.location = Vector(location)
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

views = {
    "pos_x": np.array([1.0, 0.0, 0.0]),
    "neg_x": np.array([-1.0, 0.0, 0.0]),
    "pos_y": np.array([0.0, 1.0, 0.0]),
    "neg_y": np.array([0.0, -1.0, 0.0]),
    "pos_z": np.array([0.0, 0.0, 1.0]),
    "neg_z": np.array([0.0, 0.0, -1.0]),
}
for name, axis in views.items():
    axis_idx = int(np.argmax(np.abs(axis)))
    perp = [i for i in range(3) if i != axis_idx]
    camera.data.ortho_scale = float(max(extent[perp[0]], extent[perp[1]]) * 1.15)
    loc = center + axis * max_extent * 2.6
    point_camera(loc, center)
    scene.render.filepath = str((OUT / f"gnm_neutral_{name}.png").resolve())
    bpy.ops.render.render(write_still=True)

# Eye-region closeups along all axes; this avoids assuming the source coordinate convention.
eye_centers = []
for key in ("eye_interiors", "eye_exteriors"):
    c = metrics[key]["center"]
    if c is not None:
        eye_centers.append(np.asarray(c, dtype=np.float64))
eye_center = np.mean(eye_centers, axis=0) if eye_centers else center
eye_bounds = metrics["eye_interiors"]
if eye_bounds["min"] is not None:
    eb_min = np.asarray(eye_bounds["min"])
    eb_max = np.asarray(eye_bounds["max"])
    eye_extent = eb_max - eb_min
else:
    eye_extent = extent * 0.35
for name, axis in views.items():
    axis_idx = int(np.argmax(np.abs(axis)))
    perp = [i for i in range(3) if i != axis_idx]
    camera.data.ortho_scale = float(max(eye_extent[perp[0]], eye_extent[perp[1]], max_extent * 0.08) * 1.8)
    loc = eye_center + axis * max_extent * 1.8
    point_camera(loc, eye_center)
    scene.render.filepath = str((OUT / f"gnm_eyes_{name}.png").resolve())
    bpy.ops.render.render(write_still=True)

# Export the diagnostic geometry as GLB. It retains source topology but uses diagnostic region materials.
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.export_scene.gltf(
    filepath=str((OUT / "gnm_v3_neutral_diagnostic.glb").resolve()),
    export_format="GLB",
    use_selection=False,
)

print(json.dumps(metrics, indent=2))
