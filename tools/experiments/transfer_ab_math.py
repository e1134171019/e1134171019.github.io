import numpy as np


def rasterize_uv_triangle(uv, resolution, eps=1e-10):
    uv = np.asarray(uv, dtype=np.float64)
    if uv.shape != (3, 2):
        raise ValueError("uv must have shape (3, 2)")
    resolution = int(resolution)
    if resolution <= 0:
        raise ValueError("resolution must be positive")
    p = uv * resolution
    xmin = max(0, int(np.ceil(np.min(p[:, 0]) - 0.5)))
    xmax = min(resolution - 1, int(np.floor(np.max(p[:, 0]) - 0.5)))
    ymin = max(0, int(np.ceil(np.min(p[:, 1]) - 0.5)))
    ymax = min(resolution - 1, int(np.floor(np.max(p[:, 1]) - 0.5)))
    if xmin > xmax or ymin > ymax:
        return np.empty((0, 2), dtype=np.int32), np.empty((0, 3), dtype=np.float64)
    x0, y0 = uv[0]; x1, y1 = uv[1]; x2, y2 = uv[2]
    den = (y1-y2)*(x0-x2) + (x2-x1)*(y0-y2)
    if abs(den) <= eps:
        return np.empty((0, 2), dtype=np.int32), np.empty((0, 3), dtype=np.float64)
    xs = np.arange(xmin, xmax + 1, dtype=np.int32)
    ys = np.arange(ymin, ymax + 1, dtype=np.int32)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    u = (gx.ravel().astype(np.float64) + 0.5) / resolution
    v = (gy.ravel().astype(np.float64) + 0.5) / resolution
    a = ((y1-y2)*(u-x2) + (x2-x1)*(v-y2)) / den
    b = ((y2-y0)*(u-x2) + (x0-x2)*(v-y2)) / den
    c = 1.0 - a - b
    inside = (a >= -eps) & (b >= -eps) & (c >= -eps)
    xy = np.stack([gx.ravel()[inside], gy.ravel()[inside]], axis=1).astype(np.int32)
    bary = np.stack([a[inside], b[inside], c[inside]], axis=1)
    return xy, bary


def choose_bidirectional_hits(plus_distance, minus_distance):
    plus = np.asarray(plus_distance, dtype=np.float64)
    minus = np.asarray(minus_distance, dtype=np.float64)
    if plus.shape != minus.shape:
        raise ValueError("plus_distance and minus_distance must have identical shapes")
    hp = np.isfinite(plus); hm = np.isfinite(minus)
    choice = np.zeros(plus.shape, dtype=np.int8)
    distance = np.full(plus.shape, np.nan, dtype=np.float64)
    only_p = hp & ~hm; only_m = hm & ~hp; both = hp & hm
    choose_p = both & (plus <= minus); choose_m = both & (minus < plus)
    choice[only_p | choose_p] = 1; choice[only_m | choose_m] = -1
    distance[only_p | choose_p] = plus[only_p | choose_p]
    distance[only_m | choose_m] = minus[only_m | choose_m]
    return choice, distance


def accept_nearest_fallback(distance, normal_abs_dot, max_distance=0.015, min_abs_dot=0.5):
    distance = np.asarray(distance, dtype=np.float64)
    normal_abs_dot = np.asarray(normal_abs_dot, dtype=np.float64)
    if distance.shape != normal_abs_dot.shape:
        raise ValueError("distance and normal_abs_dot must have identical shapes")
    return np.isfinite(distance) & np.isfinite(normal_abs_dot) & (distance <= max_distance) & (normal_abs_dot >= min_abs_dot)


def accept_anatomical_anchor(target_points, donor_rigid_points, max_vertical=0.025, max_lateral=0.035):
    target = np.asarray(target_points, dtype=np.float64)
    donor = np.asarray(donor_rigid_points, dtype=np.float64)
    if target.shape != donor.shape or target.ndim != 2 or target.shape[1] != 3:
        raise ValueError("target_points and donor_rigid_points must share shape (N,3)")
    delta = donor - target
    return np.isfinite(delta).all(axis=1) & (np.abs(delta[:, 2]) <= max_vertical) & (np.abs(delta[:, 0]) <= max_lateral)


def _erode_8(mask):
    mask = np.asarray(mask, dtype=bool)
    h, w = mask.shape
    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    out = np.ones((h, w), dtype=bool)
    for dy in range(3):
        for dx in range(3):
            out &= padded[dy:dy+h, dx:dx+w]
    return out


def build_feather_alpha(valid, expected, width=16):
    valid = np.asarray(valid, dtype=bool); expected = np.asarray(expected, dtype=bool)
    if valid.shape != expected.shape or valid.ndim != 2:
        raise ValueError("valid and expected must be same-shape 2D masks")
    width = int(width)
    if width <= 0:
        raise ValueError("width must be positive")
    support = valid & expected
    alpha = np.zeros(support.shape, dtype=np.float32)
    depth = np.zeros(support.shape, dtype=np.int32)
    layer = support.copy()
    for step in range(1, width + 1):
        if not np.any(layer): break
        depth[layer] = step
        layer = _erode_8(layer)
    alpha[support] = np.minimum(depth[support].astype(np.float32) / float(width), 1.0)
    alpha[~support] = 0.0
    core = support & (depth >= width)
    return alpha, core


def barycentric_coordinates_3d(point, triangle, eps=1e-14):
    p = np.asarray(point, dtype=np.float64); tri = np.asarray(triangle, dtype=np.float64)
    if p.shape != (3,) or tri.shape != (3,3):
        raise ValueError("point must have shape (3,) and triangle shape (3,3)")
    a,b,c = tri; v0=b-a; v1=c-a; v2=p-a
    d00=float(np.dot(v0,v0)); d01=float(np.dot(v0,v1)); d11=float(np.dot(v1,v1)); d20=float(np.dot(v2,v0)); d21=float(np.dot(v2,v1))
    den=d00*d11-d01*d01
    if abs(den) <= eps: raise ValueError("degenerate 3D triangle")
    vb=(d11*d20-d01*d21)/den; vc=(d00*d21-d01*d20)/den; va=1.0-vb-vc
    return np.asarray([va,vb,vc], dtype=np.float64)


def sample_image_bilinear(image, uv):
    img = np.asarray(image); coords = np.asarray(uv, dtype=np.float64)
    if img.ndim != 3 or img.shape[2] < 3: raise ValueError("image must have shape (H,W,C>=3)")
    if coords.ndim == 1: coords = coords[None,:]
    if coords.ndim != 2 or coords.shape[1] != 2: raise ValueError("uv must have shape (N,2)")
    h,w = img.shape[:2]
    u=np.clip(coords[:,0],0,1)*(w-1); v=(1-np.clip(coords[:,1],0,1))*(h-1)
    x0=np.floor(u).astype(np.int64); y0=np.floor(v).astype(np.int64); x1=np.minimum(x0+1,w-1); y1=np.minimum(y0+1,h-1)
    fx=(u-x0)[:,None]; fy=(v-y0)[:,None]
    c00=img[y0,x0,:3].astype(np.float64); c10=img[y0,x1,:3].astype(np.float64); c01=img[y1,x0,:3].astype(np.float64); c11=img[y1,x1,:3].astype(np.float64)
    top=c00*(1-fx)+c10*fx; bottom=c01*(1-fx)+c11*fx
    return top*(1-fy)+bottom*fy
