import bpy
import json
import os
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

GNM_MODEL = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
DRL_OBJ = Path(os.environ['DRL_OBJ'])
OUT = Path('artifacts/drl-gnm-nonrigid-gate')
OUT.mkdir(parents=True, exist_ok=True)

for p in (GNM_MODEL, DRL_OBJ):
    if not p.is_file() or p.stat().st_size <= 0:
        raise RuntimeError(f'missing input: {p}')

# ------------------------- helpers -------------------------
def build_kd(points):
    kd = KDTree(len(points))
    for i, p in enumerate(points):
        kd.insert(tuple(p), i)
    kd.balance()
    return kd


def nearest_stats(query, reference, max_samples=9000):
    rstep = max(1, len(reference) // max_samples)
    ref = reference[::rstep][:max_samples]
    tree = build_kd(ref)
    qstep = max(1, len(query) // max_samples)
    qs = query[::qstep][:max_samples]
    ds = np.asarray([tree.find(tuple(p))[2] for p in qs], dtype=np.float64)
    return {
        'samples': int(len(ds)),
        'median_mm': float(np.median(ds) * 1000),
        'p90_mm': float(np.percentile(ds, 90) * 1000),
        'p95_mm': float(np.percentile(ds, 95) * 1000),
        'mean_mm': float(ds.mean() * 1000),
        'max_mm': float(ds.max() * 1000),
    }


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
    mask = n > max_len
    scale[mask] = max_len / np.maximum(n[mask], 1e-12)
    return v * scale[:, None]

# ------------------------- GNM target -------------------------
with np.load(GNM_MODEL, allow_pickle=False) as d:
    gv = np.asarray(d['template_vertex_positions'], dtype=np.float64)
    gt = np.asarray(d['triangles'], dtype=np.int64)
    vg = np.asarray(d['vertex_groups'], dtype=np.float64)
    names = [str(x) for x in d['vertex_group_names']]
idx = {n: i for i, n in enumerate(names)}
if 'skin' not in idx:
    raise RuntimeError('GNM skin semantic group missing')
gskin = vg[idx['skin']] > 0.5
G = np.stack([gv[:, 0], -gv[:, 2], gv[:, 1]], axis=1)  # canonical: front=-Y, up=+Z
Gskin = G[gskin]
gmin, gmax = Gskin.min(0), Gskin.max(0)
gc = (gmin + gmax) / 2
gext = gmax - gmin

gn = (Gskin - gmin) / gext
face_roi = (
    (np.abs(gn[:, 0] - 0.5) <= 0.44)
    & (gn[:, 2] >= 0.30)
    & (gn[:, 2] <= 0.96)
    & (gn[:, 1] <= 0.56)
)
Gface = Gskin[face_roi]
if len(Gface) < 1500:
    raise RuntimeError(f'GNM face ROI too small: {len(Gface)}')
Gkd = build_kd(Gface)

# ------------------------- DRL source -------------------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.wm.obj_import(filepath=str(DRL_OBJ.resolve()))
except Exception:
    bpy.ops.import_scene.obj(filepath=str(DRL_OBJ.resolve()))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not meshes:
    raise RuntimeError('DRL OBJ import produced no mesh')
drl = max(meshes, key=lambda o: len(o.data.polygons))
drl.name = 'DRL_Donor_NonRigid'
D = np.asarray([tuple(v.co) for v in drl.data.vertices], dtype=np.float64) * 0.01

dmin, dmax = D.min(0), D.max(0)
dc, dext = (dmin + dmax) / 2, dmax - dmin
scale0 = float(np.median(gext[dext > 1e-8] / dext[dext > 1e-8]))
R = np.eye(3, dtype=np.float64) * scale0
t = gc - R @ dc
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
    raise RuntimeError(f'DRL face ROI too small: {len(Dface_idx)}')

# ------------------------- reproduce rigid ICP baseline -------------------------
step = max(1, len(Dface_idx) // 7000)
Dsample_idx = Dface_idx[::step][:7000]
history = []
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
        raise RuntimeError(f'rigid ICP inliers collapsed at iter {it}')
    Q, q = rigid_fit(cur[keep], matches[keep])
    R = Q @ R
    t = Q @ t + q
    rms = float(np.sqrt(np.mean(dist[keep] ** 2)))
    history.append({'iteration': it, 'rms_mm': rms * 1000, 'inliers': int(keep.sum())})
    if prev is not None and abs(prev - rms) < 1e-5:
        break
    prev = rms

Drigid = (D @ R.T) + t
rigid_face = Drigid[Dface_idx]
rigid_a = nearest_stats(rigid_face, Gface)
rigid_b = nearest_stats(Gface, rigid_face)

# ------------------------- smooth non-rigid registration -------------------------
# Control points are a deterministic, spatially distributed subset of donor face vertices.
control_step = max(1, len(Dface_idx) // 950)
control_idx = Dface_idx[::control_step][:950]
Dwarp = Drigid.copy()
cumulative = np.zeros_like(Dwarp)
nonrigid_history = []

for it in range(7):
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
    residual = clip_vectors(residual, 0.008)  # never move a control >8 mm in one iteration

    # Smooth correspondence motion in control space to suppress nearest-point collapse.
    ckd = build_kd(controls)
    smoothed = np.zeros_like(residual)
    sigma = 0.030
    for i, p in enumerate(controls):
        neigh = ckd.find_n(tuple(p), 12)
        ids = np.asarray([n[1] for n in neigh], dtype=np.int64)
        ds = np.asarray([n[2] for n in neigh], dtype=np.float64)
        w = np.exp(-(ds ** 2) / (2 * sigma ** 2))
        if w.sum() > 1e-12:
            smoothed[i] = (residual[ids] * w[:, None]).sum(0) / w.sum()
    ctrl_disp = 0.35 * residual + 0.65 * smoothed
    ctrl_disp = clip_vectors(ctrl_disp, 0.005)  # conservative 5 mm control step

    # Transfer smooth control motion to donor face; fade to zero outside ~50 mm.
    field = np.zeros((len(Dface_idx), 3), dtype=np.float64)
    radius = 0.052
    for j, vid in enumerate(Dface_idx):
        p = Dwarp[vid]
        neigh = ckd.find_n(tuple(p), 8)
        ids = np.asarray([n[1] for n in neigh], dtype=np.int64)
        ds = np.asarray([n[2] for n in neigh], dtype=np.float64)
        w = np.exp(-(ds ** 2) / (2 * (0.024 ** 2)))
        w[ds > radius] = 0.0
        if w.sum() > 1e-12:
            field[j] = (ctrl_disp[ids] * w[:, None]).sum(0) / w.sum()
    field = clip_vectors(field, 0.004)

    # Cumulative deformation budget: 24 mm at any face vertex.
    proposed = cumulative[Dface_idx] + field
    proposed = clip_vectors(proposed, 0.024)
    actual = proposed - cumulative[Dface_idx]
    Dwarp[Dface_idx] += actual
    cumulative[Dface_idx] = proposed

    cur_face = Dwarp[Dface_idx]
    s1 = nearest_stats(cur_face, Gface)
    s2 = nearest_stats(Gface, cur_face)
    nonrigid_history.append({
        'iteration': it,
        'control_valid': int(valid.sum()),
        'control_cutoff_mm': cutoff * 1000,
        'drl_to_gnm_p90_mm': s1['p90_mm'],
        'gnm_to_drl_p90_mm': s2['p90_mm'],
    })

final_face = Dwarp[Dface_idx]
final_a = nearest_stats(final_face, Gface)
final_b = nearest_stats(Gface, final_face)
face_def = np.linalg.norm(cumulative[Dface_idx], axis=1) * 1000

def_stats = {
    'median_mm': float(np.median(face_def)),
    'p90_mm': float(np.percentile(face_def, 90)),
    'p95_mm': float(np.percentile(face_def, 95)),
    'max_mm': float(face_def.max()),
}

rigid_p90 = max(rigid_a['p90_mm'], rigid_b['p90_mm'])
final_p90 = max(final_a['p90_mm'], final_b['p90_mm'])
improvement = float((rigid_p90 - final_p90) / max(rigid_p90, 1e-9))

thresholds = {
    'median_mm_max': 8.0,
    'p90_mm_max': 20.0,
    'deformation_p95_mm_max': 20.0,
    'deformation_max_mm_max': 24.1,
    'minimum_p90_improvement_fraction': 0.20,
}
pass_numeric = (
    final_a['median_mm'] <= thresholds['median_mm_max']
    and final_b['median_mm'] <= thresholds['median_mm_max']
    and final_a['p90_mm'] <= thresholds['p90_mm_max']
    and final_b['p90_mm'] <= thresholds['p90_mm_max']
    and def_stats['p95_mm'] <= thresholds['deformation_p95_mm_max']
    and def_stats['max_mm'] <= thresholds['deformation_max_mm_max']
    and improvement >= thresholds['minimum_p90_improvement_fraction']
)

# ------------------------- diagnostic overlays -------------------------
for v, p in zip(drl.data.vertices, Dwarp):
    v.co = tuple(p)
for p in drl.data.polygons:
    p.use_smooth = True
for o in meshes:
    if o != drl:
        o.hide_render = True

skin_faces = gt[np.asarray(gskin[gt].any(axis=1), dtype=bool)]
gmesh = bpy.data.meshes.new('GNM_Target_Skin_Mesh')
gmesh.from_pydata(G.tolist(), [], skin_faces.tolist())
gmesh.update()
gobj = bpy.data.objects.new('GNM_Target_Skin', gmesh)
bpy.context.collection.objects.link(gobj)
for p in gobj.data.polygons:
    p.use_smooth = True

def pmat(name, color, rough=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = color
    b.inputs['Roughness'].default_value = rough
    return m

drl.data.materials.clear()
drl.data.materials.append(pmat('DRL_NonRigid_Donor', (0.45, 0.16, 0.055, 1), 0.6))
gobj.data.materials.clear()
gobj.data.materials.append(pmat('GNM_Target_Wire', (0.015, 0.44, 0.70, 1), 0.38))
wire = gobj.modifiers.new('GNM_Target_Wireframe', 'WIREFRAME')
wire.thickness = max(gext) * 0.0014
wire.use_replace = True

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 760
scene.render.resolution_y = 760
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.world.color = (0.01, 0.012, 0.016)
scene.view_settings.exposure = -0.75
cc = (gmin + gmax) / 2
span = float(max(gext))
for name, direction, energy, size in [
    ('Key', (1.1, -1.4, 0.8), 34, span * 0.55),
    ('Fill', (-1, -0.7, 0.2), 11, span * 0.70),
    ('Rim', (0, 1.2, 0.7), 17, span * 0.50),
]:
    ld = bpy.data.lights.new(name, type='AREA')
    ld.energy = energy
    ld.size = size
    lo = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = Vector(cc) + Vector(direction).normalized() * span * 2.0
    lo.rotation_euler = (Vector(cc) - lo.location).to_track_quat('-Z', 'Y').to_euler()

camd = bpy.data.cameras.new('NonRigidCamera')
cam = bpy.data.objects.new('NonRigidCamera', camd)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.data.type = 'ORTHO'

def render(name, axis, target, ortho):
    axis = Vector(axis).normalized()
    target = Vector(target)
    cam.location = target + axis * span * 2.45
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.ortho_scale = ortho
    scene.render.filepath = str((OUT / name).resolve())
    bpy.ops.render.render(write_still=True)

face_center = Gface.mean(0)
face_span = float(max(Gface.max(0) - Gface.min(0)))
render('nonrigid_overlay_front.png', (0, -1, 0), cc, span * 1.08)
render('nonrigid_overlay_three_quarter.png', (0.55, -1, 0), cc, span * 1.08)
render('nonrigid_face_front.png', (0, -1, 0), face_center, face_span * 1.08)
render('nonrigid_face_three_quarter.png', (0.55, -1, 0), face_center, face_span * 1.08)

metrics = {
    'sources': {
        'GNM': {'commit': '98450b3c943101d5859ac1ceb7331ec918ebc321'},
        'DRL': {'asset': 'Marcus_PBR_Sample_01.obj', 'source_to_meters': 0.01},
    },
    'method': 'Rigid ICP baseline followed by bounded smooth control-field non-rigid face registration. Donor topology and UV indexing remain unchanged.',
    'rigid_baseline': {'drl_to_gnm_face': rigid_a, 'gnm_to_drl_face': rigid_b, 'history': history},
    'nonrigid': {'drl_to_gnm_face': final_a, 'gnm_to_drl_face': final_b, 'history': nonrigid_history},
    'face_deformation': def_stats,
    'p90_improvement_fraction': improvement,
    'gate_thresholds': thresholds,
    'numeric_gate_pass': bool(pass_numeric),
    'gate_claim': 'Non-rigid geometry-transfer feasibility only. No PBR bake, identity replacement, final asset adoption, or source redistribution.',
    'not_claimed': ['texture bake success', 'final cinematic master asset', 'browser runtime parity'],
}
(OUT / 'drl_gnm_nonrigid_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
if not pass_numeric:
    raise RuntimeError(f'DRL->GNM non-rigid gate failed: {json.dumps(metrics, indent=2)}')
