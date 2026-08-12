import bpy
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

GNM_MODEL = Path(os.environ.get("GNM_MODEL", "/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz"))
DRL_OBJ = Path(os.environ["DRL_OBJ"])
DRL_DIFFUSE = Path(os.environ["DRL_DIFFUSE"])
OUT = Path("artifacts/drl-gnm-hockey-diffuse-bake-gate")
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path("/tmp/drl-gnm-hockey-bake")
TMP.mkdir(parents=True, exist_ok=True)
BAKE_SIZE = int(os.environ.get("BAKE_SIZE", "2048"))

for p in (GNM_MODEL, DRL_OBJ, DRL_DIFFUSE):
    if not p.is_file() or p.stat().st_size <= 0:
        raise RuntimeError(f"missing input: {p}")


def build_kd(points):
    kd = KDTree(len(points))
    for i, p in enumerate(points):
        kd.insert(tuple(p), i)
    kd.balance()
    return kd


def rigid_fit(A, B):
    ma, mb = A.mean(0), B.mean(0)
    X, Y = A - ma, B - mb
    U, _, Vt = np.linalg.svd(X.T @ Y)
    Q = Vt.T @ U.T
    if np.linalg.det(Q) < 0:
        Vt[-1, :] *= -1
        Q = Vt.T @ U.T
    return Q, mb - Q @ ma


def clip_vectors(v, max_len):
    n = np.linalg.norm(v, axis=1)
    scale = np.ones_like(n)
    m = n > max_len
    scale[m] = max_len / np.maximum(n[m], 1e-12)
    return v * scale[:, None]


def face_any(vmask, tris):
    return vmask[tris].any(axis=1)


def face_all(vmask, tris):
    return vmask[tris].all(axis=1)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# Load GNM: canonical geometry + official per-triangle UV + semantic mask.
with np.load(GNM_MODEL, allow_pickle=False) as d:
    gv = np.asarray(d["template_vertex_positions"], dtype=np.float64)
    gt = np.asarray(d["triangles"], dtype=np.int64)
    guv = np.asarray(d["triangle_uvs"], dtype=np.float64)
    vg = np.asarray(d["vertex_groups"], dtype=np.float64)
    names = [str(x) for x in d["vertex_group_names"]]

if guv.shape[:2] != gt.shape or guv.shape[2] != 2:
    raise RuntimeError(f"unexpected GNM triangle_uvs shape {guv.shape} for triangles {gt.shape}")
idx = {n: i for i, n in enumerate(names)}
for needed in ("skin", "hockey_mask", "eye_interiors", "irises", "pupils"):
    if needed not in idx:
        raise RuntimeError(f"GNM semantic group missing: {needed}")

G = np.stack([gv[:, 0], -gv[:, 2], gv[:, 1]], axis=1)
gskin = vg[idx["skin"]] > 0.5
hockey = vg[idx["hockey_mask"]] > 0.5
hockey_face_mask = face_all(gskin & hockey, gt)
hockey_face_ids = np.flatnonzero(hockey_face_mask)
if len(hockey_face_ids) < 2000:
    raise RuntimeError(f"hockey mask face count unexpectedly small: {len(hockey_face_ids)}")

gskin_idx = np.flatnonzero(gskin)
Gskin = G[gskin_idx]
gmin, gmax = Gskin.min(0), Gskin.max(0)
gext = gmax - gmin
gn = (Gskin - gmin) / gext
face_local = (
    (np.abs(gn[:, 0] - 0.5) <= 0.44)
    & (gn[:, 2] >= 0.30)
    & (gn[:, 2] <= 0.96)
    & (gn[:, 1] <= 0.56)
)
Gface = Gskin[face_local]
if len(Gface) < 1500:
    raise RuntimeError("GNM face ROI unexpectedly small")
Gkd = build_kd(Gface)

# Import DRL donor and reproduce the bounded non-rigid registration.
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.wm.obj_import(filepath=str(DRL_OBJ.resolve()))
except Exception:
    bpy.ops.import_scene.obj(filepath=str(DRL_OBJ.resolve()))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    raise RuntimeError("DRL OBJ import produced no mesh")
drl = max(meshes, key=lambda o: len(o.data.polygons))
drl.name = "DRL_Diffuse_Donor"
if not drl.data.uv_layers:
    raise RuntimeError("DRL donor has no UV layer")

D = np.asarray([tuple(v.co) for v in drl.data.vertices], dtype=np.float64) * 0.01
dmin, dmax = D.min(0), D.max(0)
dc, dext = (dmin + dmax) / 2, dmax - dmin
scale0 = float(np.median(gext[dext > 1e-8] / dext[dext > 1e-8]))
R = np.eye(3, dtype=np.float64) * scale0
t = ((gmin + gmax) / 2) - R @ dc
D0 = (D @ R.T) + t

dn = (D0 - gmin) / gext
Dface_mask = (
    (np.abs(dn[:, 0] - 0.5) <= 0.47)
    & (dn[:, 2] >= 0.27)
    & (dn[:, 2] <= 0.98)
    & (dn[:, 1] <= 0.60)
)
Dface_idx = np.flatnonzero(Dface_mask)
if len(Dface_idx) < 2500:
    raise RuntimeError("DRL face ROI unexpectedly small")

sample_step = max(1, len(Dface_idx) // 7000)
Dsample_idx = Dface_idx[::sample_step][:7000]
prev = None
for it in range(18):
    cur = (D[Dsample_idx] @ R.T) + t
    matches = np.empty_like(cur)
    dist = np.empty(len(cur), dtype=np.float64)
    for i, p in enumerate(cur):
        co, _, dd = Gkd.find(tuple(p))
        matches[i] = co
        dist[i] = dd
    cutoff = min(float(np.percentile(dist, 72)), 0.035)
    keep = dist <= cutoff
    if int(keep.sum()) < 900:
        raise RuntimeError(f"rigid ICP collapsed at iteration {it}")
    Q, q = rigid_fit(cur[keep], matches[keep])
    R = Q @ R
    t = Q @ t + q
    rms = float(np.sqrt(np.mean(dist[keep] ** 2)))
    if prev is not None and abs(prev - rms) < 1e-5:
        break
    prev = rms

Dwarp = (D @ R.T) + t
control_step = max(1, len(Dface_idx) // 950)
control_idx = Dface_idx[::control_step][:950]
cumulative = np.zeros_like(Dwarp)
for _ in range(7):
    controls = Dwarp[control_idx]
    residual = np.zeros_like(controls)
    raw_dist = np.zeros(len(controls), dtype=np.float64)
    for i, p in enumerate(controls):
        co, _, dd = Gkd.find(tuple(p))
        residual[i] = np.asarray(co) - p
        raw_dist[i] = dd
    cutoff = min(float(np.percentile(raw_dist, 78)), 0.028)
    valid = raw_dist <= cutoff
    residual[~valid] = 0.0
    residual = clip_vectors(residual, 0.008)
    ckd = build_kd(controls)
    smoothed = np.zeros_like(residual)
    for i, p in enumerate(controls):
        neigh = ckd.find_n(tuple(p), 12)
        ids = np.asarray([n[1] for n in neigh], dtype=np.int64)
        ds = np.asarray([n[2] for n in neigh], dtype=np.float64)
        w = np.exp(-(ds ** 2) / (2 * 0.030 ** 2))
        if w.sum() > 1e-12:
            smoothed[i] = (residual[ids] * w[:, None]).sum(0) / w.sum()
    ctrl_disp = clip_vectors(0.35 * residual + 0.65 * smoothed, 0.005)
    field = np.zeros((len(Dface_idx), 3), dtype=np.float64)
    for j, vid in enumerate(Dface_idx):
        p = Dwarp[vid]
        neigh = ckd.find_n(tuple(p), 8)
        ids = np.asarray([n[1] for n in neigh], dtype=np.int64)
        ds = np.asarray([n[2] for n in neigh], dtype=np.float64)
        w = np.exp(-(ds ** 2) / (2 * 0.024 ** 2))
        w[ds > 0.052] = 0.0
        if w.sum() > 1e-12:
            field[j] = (ctrl_disp[ids] * w[:, None]).sum(0) / w.sum()
    field = clip_vectors(field, 0.004)
    proposed = clip_vectors(cumulative[Dface_idx] + field, 0.024)
    actual = proposed - cumulative[Dface_idx]
    Dwarp[Dface_idx] += actual
    cumulative[Dface_idx] = proposed

for v, p in zip(drl.data.vertices, Dwarp):
    v.co = tuple(p)
for p in drl.data.polygons:
    p.use_smooth = True
for o in meshes:
    if o != drl:
        o.hide_render = True

# Build hockey-mask target mesh with official GNM triangle UVs.
target_faces = gt[hockey_face_ids]
target_uvs = guv[hockey_face_ids]
mesh = bpy.data.meshes.new("GNM_Hockey_Bake_Target_Mesh")
mesh.from_pydata(G.tolist(), [], target_faces.tolist())
mesh.update()
target = bpy.data.objects.new("GNM_Hockey_Bake_Target", mesh)
bpy.context.collection.objects.link(target)
uv_layer = mesh.uv_layers.new(name="UVMap")
for poly, uvtri in zip(mesh.polygons, target_uvs):
    for li, uvco in zip(poly.loop_indices, uvtri):
        uv_layer.data[li].uv = tuple(uvco)
    poly.use_smooth = True
if len(mesh.polygons) != len(hockey_face_ids):
    raise RuntimeError("target face construction mismatch")

# Selected-to-active EMIT baking. First white coverage, then real scan diffuse.
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.render.bake.use_selected_to_active = True
scene.render.bake.cage_extrusion = 0.012
scene.render.bake.max_ray_distance = 0.040
scene.render.bake.margin = 18
scene.render.bake.use_clear = True

source_mat = bpy.data.materials.new("DRL_Source_Emission")
source_mat.use_nodes = True
nt = source_mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
emit = nt.nodes.new("ShaderNodeEmission")
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
drl.data.materials.clear()
drl.data.materials.append(source_mat)

target_mat = bpy.data.materials.new("GNM_Bake_Target")
target_mat.use_nodes = True
tnt = target_mat.node_tree
tnt.nodes.clear()
tout = tnt.nodes.new("ShaderNodeOutputMaterial")
tbsdf = tnt.nodes.new("ShaderNodeBsdfPrincipled")
tnt.links.new(tbsdf.outputs["BSDF"], tout.inputs["Surface"])
bake_node = tnt.nodes.new("ShaderNodeTexImage")
target.data.materials.clear()
target.data.materials.append(target_mat)


def activate_bake_image(img):
    bake_node.image = img
    tnt.nodes.active = bake_node
    bake_node.select = True
    for n in tnt.nodes:
        if n != bake_node:
            n.select = False


def select_for_bake():
    bpy.ops.object.select_all(action="DESELECT")
    drl.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target

coverage = bpy.data.images.new("Hockey_Coverage", width=BAKE_SIZE, height=BAKE_SIZE, alpha=True)
coverage.generated_color = (0, 0, 0, 0)
coverage.colorspace_settings.name = "Non-Color"
activate_bake_image(coverage)
emit.inputs["Color"].default_value = (1, 1, 1, 1)
emit.inputs["Strength"].default_value = 1.0
select_for_bake()
bpy.ops.object.bake(type="EMIT")
coverage.filepath_raw = str((TMP / "coverage.png").resolve())
coverage.file_format = "PNG"
coverage.save()

source_img = bpy.data.images.load(str(DRL_DIFFUSE.resolve()), check_existing=False)
source_img.colorspace_settings.name = "sRGB"
texcoord = nt.nodes.new("ShaderNodeTexCoord")
src_tex = nt.nodes.new("ShaderNodeTexImage")
src_tex.image = source_img
src_tex.interpolation = "Linear"
nt.links.new(texcoord.outputs["UV"], src_tex.inputs["Vector"])
nt.links.new(src_tex.outputs["Color"], emit.inputs["Color"])

diffuse_bake = bpy.data.images.new("GNM_Hockey_Diffuse_Bake", width=BAKE_SIZE, height=BAKE_SIZE, alpha=True)
diffuse_bake.generated_color = (0, 0, 0, 0)
diffuse_bake.colorspace_settings.name = "sRGB"
activate_bake_image(diffuse_bake)
select_for_bake()
bpy.ops.object.bake(type="EMIT")
diffuse_path = TMP / "gnm_hockey_drl_diffuse.png"
diffuse_bake.filepath_raw = str(diffuse_path.resolve())
diffuse_bake.file_format = "PNG"
diffuse_bake.save()

# Rasterized expected UV mask and coverage contract.
from PIL import Image, ImageDraw

expected = Image.new("L", (BAKE_SIZE, BAKE_SIZE), 0)
draw = ImageDraw.Draw(expected)
for tri in target_uvs:
    pts = [
        (
            int(np.clip(uv[0], 0, 1) * (BAKE_SIZE - 1)),
            int((1.0 - np.clip(uv[1], 0, 1)) * (BAKE_SIZE - 1)),
        )
        for uv in tri
    ]
    draw.polygon(pts, fill=255)
expected_np = np.asarray(expected) > 127
expected_count = int(expected_np.sum())
if expected_count < BAKE_SIZE * BAKE_SIZE * 0.02:
    raise RuntimeError(f"expected hockey UV footprint too small: {expected_count}")

cov = Image.open(TMP / "coverage.png").convert("L")
cov_np = np.asarray(cov) > 127
hit = int((cov_np & expected_np).sum())
hit_fraction = float(hit / max(expected_count, 1))
miss_np = expected_np & ~cov_np
miss_fraction = float(miss_np.sum() / max(expected_count, 1))

diag = np.zeros((BAKE_SIZE, BAKE_SIZE, 3), dtype=np.uint8)
diag[cov_np & expected_np] = (40, 180, 70)
diag[miss_np] = (230, 45, 35)
Image.fromarray(diag).resize((1024, 1024), Image.Resampling.NEAREST).save(
    OUT / "hockey_uv_coverage_diagnostic.png"
)

baked = Image.open(diffuse_path).convert("RGB")
baked_np = np.asarray(baked)
valid_pixels = baked_np[expected_np & cov_np]
if len(valid_pixels) == 0:
    raise RuntimeError("diffuse bake has no valid pixels")
mean_rgb = valid_pixels.mean(axis=0).tolist()
mean_luma = float(
    (0.2126 * valid_pixels[:, 0] + 0.7152 * valid_pixels[:, 1] + 0.0722 * valid_pixels[:, 2]).mean()
)
std_rgb = valid_pixels.std(axis=0).tolist()

# Build a full GNM skin render. Hockey faces use the baked scan texture;
# everything else stays neutral so the diagnostic does not fabricate identity.
full_skin_faces_mask = face_any(gskin, gt)
full_face_ids = np.flatnonzero(full_skin_faces_mask)
full_mesh = bpy.data.meshes.new("GNM_Full_Skin_Render_Mesh")
full_mesh.from_pydata(G.tolist(), [], gt[full_face_ids].tolist())
full_mesh.update()
full_obj = bpy.data.objects.new("GNM_Full_Skin_Render", full_mesh)
bpy.context.collection.objects.link(full_obj)
full_uv = full_mesh.uv_layers.new(name="UVMap")
for poly, uvtri in zip(full_mesh.polygons, guv[full_face_ids]):
    for li, uvco in zip(poly.loop_indices, uvtri):
        full_uv.data[li].uv = tuple(uvco)
    poly.use_smooth = True


def simple_mat(name, color, roughness):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = roughness
    return m

neutral_skin = simple_mat("Neutral_NonDonor_Skin", (0.28, 0.13, 0.09, 1), 0.55)
baked_mat = bpy.data.materials.new("DRL_Hockey_Diffuse")
baked_mat.use_nodes = True
bnt = baked_mat.node_tree
bbsdf = bnt.nodes.get("Principled BSDF")
render_tex = bnt.nodes.new("ShaderNodeTexImage")
render_tex.image = diffuse_bake
render_tex.interpolation = "Linear"
bnt.links.new(render_tex.outputs["Color"], bbsdf.inputs["Base Color"])
bbsdf.inputs["Roughness"].default_value = 0.48
full_obj.data.materials.append(neutral_skin)
full_obj.data.materials.append(baked_mat)
hockey_face_id_set = set(int(x) for x in hockey_face_ids)
for poly, original_face_id in zip(full_obj.data.polygons, full_face_ids):
    poly.material_index = 1 if int(original_face_id) in hockey_face_id_set else 0

# Add simple eye anatomy for readable renders.
eye = vg[idx["eye_interiors"]] > 0.5
iris = vg[idx["irises"]] > 0.5
pupil = vg[idx["pupils"]] > 0.5
eye_faces = face_any(eye, gt)
iris_faces = eye_faces & face_any(iris, gt)
pupil_faces = eye_faces & face_any(pupil, gt)
sclera_faces = eye_faces & ~iris_faces
iris_faces &= ~pupil_faces

for name, mask, color, rough in [
    ("Sclera", sclera_faces, (0.72, 0.68, 0.62, 1), 0.32),
    ("Iris", iris_faces, (0.08, 0.20, 0.12, 1), 0.26),
    ("Pupil", pupil_faces, (0.002, 0.002, 0.002, 1), 0.18),
]:
    m = bpy.data.meshes.new(f"{name}_mesh")
    m.from_pydata(G.tolist(), [], gt[mask].tolist())
    m.update()
    o = bpy.data.objects.new(name, m)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(simple_mat(name + "_mat", color, rough))
    for p in o.data.polygons:
        p.use_smooth = True

drl.hide_render = True
target.hide_render = True

scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1000
scene.render.resolution_y = 1000
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world.color = (0.008, 0.010, 0.014)
scene.view_settings.exposure = -0.55

all_pts = G[gskin]
center = (all_pts.min(0) + all_pts.max(0)) / 2
span = float(max(all_pts.max(0) - all_pts.min(0)))

for name, direction, energy, size, color in [
    ("Key", (1.2, -1.5, 0.8), 40, span * 0.58, (1.0, 0.85, 0.76)),
    ("Fill", (-1.0, -0.7, 0.2), 13, span * 0.75, (0.74, 0.82, 1.0)),
    ("Rim", (0.1, 1.2, 0.8), 18, span * 0.50, (0.82, 0.90, 1.0)),
]:
    ld = bpy.data.lights.new(name, type="AREA")
    ld.energy = energy
    ld.size = size
    ld.color = color
    lo = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = Vector(center) + Vector(direction).normalized() * span * 2.0
    lo.rotation_euler = (Vector(center) - lo.location).to_track_quat("-Z", "Y").to_euler()

camd = bpy.data.cameras.new("BakeReviewCamera")
cam = bpy.data.objects.new("BakeReviewCamera", camd)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.data.type = "ORTHO"


def render(name, axis, ortho):
    axis = Vector(axis).normalized()
    cam.location = Vector(center) + axis * span * 2.5
    cam.rotation_euler = (Vector(center) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = ortho
    scene.render.filepath = str((OUT / name).resolve())
    bpy.ops.render.render(write_still=True)

render("diffuse_transfer_front.png", (0, -1, 0), span * 1.04)
render("diffuse_transfer_three_quarter.png", (0.52, -1, 0), span * 1.04)
render("diffuse_transfer_side.png", (1, 0, 0), span * 1.06)

metrics = {
    "sources": {
        "GNM": {
            "commit": "98450b3c943101d5859ac1ceb7331ec918ebc321",
            "uv_source": "gnm_head.npz::triangle_uvs",
        },
        "DRL": {
            "asset": "Marcus_PBR_Sample_01.obj",
            "diffuse_proxy": DRL_DIFFUSE.name,
            "source_to_meters": 0.01,
        },
    },
    "bake": {
        "resolution": BAKE_SIZE,
        "method": "Cycles selected-to-active EMIT bake after bounded non-rigid registration",
        "hockey_vertices": int(hockey.sum()),
        "hockey_faces_all_vertices": int(len(hockey_face_ids)),
        "expected_uv_pixels": expected_count,
        "hit_pixels": hit,
        "coverage_hit_fraction": hit_fraction,
        "coverage_miss_fraction": miss_fraction,
        "cage_extrusion_m": float(scene.render.bake.cage_extrusion),
        "max_ray_distance_m": float(scene.render.bake.max_ray_distance),
        "baked_diffuse_sha256": sha256(diffuse_path),
        "valid_mean_rgb_0_255": [float(x) for x in mean_rgb],
        "valid_std_rgb_0_255": [float(x) for x in std_rgb],
        "valid_mean_luma_0_255": mean_luma,
    },
    "gate_thresholds": {
        "coverage_hit_fraction_min": 0.95,
        "mean_luma_min": 25.0,
        "mean_luma_max": 235.0,
        "rgb_std_min": 8.0,
    },
    "raw_baked_identity_map_uploaded": False,
    "gate_claim": "Functional diffuse transfer gate for the stable GNM hockey-mask facial region only.",
    "not_claimed": [
        "full-head DRL appearance transfer",
        "normal/gloss/specular/displacement transfer",
        "seam-final production blend",
        "final cinematic master asset",
        "browser runtime parity",
    ],
}
metrics["gate_pass"] = bool(
    hit_fraction >= metrics["gate_thresholds"]["coverage_hit_fraction_min"]
    and metrics["gate_thresholds"]["mean_luma_min"] <= mean_luma <= metrics["gate_thresholds"]["mean_luma_max"]
    and max(std_rgb) >= metrics["gate_thresholds"]["rgb_std_min"]
)
(OUT / "drl_gnm_hockey_diffuse_bake_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print(json.dumps(metrics, indent=2))
if not metrics["gate_pass"]:
    raise RuntimeError(f"diffuse bake gate failed: {json.dumps(metrics, indent=2)}")
