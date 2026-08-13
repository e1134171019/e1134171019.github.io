import bpy
import csv
import json
import os
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from tools.experiments.ray_geometry_math import summarize_signed_offsets

GNM_MODEL = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
DRL_OBJ = Path(os.environ['DRL_OBJ'])
OUT = Path('artifacts/drl-gnm-ray-geometry-gate')
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


def face_all(mask, tris):
    return mask[tris].all(axis=1)


def area_weighted_vertex_normals(vertices, faces):
    tri = vertices[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    lengths = np.linalg.norm(vn, axis=1)
    good = lengths > 1e-12
    vn[good] /= lengths[good, None]
    return vn, good


# ---------------- GNM canonical geometry ----------------
with np.load(GNM_MODEL, allow_pickle=False) as d:
    gv = np.asarray(d['template_vertex_positions'], dtype=np.float64)
    gt = np.asarray(d['triangles'], dtype=np.int64)
    vg = np.asarray(d['vertex_groups'], dtype=np.float64)
    names = [str(x) for x in d['vertex_group_names']]

idx = {n: i for i, n in enumerate(names)}
for needed in ('skin', 'hockey_mask'):
    if needed not in idx:
        raise RuntimeError(f'GNM semantic group missing: {needed}')

G = np.stack([gv[:, 0], -gv[:, 2], gv[:, 1]], axis=1)  # -Y front, +Z up
gskin = vg[idx['skin']] > 0.5
hockey = vg[idx['hockey_mask']] > 0.5
hockey_vertex_mask = gskin & hockey
hockey_vid = np.flatnonzero(hockey_vertex_mask)
if len(hockey_vid) < 3000:
    raise RuntimeError(f'hockey vertex count unexpectedly small: {len(hockey_vid)}')

skin_faces = gt[face_all(gskin, gt)]
vertex_normals, normal_valid = area_weighted_vertex_normals(G, skin_faces)
hockey_valid = normal_valid[hockey_vid]
hockey_vid = hockey_vid[hockey_valid]
if len(hockey_vid) < 0.95 * int(hockey_vertex_mask.sum()):
    raise RuntimeError('too many hockey vertices lack valid normals')

Gskin = G[np.flatnonzero(gskin)]
gmin, gmax = Gskin.min(0), Gskin.max(0)
gext = gmax - gmin
head_center = Gskin.mean(0)
radial = G[hockey_vid] - head_center
orientation_dot = np.einsum('ij,ij->i', vertex_normals[hockey_vid], radial)
orientation_positive_before = float(np.mean(orientation_dot > 0))
normal_global_flip = orientation_positive_before < 0.5
if normal_global_flip:
    vertex_normals *= -1.0
orientation_dot_after = np.einsum('ij,ij->i', vertex_normals[hockey_vid], radial)
orientation_positive_after = float(np.mean(orientation_dot_after > 0))
if orientation_positive_after < 0.70:
    raise RuntimeError(f'GNM normal orientation ambiguous: outward fraction={orientation_positive_after:.3f}')

# Existing broad face ROI used by preceding registration gates.
gskin_idx = np.flatnonzero(gskin)
Gskin = G[gskin_idx]
gn = (Gskin - gmin) / gext
face_local = (
    (np.abs(gn[:, 0] - 0.5) <= 0.44)
    & (gn[:, 2] >= 0.30)
    & (gn[:, 2] <= 0.96)
    & (gn[:, 1] <= 0.56)
)
Gface = Gskin[face_local]
if len(Gface) < 1500:
    raise RuntimeError('GNM face ROI unexpectedly small')
Gkd = build_kd(Gface)

# ---------------- DRL import + exact preceding bounded registration ----------------
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
    raise RuntimeError('DRL face ROI unexpectedly small')

sample_step = max(1, len(Dface_idx) // 7000)
Dsample_idx = Dface_idx[::sample_step][:7000]
prev = None
rigid_iterations = 0
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
        raise RuntimeError(f'rigid ICP collapsed at iteration {it}')
    Q, q = rigid_fit(cur[keep], matches[keep])
    R = Q @ R
    t = Q @ t + q
    rms = float(np.sqrt(np.mean(dist[keep] ** 2)))
    rigid_iterations = it + 1
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

# ---------------- registered donor triangle BVH ----------------
donor_faces = [tuple(int(i) for i in poly.vertices) for poly in drl.data.polygons]
bvh = BVHTree.FromPolygons([Vector(p) for p in Dwarp], donor_faces, all_triangles=False)

P = G[hockey_vid]
N = vertex_normals[hockey_vid]
Q = np.empty_like(P)
nearest_dist = np.empty(len(P), dtype=np.float64)
nearest_valid = np.zeros(len(P), dtype=bool)
for i, p in enumerate(P):
    loc, _, _, dist = bvh.find_nearest(Vector(p))
    if loc is not None:
        Q[i] = tuple(loc)
        nearest_dist[i] = float(dist)
        nearest_valid[i] = True

valid_fraction = float(np.mean(nearest_valid))
if valid_fraction < 0.95:
    raise RuntimeError(f'valid BVH nearest fraction too low: {valid_fraction:.4f}')
P = P[nearest_valid]
N = N[nearest_valid]
Q = Q[nearest_valid]
nearest_dist = nearest_dist[nearest_valid]

summary = summarize_signed_offsets(P, N, Q)

# Direct ray reachability, independent of Cycles. 40 mm matches the failed gate max distance.
ray_max = 0.040
ray_eps = 1e-5
plus_hit = np.zeros(len(P), dtype=bool)
minus_hit = np.zeros(len(P), dtype=bool)
plus_distance = np.full(len(P), np.nan)
minus_distance = np.full(len(P), np.nan)
for i, (p, n) in enumerate(zip(P, N)):
    lp, _, _, dp = bvh.ray_cast(Vector(p + n * ray_eps), Vector(n), ray_max)
    lm, _, _, dm = bvh.ray_cast(Vector(p - n * ray_eps), Vector(-n), ray_max)
    if lp is not None:
        plus_hit[i] = True
        plus_distance[i] = float(dp)
    if lm is not None:
        minus_hit[i] = True
        minus_distance[i] = float(dm)

plus_ray_fraction = float(np.mean(plus_hit))
minus_ray_fraction = float(np.mean(minus_hit))
any_ray_fraction = float(np.mean(plus_hit | minus_hit))
both_ray_fraction = float(np.mean(plus_hit & minus_hit))

if plus_ray_fraction >= minus_ray_fraction + 0.20:
    ray_direction = 'PLUS_N_MORE_REACHABLE'
elif minus_ray_fraction >= plus_ray_fraction + 0.20:
    ray_direction = 'MINUS_N_MORE_REACHABLE'
else:
    ray_direction = 'MIXED_OR_SIMILAR_REACHABILITY'

if summary['decision'] == 'DOMINANT_PLUS_N' or ray_direction == 'PLUS_N_MORE_REACHABLE':
    recommended_next = 'EXPLICIT_CAGE_PLUS_N_AND_CPU_AB'
elif summary['decision'] == 'DOMINANT_MINUS_N' and ray_direction == 'MINUS_N_MORE_REACHABLE':
    recommended_next = 'VERIFY_CYCLES_INWARD_CONFIG_AND_CPU_AB'
else:
    recommended_next = 'EXPLICIT_REGION_AWARE_CAGE_AND_CPU_AB'

metrics = {
    'gate': 'DRL_GNM_RAY_GEOMETRY_DIAGNOSTIC',
    'gnm_hockey_vertices_total': int(hockey_vertex_mask.sum()),
    'samples': int(len(P)),
    'valid_nearest_fraction': valid_fraction,
    'normal_orientation': {
        'outward_fraction_before_global_flip': orientation_positive_before,
        'global_flip_applied': bool(normal_global_flip),
        'outward_fraction_after_global_flip': orientation_positive_after,
    },
    'registration': {
        'rigid_iterations': int(rigid_iterations),
        'nonrigid_iterations': 7,
        'max_cumulative_deformation_mm': 24.0,
    },
    'nearest_surface': summary,
    'direct_ray_40mm': {
        'plus_n_hit_fraction': plus_ray_fraction,
        'minus_n_hit_fraction': minus_ray_fraction,
        'any_direction_hit_fraction': any_ray_fraction,
        'both_direction_hit_fraction': both_ray_fraction,
        'classification': ray_direction,
        'plus_n_hit_median_mm': float(np.nanmedian(plus_distance) * 1000.0) if plus_hit.any() else None,
        'minus_n_hit_median_mm': float(np.nanmedian(minus_distance) * 1000.0) if minus_hit.any() else None,
    },
    'recommended_next': recommended_next,
    'contract': {
        'stage1_does_not_modify_cycles_bake_settings': True,
        'real_diffuse_remains_blocked': True,
    },
}
(OUT / 'ray_geometry_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')

# Safe sample table: distances/directions only; no DRL vertex positions, UVs, or identity maps.
delta = Q - P
signed = np.einsum('ij,ij->i', delta, N)
tangent = np.linalg.norm(delta - signed[:, None] * N, axis=1)
with (OUT / 'ray_geometry_samples.csv').open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['sample', 'nearest_mm', 'signed_normal_mm', 'tangential_mm', 'plus_ray_hit_40mm', 'minus_ray_hit_40mm'])
    stride = max(1, len(P) // 1200)
    for i in range(0, len(P), stride):
        w.writerow([
            i,
            float(nearest_dist[i] * 1000.0),
            float(signed[i] * 1000.0),
            float(tangent[i] * 1000.0),
            int(plus_hit[i]),
            int(minus_hit[i]),
        ])

print(json.dumps(metrics, indent=2))
