import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from PIL import Image

from tools.experiments.transfer_ab_math import rasterize_uv_triangle, accept_nearest_fallback

GNM_MODEL = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
DRL_OBJ = Path(os.environ['DRL_OBJ'])
OUT = Path('artifacts/drl-gnm-cpu-fallback-gate')
OUT.mkdir(parents=True, exist_ok=True)
RES = int(os.environ.get('COVERAGE_SIZE', '1024'))
RAY_MAX = 0.040
RAY_EPS = 1e-5
BASE_NORMAL_FLOOR = float(math.cos(math.radians(75.0)))
FALLBACK_MAX_DISTANCE = 0.015
FALLBACK_NORMAL_FLOOR = 0.5

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
    scale = np.ones_like(n)
    mask = n > max_len
    scale[mask] = max_len / np.maximum(n[mask], 1e-12)
    return v * scale[:, None]


def face_all(mask, tris):
    return mask[tris].all(axis=1)


def vertex_normals(vertices, faces):
    tri = vertices[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    lengths = np.linalg.norm(vn, axis=1)
    good = lengths > 1e-12
    vn[good] /= lengths[good, None]
    return vn, good


def save_mask(mask, path):
    Image.fromarray((mask.astype(np.uint8) * 255), mode='L').save(path)


def rasterize_target(target_faces, target_uvs):
    owner = np.full((RES, RES), -1, dtype=np.int32)
    barymap = np.zeros((RES, RES, 3), dtype=np.float32)
    overlaps = 0
    for local_fid, uvtri in enumerate(target_uvs):
        xy, bary = rasterize_uv_triangle(uvtri, RES)
        if len(xy) == 0:
            continue
        x = xy[:, 0]
        y = RES - 1 - xy[:, 1]
        empty = owner[y, x] < 0
        overlaps += int((~empty).sum())
        if np.any(empty):
            owner[y[empty], x[empty]] = local_fid
            barymap[y[empty], x[empty]] = bary[empty]
    return owner, barymap, overlaps


# ---------------- GNM canonical geometry ----------------
with np.load(GNM_MODEL, allow_pickle=False) as data:
    gv = np.asarray(data['template_vertex_positions'], dtype=np.float64)
    gt = np.asarray(data['triangles'], dtype=np.int64)
    guv = np.asarray(data['triangle_uvs'], dtype=np.float64)
    vg = np.asarray(data['vertex_groups'], dtype=np.float64)
    names = [str(x) for x in data['vertex_group_names']]

if guv.shape[:2] != gt.shape or guv.shape[2] != 2:
    raise RuntimeError(f'unexpected triangle_uvs shape {guv.shape}')
idx = {name: i for i, name in enumerate(names)}
for needed in ('skin', 'hockey_mask'):
    if needed not in idx:
        raise RuntimeError(f'GNM semantic group missing: {needed}')

G = np.stack([gv[:, 0], -gv[:, 2], gv[:, 1]], axis=1)
gskin = vg[idx['skin']] > 0.5
hockey = vg[idx['hockey_mask']] > 0.5
hockey_vertices = gskin & hockey
hockey_face_ids = np.flatnonzero(face_all(hockey_vertices, gt))
target_faces = gt[hockey_face_ids]
target_uvs = guv[hockey_face_ids]
if len(target_faces) < 2000:
    raise RuntimeError(f'hockey face count unexpectedly small: {len(target_faces)}')

skin_faces = gt[face_all(gskin, gt)]
GN, normal_good = vertex_normals(G, skin_faces)
used_vid = np.unique(target_faces.reshape(-1))
if not np.all(normal_good[used_vid]):
    raise RuntimeError('hockey target contains invalid normals')

Gskin = G[np.flatnonzero(gskin)]
gmin, gmax = Gskin.min(0), Gskin.max(0)
gext = gmax - gmin
head_center = Gskin.mean(0)
radial = G[used_vid] - head_center
outward_before = float(np.mean(np.einsum('ij,ij->i', GN[used_vid], radial) > 0))
if outward_before < 0.5:
    GN *= -1.0
outward_after = float(np.mean(np.einsum('ij,ij->i', GN[used_vid], radial) > 0))
if outward_after < 0.70:
    raise RuntimeError(f'GNM outward normal orientation unresolved: {outward_after:.4f}')

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

# ---------------- DRL import + exact accepted bounded registration ----------------
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
for iteration in range(18):
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
        raise RuntimeError(f'rigid ICP collapsed at iteration {iteration}')
    Q, q = rigid_fit(cur[keep], matches[keep])
    R = Q @ R
    t = Q @ t + q
    rms = float(np.sqrt(np.mean(dist[keep] ** 2)))
    rigid_iterations = iteration + 1
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

# Registered donor BVH. No identity textures are loaded.
donor_faces = [tuple(int(i) for i in poly.vertices) for poly in drl.data.polygons]
bvh = BVHTree.FromPolygons([Vector(p) for p in Dwarp], donor_faces, all_triangles=False)

# ---------------- target UV raster ----------------
owner, barymap, uv_overlap_writes = rasterize_target(target_faces, target_uvs)
expected = owner >= 0
expected_count = int(expected.sum())
if expected_count < 10000:
    raise RuntimeError(f'expected hockey UV footprint too small: {expected_count}')
save_mask(expected, OUT / 'expected_hockey_uv.png')

base_cov = np.zeros((RES, RES), dtype=bool)
fallback_cov = np.zeros((RES, RES), dtype=bool)
no_ray_mask = np.zeros((RES, RES), dtype=bool)
ray_normal_reject_mask = np.zeros((RES, RES), dtype=bool)
remaining_miss = np.zeros((RES, RES), dtype=bool)

base_ray_hit_count = 0
base_normal_reject_count = 0
base_plus_count = 0
base_minus_count = 0
base_both_count = 0
fallback_attempted = 0
fallback_accepted = 0
fallback_from_no_ray = 0
fallback_from_normal_reject = 0
base_distances = []
base_normal_dots = []
fallback_distances = []
fallback_normal_dots = []

for y, x in np.argwhere(expected):
    local_fid = int(owner[y, x])
    tri_vid = target_faces[local_fid]
    bary = barymap[y, x].astype(np.float64)
    p = bary @ G[tri_vid]
    n = bary @ GN[tri_vid]
    nlen = float(np.linalg.norm(n))
    if nlen <= 1e-12:
        remaining_miss[y, x] = True
        continue
    n /= nlen

    lp, np_hit, _, dp = bvh.ray_cast(Vector(p + n * RAY_EPS), Vector(n), RAY_MAX)
    lm, nm_hit, _, dm = bvh.ray_cast(Vector(p - n * RAY_EPS), Vector(-n), RAY_MAX)
    hp, hm = lp is not None, lm is not None
    if hp and hm:
        base_both_count += 1

    chosen_dist = None
    chosen_normal = None
    if hp and (not hm or float(dp) <= float(dm)):
        chosen_dist = float(dp)
        chosen_normal = np.asarray(tuple(np_hit), dtype=np.float64) if np_hit is not None else None
        base_plus_count += 1
    elif hm:
        chosen_dist = float(dm)
        chosen_normal = np.asarray(tuple(nm_hit), dtype=np.float64) if nm_hit is not None else None
        base_minus_count += 1

    base_accepted = False
    prior_class = 'NO_RAY'
    if chosen_dist is not None:
        base_ray_hit_count += 1
        base_distances.append(chosen_dist)
        normal_abs_dot = 1.0
        if chosen_normal is not None:
            ln = float(np.linalg.norm(chosen_normal))
            if ln > 1e-12:
                normal_abs_dot = abs(float(np.dot(n, chosen_normal / ln)))
        base_normal_dots.append(normal_abs_dot)
        if normal_abs_dot >= BASE_NORMAL_FLOOR:
            base_accepted = True
            base_cov[y, x] = True
        else:
            prior_class = 'NORMAL_REJECT'
            ray_normal_reject_mask[y, x] = True
            base_normal_reject_count += 1
    else:
        no_ray_mask[y, x] = True

    if base_accepted:
        continue

    # Fixed fallback contract: nearest donor point <= 15 mm and surface normals within 60 degrees.
    fallback_attempted += 1
    loc, donor_normal, _, nearest_distance = bvh.find_nearest(Vector(p))
    if loc is None or donor_normal is None:
        remaining_miss[y, x] = True
        continue
    donor_normal = np.asarray(tuple(donor_normal), dtype=np.float64)
    dnlen = float(np.linalg.norm(donor_normal))
    if dnlen <= 1e-12:
        remaining_miss[y, x] = True
        continue
    nearest_distance = float(nearest_distance)
    normal_abs_dot = abs(float(np.dot(n, donor_normal / dnlen)))
    accepted = bool(accept_nearest_fallback(
        np.asarray([nearest_distance]),
        np.asarray([normal_abs_dot]),
        max_distance=FALLBACK_MAX_DISTANCE,
        min_abs_dot=FALLBACK_NORMAL_FLOOR,
    )[0])
    if accepted:
        fallback_cov[y, x] = True
        fallback_accepted += 1
        fallback_distances.append(nearest_distance)
        fallback_normal_dots.append(normal_abs_dot)
        if prior_class == 'NO_RAY':
            fallback_from_no_ray += 1
        else:
            fallback_from_normal_reject += 1
    else:
        remaining_miss[y, x] = True

hybrid_cov = base_cov | fallback_cov
base_count = int(base_cov.sum())
hybrid_count = int(hybrid_cov.sum())
base_fraction = float(base_count / expected_count)
hybrid_fraction = float(hybrid_count / expected_count)
remaining_count = int((expected & ~hybrid_cov).sum())

save_mask(base_cov, OUT / 'base_cpu_coverage.png')
save_mask(fallback_cov, OUT / 'fallback_accepted.png')
save_mask(hybrid_cov, OUT / 'hybrid_coverage.png')
save_mask(remaining_miss, OUT / 'remaining_miss.png')

# Green=base ray, cyan=fallback, red=still missing.
diag = np.zeros((RES, RES, 3), dtype=np.uint8)
diag[expected & base_cov] = (40, 190, 70)
diag[expected & fallback_cov] = (40, 190, 220)
diag[expected & ~hybrid_cov] = (230, 45, 35)
Image.fromarray(diag, mode='RGB').save(OUT / 'hybrid_comparison.png')

hybrid_pass = hybrid_fraction >= 0.95
selected_backend = 'CPU_HYBRID_RAY_NEAREST_CORRESPONDENCE' if hybrid_pass else 'NONE_BLOCKED'
next_if_fail = None if hybrid_pass else 'SAFE_FACIAL_CORE_PLUS_FEATHER_SEAM'

metrics = {
    'gate': 'DRL_GNM_CPU_SAFE_FALLBACK_COVERAGE',
    'resolution': RES,
    'expected_hockey_uv_pixels': expected_count,
    'uv_overlap_writes': int(uv_overlap_writes),
    'registration': {
        'rigid_iterations': int(rigid_iterations),
        'nonrigid_iterations': 7,
        'max_cumulative_deformation_mm': 24.0,
    },
    'gnm': {
        'hockey_faces': int(len(target_faces)),
        'used_vertices': int(len(used_vid)),
        'outward_normal_fraction': outward_after,
    },
    'base_bidirectional_ray': {
        'ray_max_mm': RAY_MAX * 1000.0,
        'normal_angle_limit_deg': 75.0,
        'normal_abs_dot_floor': BASE_NORMAL_FLOOR,
        'raw_ray_hit_count': int(base_ray_hit_count),
        'no_ray_count': int(expected_count - base_ray_hit_count),
        'normal_reject_count': int(base_normal_reject_count),
        'accepted_count': base_count,
        'coverage_fraction': base_fraction,
        'chosen_plus_count': int(base_plus_count),
        'chosen_minus_count': int(base_minus_count),
        'both_direction_hit_count': int(base_both_count),
        'hit_distance_median_mm': float(np.median(base_distances) * 1000.0) if base_distances else None,
        'hit_distance_p95_mm': float(np.percentile(base_distances, 95) * 1000.0) if base_distances else None,
        'normal_abs_dot_median': float(np.median(base_normal_dots)) if base_normal_dots else None,
    },
    'fixed_nearest_fallback': {
        'max_distance_mm': FALLBACK_MAX_DISTANCE * 1000.0,
        'normal_angle_limit_deg': 60.0,
        'normal_abs_dot_floor': FALLBACK_NORMAL_FLOOR,
        'attempted_count': int(fallback_attempted),
        'accepted_count': int(fallback_accepted),
        'accepted_from_no_ray_count': int(fallback_from_no_ray),
        'accepted_from_ray_normal_reject_count': int(fallback_from_normal_reject),
        'accepted_distance_median_mm': float(np.median(fallback_distances) * 1000.0) if fallback_distances else None,
        'accepted_distance_p95_mm': float(np.percentile(fallback_distances, 95) * 1000.0) if fallback_distances else None,
        'accepted_normal_abs_dot_median': float(np.median(fallback_normal_dots)) if fallback_normal_dots else None,
        'accepted_normal_abs_dot_p05': float(np.percentile(fallback_normal_dots, 5)) if fallback_normal_dots else None,
        'thresholds_fixed_before_real_data_run': True,
    },
    'hybrid': {
        'coverage_pixels': hybrid_count,
        'coverage_fraction': hybrid_fraction,
        'remaining_miss_pixels': remaining_count,
        'remaining_miss_fraction': float(remaining_count / expected_count),
        'pass_95pct': bool(hybrid_pass),
        'selected_backend': selected_backend,
        'real_diffuse_allowed_next': bool(hybrid_pass),
        'next_if_fail': next_if_fail,
    },
    'source_protection': {
        'raw_drl_obj_uploaded': False,
        'raw_identity_texture_used': False,
        'identity_texture_uploaded': False,
    },
}

# Baseline reproduction guard: fail if this script no longer matches the prior 92.37% gate within 0.5 percentage points.
reference = 0.9236982985775775
metrics['base_bidirectional_ray']['reference_previous_fraction'] = reference
metrics['base_bidirectional_ray']['absolute_delta_from_previous'] = abs(base_fraction - reference)
if abs(base_fraction - reference) > 0.005:
    metrics['hybrid']['selected_backend'] = 'NONE_BLOCKED_BASELINE_DRIFT'
    metrics['hybrid']['real_diffuse_allowed_next'] = False
    metrics['hybrid']['pass_95pct'] = False
    metrics['hybrid']['next_if_fail'] = 'INVESTIGATE_BASELINE_DRIFT'

(OUT / 'cpu_fallback_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
