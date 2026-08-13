import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from PIL import Image, ImageStat, ImageDraw

from tools.experiments.transfer_ab_math import (
    accept_nearest_fallback,
    barycentric_coordinates_3d,
    build_feather_alpha,
    rasterize_uv_triangle,
    sample_image_bilinear,
)

GNM_MODEL = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
DRL_OBJ = Path(os.environ['DRL_OBJ'])
DRL_DIFFUSE = Path(os.environ['DRL_DIFFUSE'])
OUT = Path('artifacts/drl-gnm-diffuse-transfer-gate')
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path('/tmp/drl-gnm-diffuse-transfer')
TMP.mkdir(parents=True, exist_ok=True)
RES = int(os.environ.get('TRANSFER_SIZE', '1024'))
RAY_MAX = 0.040
RAY_EPS = 1e-5
BASE_NORMAL_FLOOR = float(math.cos(math.radians(75.0)))
FALLBACK_MAX_DISTANCE = 0.015
FALLBACK_NORMAL_FLOOR = 0.5
FEATHER_WIDTH = 16
REFERENCE_HYBRID = 0.9355081017276532

for p in (GNM_MODEL, DRL_OBJ, DRL_DIFFUSE):
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


def rasterize_target(target_faces, target_uvs):
    owner = np.full((RES, RES), -1, dtype=np.int32)
    barymap = np.zeros((RES, RES, 3), dtype=np.float32)
    for local_fid, uvtri in enumerate(target_uvs):
        xy, bary = rasterize_uv_triangle(uvtri, RES)
        if len(xy) == 0:
            continue
        x = xy[:, 0]
        y = RES - 1 - xy[:, 1]
        empty = owner[y, x] < 0
        if np.any(empty):
            owner[y[empty], x[empty]] = local_fid
            barymap[y[empty], x[empty]] = bary[empty]
    return owner, barymap


def simple_material(name, color, roughness=0.45, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = roughness
    if bsdf.inputs.get('Metallic'):
        bsdf.inputs['Metallic'].default_value = metallic
    return mat


def make_semantic_object(name, vertices, faces, group_mask, material):
    ids = np.flatnonzero(face_all(group_mask, faces))
    if len(ids) == 0:
        return None
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(vertices.tolist(), [], faces[ids].tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


# ---------------- GNM geometry / semantics / final UV ----------------
with np.load(GNM_MODEL, allow_pickle=False) as data:
    gv = np.asarray(data['template_vertex_positions'], dtype=np.float64)
    gt = np.asarray(data['triangles'], dtype=np.int64)
    guv = np.asarray(data['triangle_uvs'], dtype=np.float64)
    vg = np.asarray(data['vertex_groups'], dtype=np.float64)
    names = [str(x) for x in data['vertex_group_names']]

idx = {name: i for i, name in enumerate(names)}
for needed in ('skin', 'hockey_mask'):
    if needed not in idx:
        raise RuntimeError(f'GNM semantic group missing: {needed}')
if guv.shape[:2] != gt.shape or guv.shape[2] != 2:
    raise RuntimeError(f'unexpected GNM triangle UV shape: {guv.shape}')

G = np.stack([gv[:, 0], -gv[:, 2], gv[:, 1]], axis=1)
gskin = vg[idx['skin']] > 0.5
hockey = vg[idx['hockey_mask']] > 0.5
hockey_vertices = gskin & hockey
hockey_face_ids = np.flatnonzero(face_all(hockey_vertices, gt))
target_faces = gt[hockey_face_ids]
target_uvs = guv[hockey_face_ids]
skin_face_ids = np.flatnonzero(face_all(gskin, gt))
skin_faces = gt[skin_face_ids]
skin_uvs = guv[skin_face_ids]
if len(target_faces) < 2000:
    raise RuntimeError('hockey semantic face set unexpectedly small')

GN, normal_good = vertex_normals(G, skin_faces)
used_vid = np.unique(target_faces.reshape(-1))
if not np.all(normal_good[used_vid]):
    raise RuntimeError('hockey target contains invalid vertex normals')
Gskin = G[np.flatnonzero(gskin)]
gmin, gmax = Gskin.min(0), Gskin.max(0)
gext = gmax - gmin
head_center = Gskin.mean(0)
radial = G[used_vid] - head_center
if float(np.mean(np.einsum('ij,ij->i', GN[used_vid], radial) > 0)) < 0.5:
    GN *= -1.0
outward_fraction = float(np.mean(np.einsum('ij,ij->i', GN[used_vid], radial) > 0))
if outward_fraction < 0.70:
    raise RuntimeError(f'GNM outward normals unresolved: {outward_fraction:.4f}')

gn = (Gskin - gmin) / gext
face_local = (
    (np.abs(gn[:, 0] - 0.5) <= 0.44)
    & (gn[:, 2] >= 0.30)
    & (gn[:, 2] <= 0.96)
    & (gn[:, 1] <= 0.56)
)
Gface = Gskin[face_local]
Gkd = build_kd(Gface)

# ---------------- DRL import + accepted registration ----------------
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.wm.obj_import(filepath=str(DRL_OBJ.resolve()))
except Exception:
    bpy.ops.import_scene.obj(filepath=str(DRL_OBJ.resolve()))
source_meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not source_meshes:
    raise RuntimeError('DRL OBJ import produced no mesh')
drl = max(source_meshes, key=lambda o: len(o.data.polygons))
if not drl.data.uv_layers or drl.data.uv_layers.active is None:
    raise RuntimeError('DRL donor head has no active UV layer')
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

# Keep donor UV topology; only positions are registered.
for vertex, pos in zip(drl.data.vertices, Dwarp):
    vertex.co = tuple(pos)
drl.data.update()
drl.data.calc_loop_triangles()
uv_layer = drl.data.uv_layers.active.data
loop_tris = list(drl.data.loop_triangles)
if not loop_tris:
    raise RuntimeError('DRL donor has no loop triangles')
donor_tri_vertices = np.asarray([tuple(tri.vertices) for tri in loop_tris], dtype=np.int64)
donor_tri_positions = Dwarp[donor_tri_vertices]
donor_tri_uv = np.asarray([
    [tuple(uv_layer[loop_index].uv) for loop_index in tri.loops]
    for tri in loop_tris
], dtype=np.float64)
if not np.isfinite(donor_tri_uv).all():
    raise RuntimeError('DRL donor UV contains non-finite values')

bvh = BVHTree.FromPolygons(
    [Vector(p) for p in Dwarp],
    [tuple(map(int, tri)) for tri in donor_tri_vertices],
    all_triangles=True,
)

# ---------------- target texels → donor triangle/UV correspondence ----------------
owner, barymap = rasterize_target(target_faces, target_uvs)
expected = owner >= 0
expected_count = int(expected.sum())
valid = np.zeros((RES, RES), dtype=bool)
donor_uv_map = np.full((RES, RES, 2), np.nan, dtype=np.float32)
method_map = np.zeros((RES, RES), dtype=np.uint8)  # 1=ray, 2=nearest fallback
bary_sum_errors = []
bary_min_values = []
donor_uv_outside_unit = 0
invalid_face_index = 0
ray_accepted = 0
fallback_accepted = 0

for y, x in np.argwhere(expected):
    local_fid = int(owner[y, x])
    tri_vid = target_faces[local_fid]
    bary = barymap[y, x].astype(np.float64)
    p = bary @ G[tri_vid]
    n = bary @ GN[tri_vid]
    nlen = float(np.linalg.norm(n))
    if nlen <= 1e-12:
        continue
    n /= nlen

    candidates = []
    lp, np_hit, fp, dp = bvh.ray_cast(Vector(p + n * RAY_EPS), Vector(n), RAY_MAX)
    lm, nm_hit, fm, dm = bvh.ray_cast(Vector(p - n * RAY_EPS), Vector(-n), RAY_MAX)
    if lp is not None:
        candidates.append((float(dp), lp, np_hit, int(fp), 1))
    if lm is not None:
        candidates.append((float(dm), lm, nm_hit, int(fm), 1))
    candidates.sort(key=lambda item: item[0])

    chosen = None
    for distance, loc, donor_normal, face_index, method in candidates:
        if donor_normal is None:
            normal_dot = 1.0
        else:
            dnrm = np.asarray(tuple(donor_normal), dtype=np.float64)
            ln = float(np.linalg.norm(dnrm))
            normal_dot = abs(float(np.dot(n, dnrm / ln))) if ln > 1e-12 else 0.0
        if normal_dot >= BASE_NORMAL_FLOOR:
            chosen = (distance, loc, face_index, method)
            break

    if chosen is None:
        loc, donor_normal, face_index, nearest_distance = bvh.find_nearest(Vector(p))
        if loc is not None and donor_normal is not None:
            dnrm = np.asarray(tuple(donor_normal), dtype=np.float64)
            ln = float(np.linalg.norm(dnrm))
            normal_dot = abs(float(np.dot(n, dnrm / ln))) if ln > 1e-12 else 0.0
            accepted = bool(accept_nearest_fallback(
                np.asarray([float(nearest_distance)]),
                np.asarray([normal_dot]),
                max_distance=FALLBACK_MAX_DISTANCE,
                min_abs_dot=FALLBACK_NORMAL_FLOOR,
            )[0])
            if accepted:
                chosen = (float(nearest_distance), loc, int(face_index), 2)

    if chosen is None:
        continue

    _, loc, face_index, method = chosen
    if face_index < 0 or face_index >= len(donor_tri_vertices):
        invalid_face_index += 1
        continue
    hit = np.asarray(tuple(loc), dtype=np.float64)
    try:
        dbary = barycentric_coordinates_3d(hit, donor_tri_positions[face_index])
    except ValueError:
        continue
    bary_sum_errors.append(abs(float(dbary.sum()) - 1.0))
    bary_min_values.append(float(dbary.min()))
    # BVH intersection can differ from the source triangle plane by numerical epsilon only.
    if dbary.min() < -1e-3 or dbary.max() > 1.001:
        continue
    duv = dbary @ donor_tri_uv[face_index]
    if np.any((duv < -1e-4) | (duv > 1.0001)):
        donor_uv_outside_unit += 1
    duv = np.clip(duv, 0.0, 1.0)
    donor_uv_map[y, x] = duv
    valid[y, x] = True
    method_map[y, x] = method
    if method == 1:
        ray_accepted += 1
    else:
        fallback_accepted += 1

valid_count = int(valid.sum())
valid_fraction = float(valid_count / expected_count)
alpha, core = build_feather_alpha(valid, expected, width=FEATHER_WIDTH)
if np.any(alpha[~valid] != 0.0):
    raise RuntimeError('donor alpha leaked into invalid correspondence')

# ---------------- sample real DRL diffuse (4K diagnostic proxy) ----------------
diffuse_img = np.asarray(Image.open(DRL_DIFFUSE).convert('RGB'), dtype=np.uint8)
if min(diffuse_img.shape[:2]) < 2048:
    raise RuntimeError(f'DRL diffuse proxy too small: {diffuse_img.shape}')
valid_yx = np.argwhere(valid)
uv_samples = donor_uv_map[valid]
rgb_samples = sample_image_bilinear(diffuse_img, uv_samples)
if np.std(rgb_samples) < 6.0:
    raise RuntimeError('sampled DRL diffuse is unexpectedly flat')

# Neutral base is derived only from median legal donor color for seam visibility; no raw map is exported.
median_rgb = np.median(rgb_samples, axis=0)
base_rgb = np.clip(median_rgb * np.asarray([0.92, 0.90, 0.88]), 0, 255)
transfer_rgb = np.zeros((RES, RES, 3), dtype=np.float64)
transfer_rgb[:] = base_rgb
transfer_rgb[valid] = rgb_samples
blend = alpha[:, :, None]
final_rgb = transfer_rgb * blend + base_rgb[None, None, :] * (1.0 - blend)
final_rgb = np.clip(final_rgb, 0, 255).astype(np.uint8)
derived_path = TMP / 'gnm_drl_diffuse_transfer_1024.png'
Image.fromarray(final_rgb, mode='RGB').save(derived_path)

# ---------------- render actual GNM geometry with GNM UV ----------------
# Delete DRL source meshes from render scene entirely after correspondence generation.
for obj in list(source_meshes):
    bpy.data.objects.remove(obj, do_unlink=True)

skin_mesh = bpy.data.meshes.new('GNM_Diffuse_Skin_Mesh')
skin_mesh.from_pydata(G.tolist(), [], skin_faces.tolist())
skin_mesh.update()
skin_obj = bpy.data.objects.new('GNM_Diffuse_Skin', skin_mesh)
bpy.context.collection.objects.link(skin_obj)
skin_uv = skin_mesh.uv_layers.new(name='UVMap')
for poly, uvtri in zip(skin_mesh.polygons, skin_uvs):
    for loop_index, uvco in zip(poly.loop_indices, uvtri):
        skin_uv.data[loop_index].uv = tuple(uvco)
    poly.use_smooth = True

skin_mat = bpy.data.materials.new('GNM_Real_DRL_Diffuse_Only')
skin_mat.use_nodes = True
nt = skin_mat.node_tree
bsdf = nt.nodes.get('Principled BSDF')
tex = nt.nodes.new('ShaderNodeTexImage')
tex.image = bpy.data.images.load(str(derived_path))
tex.interpolation = 'Linear'
nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = 0.52
if bsdf.inputs.get('Subsurface Weight'):
    bsdf.inputs['Subsurface Weight'].default_value = 0.035
skin_obj.data.materials.append(skin_mat)

# Add GNM real eye anatomy as neutral materials so facial transfer can be reviewed in context.
sclera_mat = simple_material('GNM_Sclera', (0.65, 0.62, 0.58, 1), 0.28)
iris_mat = simple_material('GNM_Iris', (0.09, 0.13, 0.12, 1), 0.32)
pupil_mat = simple_material('GNM_Pupil', (0.002, 0.002, 0.002, 1), 0.18)
cornea_mat = simple_material('GNM_Cornea_Diagnostic', (0.12, 0.15, 0.17, 1), 0.08)
for group_name, material in [
    ('scleras', sclera_mat),
    ('irises', iris_mat),
    ('pupils', pupil_mat),
    ('eye_exteriors', cornea_mat),
]:
    if group_name in idx:
        make_semantic_object('GNM_' + group_name, G, gt, vg[idx[group_name]] > 0.5, material)

# Studio render.
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 900
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.world.color = (0.008, 0.010, 0.014)
scene.view_settings.exposure = -0.35

head_min = Gskin.min(0)
head_max = Gskin.max(0)
center = (head_min + head_max) / 2
extent = head_max - head_min
scale = float(max(extent))

def add_area(name, direction, energy, size, color):
    light_data = bpy.data.lights.new(name, type='AREA')
    light_data.energy = energy
    light_data.shape = 'DISK'
    light_data.size = size
    light_data.color = color
    obj = bpy.data.objects.new(name, light_data)
    bpy.context.collection.objects.link(obj)
    obj.location = Vector(center) + Vector(direction).normalized() * scale * 2.0
    obj.rotation_euler = (Vector(center) - obj.location).to_track_quat('-Z', 'Y').to_euler()

add_area('Key', (1.2, -1.4, 0.8), 58, scale * 0.65, (1.0, 0.86, 0.78))
add_area('Fill', (-1.1, -0.8, 0.15), 21, scale * 0.85, (0.72, 0.80, 1.0))
add_area('Rim', (0.2, 1.2, 0.7), 30, scale * 0.55, (0.78, 0.88, 1.0))
cam_data = bpy.data.cameras.new('DiffuseGateCamera')
cam = bpy.data.objects.new('DiffuseGateCamera', cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam
cam.data.type = 'ORTHO'

def render_view(name, axis, ortho_factor):
    axis = Vector(axis).normalized()
    cam.location = Vector(center) + axis * scale * 2.4
    cam.rotation_euler = (Vector(center) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.ortho_scale = scale * ortho_factor
    scene.render.filepath = str((OUT / name).resolve())
    bpy.ops.render.render(write_still=True)

views = {
    'front.png': ((0, -1, 0), 1.08),
    'three_quarter_right.png': ((0.65, -1, 0.08), 1.10),
    'three_quarter_left.png': ((-0.65, -1, 0.08), 1.10),
    'side_right.png': ((1, 0, 0.05), 1.08),
    'face_close.png': ((0, -1, 0), 0.78),
    'face_3q_close.png': ((0.55, -1, 0.05), 0.80),
}
for name, (axis, ortho) in views.items():
    render_view(name, axis, ortho)

# Never publish raw or derived identity texture; remove it before artifact collection.
derived_sha256 = None
import hashlib
with derived_path.open('rb') as f:
    derived_sha256 = hashlib.sha256(f.read()).hexdigest()
derived_path.unlink()

# Render validity metrics.
render_stats = {}
for name in views:
    im = Image.open(OUT / name).convert('RGB')
    stat = ImageStat.Stat(im)
    bg = im.getpixel((2, 2))
    changed = sum(1 for px in im.getdata() if sum(abs(px[i] - bg[i]) for i in range(3)) > 24)
    render_stats[name] = {
        'mean_rgb': stat.mean,
        'std_rgb': stat.stddev,
        'foreground_changed_pixels': changed,
    }
    if changed < 10000 or max(stat.stddev) < 10:
        raise RuntimeError(f'blank or flat render: {name}')

# Make a render-only contact sheet.
thumb = 360
sheet = Image.new('RGB', (thumb * 3, (thumb + 34) * 2), 'white')
draw = ImageDraw.Draw(sheet)
for i, name in enumerate(views):
    im = Image.open(OUT / name).convert('RGB')
    im.thumbnail((thumb, thumb), Image.Resampling.LANCZOS)
    x = (i % 3) * thumb
    y = (i // 3) * (thumb + 34)
    sheet.paste(im, (x, y + 34))
    draw.text((x + 8, y + 9), name.replace('.png', ''), fill='black')
sheet.save(OUT / '00_drl_gnm_diffuse_transfer_contact_sheet.jpg', quality=95)

metrics = {
    'gate': 'DRL_GNM_REAL_DIFFUSE_ONLY_TRANSFER',
    'source': {
        'donor': 'Digital Reality Lab Marcus PBR sample',
        'source_diffuse_entry': 'Textures/Marcus_38_diffuse.png',
        'diagnostic_proxy_file': DRL_DIFFUSE.name,
        'diagnostic_proxy_resolution': [int(diffuse_img.shape[1]), int(diffuse_img.shape[0])],
        'raw_or_derived_identity_texture_uploaded': False,
    },
    'target': {
        'model': 'Google GNM v3',
        'semantic_scope': 'skin ∩ hockey_mask',
        'transfer_resolution': RES,
        'expected_hockey_pixels': expected_count,
        'outward_normal_fraction': outward_fraction,
    },
    'registration': {
        'rigid_iterations': rigid_iterations,
        'nonrigid_iterations': 7,
        'max_cumulative_deformation_mm': 24.0,
    },
    'correspondence': {
        'valid_pixels': valid_count,
        'valid_fraction': valid_fraction,
        'reference_safe_core_fraction': REFERENCE_HYBRID,
        'absolute_delta_from_reference': abs(valid_fraction - REFERENCE_HYBRID),
        'ray_accepted_pixels': ray_accepted,
        'safe_nearest_fallback_pixels': fallback_accepted,
        'invalid_face_index_count': invalid_face_index,
        'donor_uv_outside_unit_count_before_clamp': donor_uv_outside_unit,
        'barycentric_sum_error_max': float(max(bary_sum_errors)) if bary_sum_errors else None,
        'barycentric_min_p01': float(np.percentile(bary_min_values, 1)) if bary_min_values else None,
    },
    'blend': {
        'feather_width_pixels_at_1024': FEATHER_WIDTH,
        'full_alpha_core_pixels': int(core.sum()),
        'full_alpha_core_fraction': float(core.sum() / expected_count),
        'invalid_correspondence_nonzero_alpha': int(np.count_nonzero(alpha[~valid] > 0)),
        'base_color_rgb_median_derived': [float(x) for x in base_rgb],
    },
    'sampled_diffuse': {
        'sample_count': int(len(rgb_samples)),
        'rgb_mean': [float(x) for x in np.mean(rgb_samples, axis=0)],
        'rgb_std': [float(x) for x in np.std(rgb_samples, axis=0)],
        'derived_runtime_texture_sha256_not_uploaded': derived_sha256,
    },
    'renders': render_stats,
    'decision_contract': {
        'minimum_correspondence_fraction': 0.90,
        'minimum_full_alpha_core_fraction': 0.50,
        'maximum_reference_drift': 0.005,
        'must_not_sample_invalid_correspondence': True,
        'this_is_diffuse_only_not_final_skin': True,
    },
    'not_claimed': [
        'final cinematic skin',
        'normal/specular/glossiness/displacement transfer',
        'final SSS calibration',
        'web runtime texture parity',
        'formal cinematic master asset adoption',
    ],
}
pass_gate = (
    valid_fraction >= 0.90
    and float(core.sum() / expected_count) >= 0.50
    and abs(valid_fraction - REFERENCE_HYBRID) <= 0.005
    and int(np.count_nonzero(alpha[~valid] > 0)) == 0
    and invalid_face_index == 0
    and (max(bary_sum_errors) if bary_sum_errors else 1.0) <= 1e-5
    and len(rgb_samples) > 100000
    and float(np.mean(np.std(rgb_samples, axis=0))) > 6.0
)
metrics['decision'] = {
    'pass': bool(pass_gate),
    'status': 'PASS_READY_FOR_GPT_VISUAL_REVIEW' if pass_gate else 'FAIL_BLOCKED',
    'next_if_visual_pass': 'NORMAL_GLOSS_SPECULAR_TRANSFER_USING_SAME_CORRESPONDENCE',
    'next_if_visual_fail': 'REVIEW_DONOR_UV_OR_LANDMARK_CORRESPONDENCE',
}
(OUT / 'diffuse_transfer_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
if not pass_gate:
    raise RuntimeError('diffuse-only numeric contract failed')
