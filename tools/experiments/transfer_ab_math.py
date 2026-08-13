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

    x0, y0 = uv[0]
    x1, y1 = uv[1]
    x2, y2 = uv[2]
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(den) <= eps:
        return np.empty((0, 2), dtype=np.int32), np.empty((0, 3), dtype=np.float64)

    xs = np.arange(xmin, xmax + 1, dtype=np.int32)
    ys = np.arange(ymin, ymax + 1, dtype=np.int32)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    u = (gx.ravel().astype(np.float64) + 0.5) / resolution
    v = (gy.ravel().astype(np.float64) + 0.5) / resolution

    a = ((y1 - y2) * (u - x2) + (x2 - x1) * (v - y2)) / den
    b = ((y2 - y0) * (u - x2) + (x0 - x2) * (v - y2)) / den
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

    hp = np.isfinite(plus)
    hm = np.isfinite(minus)
    choice = np.zeros(plus.shape, dtype=np.int8)
    distance = np.full(plus.shape, np.nan, dtype=np.float64)

    only_p = hp & ~hm
    only_m = hm & ~hp
    both = hp & hm
    choose_p = both & (plus <= minus)
    choose_m = both & (minus < plus)

    choice[only_p | choose_p] = 1
    choice[only_m | choose_m] = -1
    distance[only_p | choose_p] = plus[only_p | choose_p]
    distance[only_m | choose_m] = minus[only_m | choose_m]
    return choice, distance


def accept_nearest_fallback(distance, normal_abs_dot, max_distance=0.015, min_abs_dot=0.5):
    distance = np.asarray(distance, dtype=np.float64)
    normal_abs_dot = np.asarray(normal_abs_dot, dtype=np.float64)
    if distance.shape != normal_abs_dot.shape:
        raise ValueError("distance and normal_abs_dot must have identical shapes")
    return (
        np.isfinite(distance)
        & np.isfinite(normal_abs_dot)
        & (distance <= max_distance)
        & (normal_abs_dot >= min_abs_dot)
    )
