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

from tools.experiments.transfer_ab_math import rasterize_uv_triangle

GNM_MODEL = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
DRL_OBJ = Path(os.environ['DRL_OBJ'])
OUT = Path('artifacts/drl-gnm-transfer-ab-gate')
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path('/tmp/drl-gnm-transfer-ab')
TMP.mkdir(parents=True, exist_ok=True)
RES = int(os.environ.get('COVERAGE_SIZE', '1024'))
RAY_MAX = 0.040
RAY_EPS = 1e-5
CAGE_MARGIN = 0.004
CAGE_MAX_OFFSET = 0.030

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
    m = n > max_len
    scale[m] = max_len / np.maximum(n[m], 1e-12)
    return v * scale[:, None]


def face_all(mask, tris):
    return mask[tris].all(axis=1)


def vertex_normals(vertices, faces):
    tri = vertices[faces]
    fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    vn = np.zeros_like(vertices)
    for k in range(3):
        np.add.at(vn, faces[:, k], fn)
    ln = np.linalg.norm(vn, axis=1)
    good = ln > 1e-12
    vn[good] /= ln[good, None]
    return vn, good


def save_mask(mask, path):
    Image.fromarray((mask.astype(np.uint8) * 255), mode='L').save(path)


def make_expected_owner(target_faces, target_uvs):
    owner = np.full((RES, RES), -1, dtype=np.int32)
    barymap = np.zeros((RES, RES, 3), dtype=np.float32)
    overlaps = 0
    for local_fid, uvtri in enumerate(target_uvs):
        xy, bary = rasterize_uv_triangle(uvtri, RES)
        if len(xy) == 0:
            continue
        # raster helper uses UV lower-left; PNG/NumPy rows are upper-left.
        x = xy[:, 0]
        y = RES - 1 - xy[:, 1]
        empty = owner[y, x] < 0
        overlaps += int((~empty).sum())
        if np.any(empty):
            owner[y[empty], x[empty]] = local_fid
            barymap[y[empty], x[empty]] = bary[empty]
    return owner, barymap, overlaps


# ---------------- GNM canonical geometry / UV / semantic scope ----------------
with np.load(GNM_MODEL, allow_pickle=False) as d:
    gv = np.asarray(d['template_vertex_positions'], dtype=np.float64)
    gt = np.asarray(d['triangles'], dtype=np.int64)
    guv = np.asarray(d['triangle_uvs'], dtype=np.float64)
    vg = np.asarray(d['vertex_groups'], dtype=np.float64)
    names = [str(x) for x in d['vertex_group_names']]

if guv.shape[:2] != gt.shape or guv.shape[2] != 2:
    raise RuntimeError(f'unexpected triangle_uvs shape {guv.shape}')
idx = {n: i for i, n in enumerate(names)}
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
if len(hockey_face_ids) < 2000:
    raise RuntimeError(f'hockey face count unexpectedly small: {len(hockey_face_ids)}')

skin_faces = gt[face_all(gskin, gt)]
GN, normal_good = vertex_normals(G, skin_faces)
used_vid = np.unique(target_faces.reshape(-1))
if not np.all(normal_good[used_vid]):
    raise RuntimeError('hockey target contains invalid vertex normals')
head_center = G[np.flatnonzero(gskin)].mean(0)
radial = G[used_vid] - head_center
outward_before = float(np.mean(np.einsum('ij,ij->i', GN[used_vid], radial) > 0))
if outward_before < 0.5:
    GN *= -1.0
outward_after = float(np.mean(np.einsum('ij,ij->i', GN[used_vid], radial) > 0))
if outward_after < 0.70:
    raise RuntimeError(f'GNM outward normal orientation unresolved: {outward_after:.4f}')

Gskin = G[np.flatnonzero(gskin)]
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
drl.name = 'DRL_Coverage_Donor'
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

for v, p in zip(drl.data.vertices, Dwarp):
    v.co = tuple(p)
for p in drl.data.polygons:
    p.use_smooth = True
for o in meshes:
    if o != drl:
        o.hide_render = True
drl.hide_render = False

# Donor triangle BVH after registration.
donor_faces = [tuple(int(i) for i in poly.vertices) for poly in drl.data.polygons]
bvh = BVHTree.FromPolygons([Vector(p) for p in Dwarp], donor_faces, all_triangles=False)

# Shared UV raster contract.
owner, barymap, uv_overlap_writes = make_expected_owner(target_faces, target_uvs)
expected = owner >= 0
expected_count = int(expected.sum())
if expected_count < RES * RES * 0.02:
    raise RuntimeError(f'expected hockey UV footprint too small: {expected_count}')
save_mask(expected, OUT / 'expected_hockey_uv.png')

# ---------------- A: explicit mixed-side region-aware cage ----------------
# Per used target vertex, find which normal direction reaches the donor nearest.
cage_offsets = np.zeros(len(G), dtype=np.float64)
vertex_side = np.zeros(len(G), dtype=np.int8)
vertex_hit_distance = np.full(len(G), np.nan, dtype=np.float64)
for vid in used_vid:
    p = G[vid]
    n = GN[vid]
    lp, _, _, dp = bvh.ray_cast(Vector(p + n * RAY_EPS), Vector(n), RAY_MAX)
    lm, _, _, dm = bvh.ray_cast(Vector(p - n * RAY_EPS), Vector(-n), RAY_MAX)
    hp, hm = lp is not None, lm is not None
    if hp and (not hm or float(dp) <= float(dm)):
        sign, dd = 1, float(dp)
    elif hm:
        sign, dd = -1, float(dm)
    else:
        loc, _, _, nd = bvh.find_nearest(Vector(p))
        if loc is None:
            continue
        delta = np.asarray(tuple(loc), dtype=np.float64) - p
        signed = float(np.dot(delta, n))
        sign = 1 if signed >= 0 else -1
        dd = float(nd)
    vertex_side[vid] = sign
    vertex_hit_distance[vid] = dd
    offset = min(max(dd + CAGE_MARGIN, 0.006), CAGE_MAX_OFFSET)
    cage_offsets[vid] = sign * offset

cage_G = G.copy()
cage_G[used_vid] = G[used_vid] + GN[used_vid] * cage_offsets[used_vid, None]

# Cage structural diagnostics before Cycles uses it.
target_tri = G[target_faces]
cage_tri = cage_G[target_faces]
target_fn = np.cross(target_tri[:, 1] - target_tri[:, 0], target_tri[:, 2] - target_tri[:, 0])
cage_fn = np.cross(cage_tri[:, 1] - cage_tri[:, 0], cage_tri[:, 2] - cage_tri[:, 0])
face_dot = np.einsum('ij,ij->i', target_fn, cage_fn)
cage_face_flip_fraction = float(np.mean(face_dot <= 0))

def tri_edges(tri):
    return np.stack([
        np.linalg.norm(tri[:, 1] - tri[:, 0], axis=1),
        np.linalg.norm(tri[:, 2] - tri[:, 1], axis=1),
        np.linalg.norm(tri[:, 0] - tri[:, 2], axis=1),
    ], axis=1)

te = tri_edges(target_tri)
ce = tri_edges(cage_tri)
edge_ratio = ce / np.maximum(te, 1e-12)
cage_edge_ratio_p95 = float(np.percentile(edge_ratio, 95))
cage_edge_ratio_p05 = float(np.percentile(edge_ratio, 5))

# Build target and cage with identical topology/order.
tmesh = bpy.data.meshes.new('GNM_Hockey_AB_Target_Mesh')
tmesh.from_pydata(G.tolist(), [], target_faces.tolist())
tmesh.update()
target = bpy.data.objects.new('GNM_Hockey_AB_Target', tmesh)
bpy.context.collection.objects.link(target)
tuv = tmesh.uv_layers.new(name='UVMap')
for poly, uvtri in zip(tmesh.polygons, target_uvs):
    for li, uvco in zip(poly.loop_indices, uvtri):
        tuv.data[li].uv = tuple(uvco)
    poly.use_smooth = True

cmesh = bpy.data.meshes.new('GNM_Hockey_AB_Cage_Mesh')
cmesh.from_pydata(cage_G.tolist(), [], target_faces.tolist())
cmesh.update()
cage = bpy.data.objects.new('GNM_Hockey_AB_Cage', cmesh)
bpy.context.collection.objects.link(cage)
cage.hide_render = True

source_mat = bpy.data.materials.new('DRL_White_Emission')
source_mat.use_nodes = True
snt = source_mat.node_tree
snt.nodes.clear()
sout = snt.nodes.new('ShaderNodeOutputMaterial')
semit = snt.nodes.new('ShaderNodeEmission')
semit.inputs['Color'].default_value = (1, 1, 1, 1)
semit.inputs['Strength'].default_value = 1.0
snt.links.new(semit.outputs['Emission'], sout.inputs['Surface'])
drl.data.materials.clear()
drl.data.materials.append(source_mat)

target_mat = bpy.data.materials.new('GNM_AB_Bake_Target')
target_mat.use_nodes = True
tnt = target_mat.node_tree
tnt.nodes.clear()
tout = tnt.nodes.new('ShaderNodeOutputMaterial')
tbsdf = tnt.nodes.new('ShaderNodeBsdfPrincipled')
tnt.links.new(tbsdf.outputs['BSDF'], tout.inputs['Surface'])
bake_node = tnt.nodes.new('ShaderNodeTexImage')
target.data.materials.clear()
target.data.materials.append(target_mat)

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.render.bake.use_selected_to_active = True
scene.render.bake.use_cage = True
scene.render.bake.cage_object = cage
scene.render.bake.cage_extrusion = 0.0
scene.render.bake.max_ray_distance = 0.0
scene.render.bake.margin = 0
scene.render.bake.use_clear = True

cycles_img = bpy.data.images.new('Cycles_Explicit_Cage_Coverage', width=RES, height=RES, alpha=True)
cycles_img.generated_color = (0, 0, 0, 0)
cycles_img.colorspace_settings.name = 'Non-Color'
bake_node.image = cycles_img
tnt.nodes.active = bake_node
for node in tnt.nodes:
    node.select = node == bake_node

bpy.ops.object.select_all(action='DESELECT')
drl.select_set(True)
target.select_set(True)
bpy.context.view_layer.objects.active = target
cycles_error = None
try:
    bpy.ops.object.bake(type='EMIT')
except Exception as exc:
    cycles_error = repr(exc)

cycles_pixels = np.asarray(cycles_img.pixels[:], dtype=np.float32).reshape(RES, RES, 4)
# Blender image pixel array is bottom-up relative to NumPy/PIL image row convention.
cycles_raw = np.max(cycles_pixels[:, :, :3], axis=2) > 0.5
cycles_cov = np.flipud(cycles_raw)
cycles_hit = int((cycles_cov & expected).sum())
cycles_fraction = float(cycles_hit / max(expected_count, 1))
save_mask(cycles_cov, OUT / 'cycles_explicit_cage_coverage.png')

# ---------------- B: deterministic bidirectional CPU correspondence ----------------
yx = np.argwhere(expected)
cpu_cov = np.zeros((RES, RES), dtype=bool)
cpu_choice_plus = 0
cpu_choice_minus = 0
cpu_both = 0
cpu_distances = []
cpu_normal_abs_dots = []

for y, x in yx:
    local_fid = int(owner[y, x])
    tri_vid = target_faces[local_fid]
    bary = barymap[y, x].astype(np.float64)
    p = bary @ G[tri_vid]
    n = bary @ GN[tri_vid]
    nl = float(np.linalg.norm(n))
    if nl <= 1e-12:
        continue
    n /= nl

    lp, np_hit, fp, dp = bvh.ray_cast(Vector(p + n * RAY_EPS), Vector(n), RAY_MAX)
    lm, nm_hit, fm, dm = bvh.ray_cast(Vector(p - n * RAY_EPS), Vector(-n), RAY_MAX)
    hp, hm = lp is not None, lm is not None
    if hp and hm:
        cpu_both += 1
    if not hp and not hm:
        continue
    if hp and (not hm or float(dp) <= float(dm)):
        chosen_dist = float(dp)
        chosen_normal = np.asarray(tuple(np_hit), dtype=np.float64) if np_hit is not None else None
        cpu_choice_plus += 1
    else:
        chosen_dist = float(dm)
        chosen_normal = np.asarray(tuple(nm_hit), dtype=np.float64) if nm_hit is not None else None
        cpu_choice_minus += 1

    # Reject an almost-tangent donor hit. Use absolute normal agreement because
    # donor winding is source-specific; 75 degrees still allows facial curvature.
    if chosen_normal is not None:
        ln = float(np.linalg.norm(chosen_normal))
        if ln > 1e-12:
            ndot = abs(float(np.dot(n, chosen_normal / ln)))
            cpu_normal_abs_dots.append(ndot)
            if ndot < math.cos(math.radians(75.0)):
                continue
    cpu_cov[y, x] = True
    cpu_distances.append(chosen_dist)

cpu_hit = int((cpu_cov & expected).sum())
cpu_fraction = float(cpu_hit / max(expected_count, 1))
save_mask(cpu_cov, OUT / 'cpu_bidirectional_coverage.png')

# Combined safe diagnostic: green both, cyan CPU only, yellow cage only, red miss both.
diag = np.zeros((RES, RES, 3), dtype=np.uint8)
both = expected & cycles_cov & cpu_cov
cpu_only = expected & cpu_cov & ~cycles_cov
cage_only = expected & cycles_cov & ~cpu_cov
miss = expected & ~cycles_cov & ~cpu_cov
diag[both] = (40, 190, 70)
diag[cpu_only] = (40, 190, 220)
diag[cage_only] = (235, 190, 30)
diag[miss] = (230, 45, 35)
Image.fromarray(diag, mode='RGB').save(OUT / 'ab_coverage_comparison.png')

cage_safe = cage_face_flip_fraction <= 0.01 and cage_edge_ratio_p95 <= 3.0 and cage_edge_ratio_p05 >= 0.25
cycles_pass = cycles_fraction >= 0.95 and cage_safe and cycles_error is None
cpu_pass = cpu_fraction >= 0.95

if cpu_pass and (not cycles_pass or cpu_fraction >= cycles_fraction - 0.01):
    selected_backend = 'CPU_BIDIRECTIONAL_CORRESPONDENCE'
elif cycles_pass:
    selected_backend = 'BLENDER_EXPLICIT_REGION_AWARE_CAGE'
else:
    selected_backend = 'NONE_BLOCKED'

metrics = {
    'gate': 'DRL_GNM_TRANSFER_AB_COVERAGE',
    'resolution': RES,
    'expected_hockey_uv_pixels': expected_count,
    'uv_overlap_writes': int(uv_overlap_writes),
    'gnm': {
        'hockey_faces': int(len(target_faces)),
        'used_vertices': int(len(used_vid)),
        'outward_normal_fraction': outward_after,
    },
    'registration': {
        'rigid_iterations': int(rigid_iterations),
        'nonrigid_iterations': 7,
        'max_cumulative_deformation_mm': 24.0,
    },
    'A_explicit_cage': {
        'coverage_pixels': cycles_hit,
        'coverage_fraction': cycles_fraction,
        'pass_95pct': bool(cycles_pass),
        'cycles_error': cycles_error,
        'use_cage': True,
        'cage_object': cage.name,
        'max_ray_distance_m': 0.0,
        'cage_face_flip_fraction': cage_face_flip_fraction,
        'cage_edge_ratio_p05': cage_edge_ratio_p05,
        'cage_edge_ratio_p95': cage_edge_ratio_p95,
        'cage_safe_contract': bool(cage_safe),
        'vertex_plus_side_fraction': float(np.mean(vertex_side[used_vid] == 1)),
        'vertex_minus_side_fraction': float(np.mean(vertex_side[used_vid] == -1)),
        'vertex_no_hit_fraction': float(np.mean(vertex_side[used_vid] == 0)),
        'offset_abs_median_mm': float(np.median(np.abs(cage_offsets[used_vid])) * 1000.0),
        'offset_abs_p95_mm': float(np.percentile(np.abs(cage_offsets[used_vid]), 95) * 1000.0),
    },
    'B_cpu_bidirectional': {
        'coverage_pixels': cpu_hit,
        'coverage_fraction': cpu_fraction,
        'pass_95pct': bool(cpu_pass),
        'chosen_plus_count': int(cpu_choice_plus),
        'chosen_minus_count': int(cpu_choice_minus),
        'both_direction_hit_count': int(cpu_both),
        'hit_distance_median_mm': float(np.median(cpu_distances) * 1000.0) if cpu_distances else None,
        'hit_distance_p95_mm': float(np.percentile(cpu_distances, 95) * 1000.0) if cpu_distances else None,
        'normal_abs_dot_median': float(np.median(cpu_normal_abs_dots)) if cpu_normal_abs_dots else None,
        'normal_compatibility_floor': float(math.cos(math.radians(75.0))),
        'deterministic_mapping_reusable_for_multiple_maps': True,
    },
    'comparison': {
        'both_backend_pixels': int(both.sum()),
        'cpu_only_pixels': int(cpu_only.sum()),
        'cage_only_pixels': int(cage_only.sum()),
        'miss_both_pixels': int(miss.sum()),
        'selected_backend': selected_backend,
        'real_diffuse_allowed_next': bool(selected_backend != 'NONE_BLOCKED'),
    },
    'source_protection': {
        'raw_drl_obj_uploaded': False,
        'raw_identity_texture_used': False,
        'identity_texture_uploaded': False,
    },
}
(OUT / 'transfer_ab_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
