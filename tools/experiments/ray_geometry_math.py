import numpy as np


def _percentile_mm(values, q):
    return float(np.percentile(values, q) * 1000.0)


def summarize_signed_offsets(points, normals, nearest_points):
    p = np.asarray(points, dtype=np.float64)
    n = np.asarray(normals, dtype=np.float64)
    q = np.asarray(nearest_points, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3 or n.shape != p.shape or q.shape != p.shape:
        raise ValueError("points, normals, nearest_points must all have shape (N, 3)")
    if len(p) == 0:
        raise ValueError("at least one sample is required")

    nlen = np.linalg.norm(n, axis=1)
    if np.any(nlen <= 1e-12):
        raise ValueError("normals must be non-zero")
    n = n / nlen[:, None]

    delta = q - p
    dist = np.linalg.norm(delta, axis=1)
    signed = np.einsum("ij,ij->i", delta, n)
    tangent = delta - signed[:, None] * n
    tangential = np.linalg.norm(tangent, axis=1)

    eps = 1e-9
    plus = signed > eps
    minus = signed < -eps
    zero = ~(plus | minus)
    plus_fraction = float(np.mean(plus))
    minus_fraction = float(np.mean(minus))
    zero_fraction = float(np.mean(zero))

    if plus_fraction >= 0.75:
        decision = "DOMINANT_PLUS_N"
    elif minus_fraction >= 0.75:
        decision = "DOMINANT_MINUS_N"
    else:
        decision = "MIXED_SIGN"

    mm = dist * 1000.0
    buckets = {
        "0_2": int(np.sum(mm <= 2.0)),
        "2_5": int(np.sum((mm > 2.0) & (mm <= 5.0))),
        "5_10": int(np.sum((mm > 5.0) & (mm <= 10.0))),
        "10_20": int(np.sum((mm > 10.0) & (mm <= 20.0))),
        "gt20": int(np.sum(mm > 20.0)),
    }

    return {
        "count": int(len(p)),
        "plus_fraction": plus_fraction,
        "minus_fraction": minus_fraction,
        "zero_fraction": zero_fraction,
        "decision": decision,
        "distance_buckets_mm": buckets,
        "distance_median_mm": _percentile_mm(dist, 50),
        "distance_p90_mm": _percentile_mm(dist, 90),
        "distance_p95_mm": _percentile_mm(dist, 95),
        "signed_median_mm": _percentile_mm(signed, 50),
        "signed_p10_mm": _percentile_mm(signed, 10),
        "signed_p90_mm": _percentile_mm(signed, 90),
        "tangential_median_mm": _percentile_mm(tangential, 50),
        "tangential_p90_mm": _percentile_mm(tangential, 90),
        "max_tangential_mm": float(np.max(tangential) * 1000.0),
    }
