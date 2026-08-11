import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Vector

GNM_MODEL = Path(os.environ.get("GNM_MODEL", "/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz"))
MHR_FBX = Path(os.environ.get("MHR_FBX", "assets/lod1.fbx"))
OUT = Path("artifacts/gnm-mhr-joint-fit-gate")
OUT.mkdir(parents=True, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def umeyama_similarity(src, dst):
    """Solve dst ~= scale * R @ src + t, proper rotation only."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    assert src.shape == dst.shape and src.shape[1] == 3
    n = src.shape[0]
    mu_s = src.mean(axis=0)
    mu_d = dst.mean(axis=0)
    xs = src - mu_s
    xd = dst - mu_d
    cov = (xd.T @ xs) / n
    u, singular, vt = np.linalg.svd(cov)
    sign = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        sign[-1] = -1.0
    r = u @ np.diag(sign) @ vt
    var_s = float(np.sum(xs * xs) / n)
    scale = float(np.sum(singular * sign) / var_s)
    t = mu_d - scale * (r @ mu_s)
    return scale, r, t


def transform_points(points, scale, r, t):
    p = np.asarray(points, dtype=np.float64)
    return (scale * (r @ p.T)).T + t


def make_material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def create_mesh_object(name, vertices, faces, material):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(np.asarray(vertices).tolist(), [], np.asarray(faces, dtype=np.int64).tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


clear_scene()

# -------------------- Import verified MHR rigged carrier --------------------
bpy.ops.import_scene.fbx(filepath=str(MHR_FBX.resolve()), use_anim=False)
armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if len(armatures) != 1 or len(meshes) < 1:
    raise RuntimeError(f"Unexpected MHR import: armatures={len(armatures)}, meshes={len(meshes)}")
arm = armatures[0]
# Choose the largest mesh as the body carrier.
mhr_body = max(meshes, key=lambda o: len(o.data.vertices))

bone_aliases = {
    "neck": ["c_neck", "neck"],
    "head": ["c_head", "head"],
    "left_eye": ["l_eye", "l_eye_null", "left_eye"],
    "right_eye": ["r_eye", "r_eye_null", "right_eye"],
}

def resolve_bone(role):
    for candidate in bone_aliases[role]:
        b = arm.data.bones.get(candidate)
        if b is not None:
            return b
    raise RuntimeError(f"Could not resolve MHR bone for {role}; aliases={bone_aliases[role]}")

mhr_bones = {role: resolve_bone(role) for role in bone_aliases}
# Bone heads are rest-pose anchors. For eyes we deliberately prefer l_eye/r_eye
# over *_null, because GNM left_eye/right_eye are eyeball joints rather than surface locators.
mhr_joint_positions = {}
for role, bone in mhr_bones.items():
    p = arm.matrix_world @ bone.head_local
    mhr_joint_positions[role] = np.array([p.x, p.y, p.z], dtype=np.float64)

# Preserve source MHR body geometry in world space for diagnostic cropping.
mhr_world_vertices = np.array([(mhr_body.matrix_world @ v.co)[:] for v in mhr_body.data.vertices], dtype=np.float64)
mhr_faces = np.array([list(p.vertices) for p in mhr_body.data.polygons], dtype=object)
# LOD1 is triangular; fail loudly if that assumption changes.
if any(len(f) != 3 for f in mhr_faces):
    raise RuntimeError("MHR diagnostic crop expects triangular LOD1 polygons")
mhr_faces = np.stack(mhr_faces).astype(np.int64)

# Hide imported render objects; we create non-destructive diagnostic copies.
for o in meshes + armatures:
    o.hide_render = True

# -------------------- Read official GNM neutral head + joints --------------------
with np.load(GNM_MODEL, allow_pickle=False) as d:
    gnm_vertices = np.asarray(d["template_vertex_positions"], dtype=np.float64)
    gnm_triangles = np.asarray(d["triangles"], dtype=np.int64)
    gnm_joint_positions_all = np.asarray(d["template_joint_positions"], dtype=np.float64)
    gnm_joint_names = [str(x) for x in d["joint_names"]]
    vertex_groups = np.asarray(d["vertex_groups"], dtype=np.float64)
    vertex_group_names = [str(x) for x in d["vertex_group_names"]]

name_to_joint = {n: i for i, n in enumerate(gnm_joint_names)}
roles = ["neck", "head", "left_eye", "right_eye"]
missing = [r for r in roles if r not in name_to_joint]
if missing:
    raise RuntimeError(f"GNM joint roles missing: {missing}; available={gnm_joint_names}")
gnm_joint_positions = {r: gnm_joint_positions_all[name_to_joint[r]].copy() for r in roles}

src = np.stack([gnm_joint_positions[r] for r in roles], axis=0)
dst = np.stack([mhr_joint_positions[r] for r in roles], axis=0)
scale, rotation, translation = umeyama_similarity(src, dst)
if not np.isfinite(scale) or scale <= 0:
    raise RuntimeError(f"Invalid similarity scale: {scale}")
if not np.isfinite(rotation).all() or not np.isfinite(translation).all():
    raise RuntimeError("Non-finite joint-fit transform")
if np.linalg.det(rotation) < 0.999:
    raise RuntimeError(f"Expected proper rotation, det={np.linalg.det(rotation)}")

src_fit = transform_points(src, scale, rotation, translation)
residuals = np.linalg.norm(src_fit - dst, axis=1)
rms = float(np.sqrt(np.mean(residuals ** 2)))
max_residual = float(np.max(residuals))
gnm_world_vertices = transform_points(gnm_vertices, scale, rotation, translation)

# -------------------- Build diagnostic MHR body copy --------------------
mhr_mat = make_material("MHR_Body_Diagnostic", (0.075, 0.11, 0.16, 1.0), 0.58)
# Keep MHR geometry through the base of the head/upper neck. This is a visual-only crop.
head_z = float(mhr_joint_positions["head"][2])
neck_z = float(mhr_joint_positions["neck"][2])
cut_z = head_z + 0.008
face_centers = mhr_world_vertices[mhr_faces].mean(axis=1)
body_keep = face_centers[:, 2] <= cut_z
mhr_diag = create_mesh_object("MHR_body_below_head_cut", mhr_world_vertices, mhr_faces[body_keep], mhr_mat)

# Create a separate ghost copy of native MHR head region for alignment comparison.
ghost_mat = make_material("MHR_Native_Head_Ghost", (0.16, 0.22, 0.30, 1.0), 0.65)
head_region = face_centers[:, 2] > (neck_z - 0.015)
mhr_ghost = create_mesh_object("MHR_native_head_reference", mhr_world_vertices, mhr_faces[head_region], ghost_mat)

# -------------------- Build GNM head anatomy partitions --------------------
vg_idx = {n: i for i, n in enumerate(vertex_group_names)}
required_groups = ["skin", "eye_interiors", "eye_exteriors", "scleras", "irises", "pupils", "upper_teeth_and_gums", "lower_teeth_and_gums", "tongue"]
missing_groups = [n for n in required_groups if n not in vg_idx]
if missing_groups:
    raise RuntimeError(f"GNM expected groups missing: {missing_groups}")

def vm(name):
    return vertex_groups[vg_idx[name]] > 0.5

def face_any(name):
    return vm(name)[gnm_triangles].any(axis=1)

eye_faces = face_any("eye_interiors")
iris_faces = eye_faces & face_any("irises")
pupil_faces = eye_faces & face_any("pupils")
sclera_faces = eye_faces & ~iris_faces
iris_faces = iris_faces & ~pupil_faces
cornea_faces = face_any("eye_exteriors")
teeth_faces = face_any("upper_teeth_and_gums") | face_any("lower_teeth_and_gums")
tongue_faces = face_any("tongue")
skin_faces = face_any("skin") & ~eye_faces & ~cornea_faces

parts = {
    "skin": skin_faces,
    "sclera": sclera_faces,
    "iris": iris_faces,
    "pupil": pupil_faces,
    "cornea": cornea_faces,
    "teeth": teeth_faces,
    "tongue": tongue_faces,
}
for critical in ("skin", "sclera", "iris", "pupil", "cornea"):
    if int(parts[critical].sum()) <= 0:
        raise RuntimeError(f"Zero GNM faces for {critical}")

gnm_mats = {
    "skin": make_material("GNM_Head_Skin_Diagnostic", (0.42, 0.19, 0.12, 1.0), 0.56),
    "sclera": make_material("GNM_Sclera_Diagnostic", (0.72, 0.70, 0.65, 1.0), 0.35),
    "iris": make_material("GNM_Iris_Diagnostic", (0.03, 0.27, 0.13, 1.0), 0.24),
    "pupil": make_material("GNM_Pupil_Diagnostic", (0.002, 0.002, 0.002, 1.0), 0.18),
    "cornea": make_material("GNM_Cornea_Diagnostic", (0.08, 0.25, 0.42, 1.0), 0.08),
    "teeth": make_material("GNM_Teeth_Diagnostic", (0.78, 0.72, 0.61, 1.0), 0.32),
    "tongue": make_material("GNM_Tongue_Diagnostic", (0.36, 0.035, 0.05, 1.0), 0.48),
}
gnm_objects = {}
for name, mask in parts.items():
    if int(mask.sum()) == 0:
        continue
    gnm_objects[name] = create_mesh_object(f"GNM_{name}", gnm_world_vertices, gnm_triangles[mask], gnm_mats[name])

# -------------------- Quantitative integration metrics --------------------
gnm_bbox_min = gnm_world_vertices.min(axis=0)
gnm_bbox_max = gnm_world_vertices.max(axis=0)
mhr_bbox_min = mhr_world_vertices.min(axis=0)
mhr_bbox_max = mhr_world_vertices.max(axis=0)

gnm_neck_world = src_fit[roles.index("neck")]
gnm_head_world = src_fit[roles.index("head")]
# Nearest GNM vertex to transformed neck joint gives a rough surface seam radius metric.
neck_dists = np.linalg.norm(gnm_world_vertices - gnm_neck_world[None, :], axis=1)
nearest_neck_vertex_distance = float(neck_dists.min())

metrics = {
    "sources": {
        "mhr": {
            "version": "v1.0.1",
            "asset": "assets/lod1.fbx",
            "assets_zip_sha256": "e4f4f205cd87c0fa106577ba1de4fc763e4eb197c924461d2ef7e6944e9d6b94",
        },
        "gnm": {
            "commit": "98450b3c943101d5859ac1ceb7331ec918ebc321",
            "asset": "gnm/shape/data/versions/v3_0/gnm_head.npz",
            "npz_sha256": "868075bbb172fc6574ece89338e21fdc0efe0be91ca4e6e5c3166a1a97840055",
        },
    },
    "joint_mapping": {
        "neck": mhr_bones["neck"].name,
        "head": mhr_bones["head"].name,
        "left_eye": mhr_bones["left_eye"].name,
        "right_eye": mhr_bones["right_eye"].name,
    },
    "gnm_joint_positions_source": {r: gnm_joint_positions[r].tolist() for r in roles},
    "mhr_joint_positions_target": {r: mhr_joint_positions[r].tolist() for r in roles},
    "gnm_joint_positions_fitted": {r: src_fit[i].tolist() for i, r in enumerate(roles)},
    "similarity_fit": {
        "scale": scale,
        "rotation": rotation.tolist(),
        "translation": translation.tolist(),
        "rotation_det": float(np.linalg.det(rotation)),
        "rms_residual_m": rms,
        "rms_residual_mm": rms * 1000.0,
        "max_residual_m": max_residual,
        "max_residual_mm": max_residual * 1000.0,
        "per_joint_residual_mm": {r: float(residuals[i] * 1000.0) for i, r in enumerate(roles)},
    },
    "diagnostic_cut": {
        "mhr_neck_z": neck_z,
        "mhr_head_z": head_z,
        "cut_z": cut_z,
        "kept_mhr_faces": int(body_keep.sum()),
        "native_head_reference_faces": int(head_region.sum()),
    },
    "gnm_transformed_bbox": {"min": gnm_bbox_min.tolist(), "max": gnm_bbox_max.tolist(), "extent": (gnm_bbox_max-gnm_bbox_min).tolist()},
    "mhr_bbox": {"min": mhr_bbox_min.tolist(), "max": mhr_bbox_max.tolist(), "extent": (mhr_bbox_max-mhr_bbox_min).tolist()},
    "nearest_gnm_surface_to_neck_joint_mm": nearest_neck_vertex_distance * 1000.0,
    "gnm_part_face_counts": {name: int(mask.sum()) for name, mask in parts.items()},
    "contract": "Alignment/proportion/seam diagnostic only. No topology merge, skin-weight transfer, animation retarget, or final material claim.",
}
(OUT / "gnm_mhr_joint_fit_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

# -------------------- Rendering --------------------
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world.color = (0.010, 0.012, 0.016)
scene.view_settings.exposure = -0.65

combined_min = np.minimum(mhr_bbox_min, gnm_bbox_min)
combined_max = np.maximum(mhr_bbox_max, gnm_bbox_max)
combined_center = (combined_min + combined_max) * 0.5
combined_extent = combined_max - combined_min
max_extent = float(max(combined_extent))

for lname, direction, energy, size in [
    ("Key", (1.3, -1.4, 1.3), 70.0, 0.55),
    ("Fill", (-1.2, -0.8, 0.6), 28.0, 0.70),
    ("Rim", (0.2, 1.3, 1.2), 38.0, 0.50),
]:
    ld = bpy.data.lights.new(lname, type="AREA")
    lo = bpy.data.objects.new(lname, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = Vector(combined_center) + Vector(direction).normalized() * max_extent * 1.8
    ld.energy = energy
    ld.size = size

camd = bpy.data.cameras.new("IntegrationCamera")
cam = bpy.data.objects.new("IntegrationCamera", camd)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"

def render_view(filename, axis, target, scale_value):
    axis = Vector(axis).normalized()
    target = Vector(target)
    cam.location = target + axis * max_extent * 2.1
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = scale_value
    scene.render.filepath = str((OUT / filename).resolve())
    bpy.ops.render.render(write_still=True)

front = (0.0, -1.0, 0.0)
threeq = (0.75, -1.0, 0.0)
side = (1.0, 0.0, 0.0)

# Body-scale views without the native-head ghost.
mhr_ghost.hide_render = True
for label, axis in [("front", front), ("three_quarter", threeq), ("side", side)]:
    render_view(f"integrated_body_{label}.png", axis, combined_center, float(max(combined_extent[0], combined_extent[2]) * 1.10))

# Head/neck closeups to inspect scale and seam.
head_target = (mhr_joint_positions["head"] + mhr_joint_positions["neck"]) * 0.5
head_scale = float(max(gnm_bbox_max[0]-gnm_bbox_min[0], gnm_bbox_max[2]-gnm_bbox_min[2]) * 1.65)
for label, axis in [("front", front), ("three_quarter", threeq), ("side", side)]:
    render_view(f"neck_seam_{label}.png", axis, head_target, head_scale)

# Native MHR head comparison overlay in its own render set.
mhr_ghost.hide_render = False
# Hide cropped body to avoid duplicated lower body distraction; GNM stays visible.
mhr_diag.hide_render = True
for label, axis in [("front", front), ("three_quarter", threeq), ("side", side)]:
    render_view(f"native_head_overlay_{label}.png", axis, head_target, head_scale)
mhr_diag.hide_render = False
mhr_ghost.hide_render = True

# Export diagnostic composite. The hidden source armature remains excluded from render but may be exported,
# so explicitly select diagnostic geometry only.
bpy.ops.object.select_all(action="DESELECT")
export_objs = [mhr_diag] + list(gnm_objects.values())
for o in export_objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = mhr_diag
bpy.ops.export_scene.gltf(
    filepath=str((OUT / "gnm_head_on_mhr_body_diagnostic.glb").resolve()),
    export_format="GLB",
    use_selection=True,
)

print(json.dumps(metrics, indent=2))
