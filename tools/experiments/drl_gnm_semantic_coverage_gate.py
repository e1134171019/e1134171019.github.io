import bpy
import json
import os
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

GNM_MODEL = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
DRL_OBJ = Path(os.environ['DRL_OBJ'])
OUT = Path('artifacts/drl-gnm-semantic-coverage-gate')
OUT.mkdir(parents=True, exist_ok=True)

for p in (GNM_MODEL, DRL_OBJ):
    if not p.is_file() or p.stat().st_size <= 0:
        raise RuntimeError(f'missing input: {p}')


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
    s = np.ones_like(n)
    m = n > max_len
    s[m] = max_len / np.maximum(n[m], 1e-12)
    return v * s[:, None]


def stats(values):
    a = np.asarray(values, dtype=np.float64)
    if len(a) == 0:
        return {'count': 0}
    return {
        'count': int(len(a)),
        'median_mm': float(np.median(a) * 1000),
        'p90_mm': float(np.percentile(a, 90) * 1000),
        'p95_mm': float(np.percentile(a, 95) * 1000),
        'mean_mm': float(a.mean() * 1000),
        'gt10_fraction': float(np.mean(a > 0.010)),
        'gt20_fraction': float(np.mean(a > 0.020)),
        'gt30_fraction': float(np.mean(a > 0.030)),
    }

# ------------------------- GNM -------------------------
with np.load(GNM_MODEL, allow_pickle=False) as d:
    gv = np.asarray(d['template_vertex_positions'], dtype=np.float64)
    gt = np.asarray(d['triangles'], dtype=np.int64)
    vg = np.asarray(d['vertex_groups'], dtype=np.float64)
    names = [str(x) for x in d['vertex_group_names']]
idx = {n: i for i, n in enumerate(names)}
if 'skin' not in idx:
    raise RuntimeError('GNM skin group missing')

gskin = vg[idx['skin']] > 0.5
gskin_idx = np.flatnonzero(gskin)
G = np.stack([gv[:, 0], -gv[:, 2], gv[:, 1]], axis=1)  # canonical -Y front, +Z up
Gskin = G[gskin_idx]
gmin, gmax = Gskin.min(0), Gskin.max(0)
gext = gmax - gmin
gn = (Gskin - gmin) / gext

# Same broad face envelope as the preceding gates, but retain original GNM vertex ids.
face_local_mask = (
    (np.abs(gn[:, 0] - 0.5) <= 0.44)
    & (gn[:, 2] >= 0.30)
    & (gn[:, 2] <= 0.96)
    & (gn[:, 1] <= 0.56)
)
Gface = Gskin[face_local_mask]
Gface_ids = gskin_idx[face_local_mask]
Gface_n = gn[face_local_mask]
if len(Gface) < 1500:
    raise RuntimeError(f'GNM face ROI too small: {len(Gface)}')
Gkd = build_kd(Gface)

# ------------------------- DRL + reproduce bounded nonrigid result -------------------------
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
    raise RuntimeError(f'DRL face ROI too small: {len(Dface_idx)}')

step = max(1, len(Dface_idx) // 7000)
Dsample_idx = Dface_idx[::step][:7000]
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
        raise RuntimeError(f'rigid ICP collapsed at {it}')
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
    sigma = 0.030
    for i, p in enumerate(controls):
        neigh = ckd.find_n(tuple(p), 12)
        ids = np.asarray([n[1] for n in neigh], dtype=np.int64)
        ds = np.asarray([n[2] for n in neigh], dtype=np.float64)
        w = np.exp(-(ds ** 2) / (2 * sigma ** 2))
        if w.sum() > 1e-12:
            smoothed[i] = (residual[ids] * w[:, None]).sum(0) / w.sum()
    ctrl_disp = clip_vectors(0.35 * residual + 0.65 * smoothed, 0.005)
    field = np.zeros((len(Dface_idx), 3), dtype=np.float64)
    for j, vid in enumerate(Dface_idx):
        p = Dwarp[vid]
        neigh = ckd.find_n(tuple(p), 8)
        ids = np.asarray([n[1] for n in neigh], dtype=np.int64)
        ds = np.asarray([n[2] for n in neigh], dtype=np.float64)
        w = np.exp(-(ds ** 2) / (2 * (0.024 ** 2)))
        w[ds > 0.052] = 0.0
        if w.sum() > 1e-12:
            field[j] = (ctrl_disp[ids] * w[:, None]).sum(0) / w.sum()
    field = clip_vectors(field, 0.004)
    proposed = clip_vectors(cumulative[Dface_idx] + field, 0.024)
    actual = proposed - cumulative[Dface_idx]
    Dwarp[Dface_idx] += actual
    cumulative[Dface_idx] = proposed

Dface_final = Dwarp[Dface_idx]
Dkd = build_kd(Dface_final)

# Distances from every GNM face point to donor. This is the stubborn direction from the previous gate.
g_to_d = np.asarray([Dkd.find(tuple(p))[2] for p in Gface], dtype=np.float64)

# ------------------------- semantic localization -------------------------
semantic = []
for gi, name in enumerate(names):
    active = vg[gi, Gface_ids] > 0.5
    count = int(active.sum())
    if count < 8:
        continue
    s = stats(g_to_d[active])
    s.update({
        'name': name,
        'active_vertices': count,
        'share_of_face_roi': float(count / len(Gface)),
    })
    semantic.append(s)
semantic.sort(key=lambda x: (x.get('gt20_fraction', 0.0), x.get('p90_mm', 0.0), x['active_vertices']), reverse=True)

# Known nested/non-skin appearance surfaces are never valid DRL skin-transfer targets.
exclude_tokens = ('eye_interior', 'eye_exterior', 'sclera', 'iris', 'pupil', 'teeth', 'tooth', 'tongue', 'mouth_interior', 'oral')
semantic_exclusion = np.zeros(len(Gface), dtype=bool)
excluded_group_names = []
for gi, name in enumerate(names):
    lname = name.lower()
    if any(tok in lname for tok in exclude_tokens):
        m = vg[gi, Gface_ids] > 0.5
        if m.any():
            semantic_exclusion |= m
            excluded_group_names.append(name)

x, y, z = Gface_n[:, 0], Gface_n[:, 1], Gface_n[:, 2]
regions = {
    'face_roi_all': np.ones(len(Gface), dtype=bool),
    'forehead_front': (z >= 0.68) & (z <= 0.94) & (np.abs(x - 0.5) <= 0.30) & (y <= 0.46),
    'eye_band_front': (z >= 0.56) & (z < 0.70) & (np.abs(x - 0.5) <= 0.36) & (y <= 0.46),
    'nose_cheek_front': (z >= 0.45) & (z < 0.60) & (np.abs(x - 0.5) <= 0.34) & (y <= 0.43),
    'perioral_front': (z >= 0.36) & (z < 0.50) & (np.abs(x - 0.5) <= 0.25) & (y <= 0.43),
    'chin_jaw_front': (z >= 0.30) & (z < 0.43) & (np.abs(x - 0.5) <= 0.38) & (y <= 0.50),
    'left_ear_side': (x < 0.16) & (z >= 0.36) & (z <= 0.70),
    'right_ear_side': (x > 0.84) & (z >= 0.36) & (z <= 0.70),
    'central_external_skin': (np.abs(x - 0.5) <= 0.34) & (z >= 0.34) & (z <= 0.92) & (y <= 0.48) & (~semantic_exclusion),
}
region_stats = {name: stats(g_to_d[m]) for name, m in regions.items()}

high = {
    'gt10_count': int((g_to_d > 0.010).sum()),
    'gt20_count': int((g_to_d > 0.020).sum()),
    'gt30_count': int((g_to_d > 0.030).sum()),
    'gt20_fraction': float(np.mean(g_to_d > 0.020)),
    'gt30_fraction': float(np.mean(g_to_d > 0.030)),
}

# ------------------------- heatmap render -------------------------
# Map each original GNM vertex to its diagnosed distance; vertices outside ROI are neutral.
dist_by_vertex = np.full(len(G), np.nan, dtype=np.float64)
dist_by_vertex[Gface_ids] = g_to_d
skin_faces = gt[np.asarray(gskin[gt].any(axis=1), dtype=bool)]

heat_mesh = bpy.data.meshes.new('GNM_Semantic_Coverage_Heatmap')
heat_mesh.from_pydata(G.tolist(), [], skin_faces.tolist())
heat_mesh.update()
heat_obj = bpy.data.objects.new('GNM_Semantic_Coverage_Heatmap', heat_mesh)
bpy.context.collection.objects.link(heat_obj)
for p in heat_obj.data.polygons:
    p.use_smooth = True

# Discrete diagnostic bins: neutral / <5 / 5-10 / 10-20 / 20-30 / >30 mm.
def mat(name, color, rough=0.55):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = color
    b.inputs['Roughness'].default_value = rough
    return m

mats = [
    mat('Outside_ROI', (0.06, 0.07, 0.08, 1)),
    mat('Error_lt_5mm', (0.02, 0.40, 0.10, 1)),
    mat('Error_5_10mm', (0.20, 0.55, 0.04, 1)),
    mat('Error_10_20mm', (0.75, 0.48, 0.02, 1)),
    mat('Error_20_30mm', (0.80, 0.11, 0.02, 1)),
    mat('Error_gt_30mm', (0.55, 0.00, 0.24, 1)),
]
for m in mats:
    heat_obj.data.materials.append(m)

for poly, face in zip(heat_obj.data.polygons, skin_faces):
    vals = dist_by_vertex[face]
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        poly.material_index = 0
        continue
    d = float(np.max(vals))
    if d < 0.005: poly.material_index = 1
    elif d < 0.010: poly.material_index = 2
    elif d < 0.020: poly.material_index = 3
    elif d < 0.030: poly.material_index = 4
    else: poly.material_index = 5

# Donor as very thin dark wire only, to reveal whether red zones are true coverage gaps.
for v, p in zip(drl.data.vertices, Dwarp):
    v.co = tuple(p)
for p in drl.data.polygons:
    p.use_smooth = True
for o in meshes:
    if o != drl:
        o.hide_render = True
wire_mat = mat('DRL_Donor_Wire', (0.015, 0.015, 0.018, 1), 0.6)
drl.data.materials.clear(); drl.data.materials.append(wire_mat)
wire = drl.modifiers.new('DRL_Donor_Wireframe', 'WIREFRAME')
wire.thickness = float(max(gext)) * 0.0007
wire.use_replace = True

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 900
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.world.color = (0.008, 0.009, 0.012)
scene.view_settings.exposure = -0.9
cc = (gmin + gmax) / 2
span = float(max(gext))
for lname, direction, energy, size in [
    ('Key', (1.0, -1.4, 0.8), 30, span * 0.55),
    ('Fill', (-1.0, -0.7, 0.25), 10, span * 0.70),
    ('Rim', (0.1, 1.2, 0.7), 15, span * 0.48),
]:
    ld = bpy.data.lights.new(lname, type='AREA'); ld.energy = energy; ld.size = size
    lo = bpy.data.objects.new(lname, ld); bpy.context.collection.objects.link(lo)
    lo.location = Vector(cc) + Vector(direction).normalized() * span * 2.0
    lo.rotation_euler = (Vector(cc) - lo.location).to_track_quat('-Z', 'Y').to_euler()
camd = bpy.data.cameras.new('CoverageCamera')
cam = bpy.data.objects.new('CoverageCamera', camd)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.data.type = 'ORTHO'

def render(name, axis, target, ortho):
    axis = Vector(axis).normalized(); target = Vector(target)
    cam.location = target + axis * span * 2.4
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.ortho_scale = ortho
    scene.render.filepath = str((OUT / name).resolve())
    bpy.ops.render.render(write_still=True)

face_center = Gface.mean(0)
face_span = float(max(Gface.max(0) - Gface.min(0)))
render('coverage_front.png', (0, -1, 0), face_center, face_span * 1.08)
render('coverage_three_quarter.png', (0.55, -1, 0), face_center, face_span * 1.08)
render('coverage_side.png', (1, 0, 0), face_center, face_span * 1.10)

central = region_stats['central_external_skin']
central_pass = bool(
    central.get('count', 0) >= 1200
    and central.get('median_mm', 999) <= 6.0
    and central.get('p90_mm', 999) <= 15.0
    and central.get('gt20_fraction', 1.0) <= 0.05
)

metrics = {
    'sources': {
        'GNM': {'commit': '98450b3c943101d5859ac1ceb7331ec918ebc321'},
        'DRL': {'asset': 'Marcus_PBR_Sample_01.obj', 'source_to_meters': 0.01},
    },
    'purpose': 'Localize stubborn target-to-donor coverage tail after bounded non-rigid registration. Diagnostic only; no new warp or texture bake.',
    'gnm_vertex_group_names': names,
    'excluded_semantic_groups_from_skin_transfer_roi': excluded_group_names,
    'face_roi_target_to_donor': stats(g_to_d),
    'high_error_summary': high,
    'region_stats': region_stats,
    'semantic_group_stats_sorted_by_gt20': semantic,
    'central_external_skin_transfer_candidate': {
        'criteria': {'min_count': 1200, 'median_mm_max': 6.0, 'p90_mm_max': 15.0, 'gt20_fraction_max': 0.05},
        'pass': central_pass,
    },
    'heatmap_bins_mm': {'green_dark': '<5', 'green_light': '5-10', 'orange': '10-20', 'red': '20-30', 'magenta': '>30'},
    'gate_claim': 'Semantic/region coverage localization only. No PBR baking, final asset adoption, or source redistribution.',
}
(OUT / 'drl_gnm_semantic_coverage_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
