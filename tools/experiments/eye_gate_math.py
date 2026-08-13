import numpy as np


def priority_eye_partition(eye_faces, iris_faces, pupil_faces, cornea_faces, skin_faces):
    eye = np.asarray(eye_faces, dtype=bool)
    iris = np.asarray(iris_faces, dtype=bool)
    pupil = np.asarray(pupil_faces, dtype=bool)
    cornea = np.asarray(cornea_faces, dtype=bool)
    skin = np.asarray(skin_faces, dtype=bool)
    if not (eye.shape == iris.shape == pupil.shape == cornea.shape == skin.shape):
        raise ValueError('all face masks must have identical shapes')

    pupil_out = eye & pupil
    iris_out = eye & iris & ~pupil_out
    sclera_out = eye & ~iris & ~pupil_out
    cornea_out = cornea.copy()
    skin_out = skin & ~eye & ~cornea_out

    return {
        'skin': skin_out,
        'sclera': sclera_out,
        'iris': iris_out,
        'pupil': pupil_out,
        'cornea': cornea_out,
    }


def _as_points(points, name):
    p = np.asarray(points, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 4 or not np.isfinite(p).all():
        raise ValueError(f'{name} must be finite Nx3 points with N>=4')
    return p


def _split(points, midline):
    left = points[points[:, 0] <= midline]
    right = points[points[:, 0] > midline]
    if len(left) < 2 or len(right) < 2:
        raise ValueError('eye component does not contain both bilateral halves')
    return left, right


def _center(points):
    return np.mean(points, axis=0)


def _radius(points):
    extent = np.ptp(points, axis=0)
    return max(float(np.max(extent) * 0.5), 1e-12)


def measure_eye_alignment(sclera_points, iris_points, pupil_points):
    sclera = _as_points(sclera_points, 'sclera_points')
    iris = _as_points(iris_points, 'iris_points')
    pupil = _as_points(pupil_points, 'pupil_points')

    midline = float((np.min(sclera[:, 0]) + np.max(sclera[:, 0])) * 0.5)
    sl, sr = _split(sclera, midline)
    il, ir = _split(iris, midline)
    pl, pr = _split(pupil, midline)

    sclera_radius_l = _radius(sl)
    sclera_radius_r = _radius(sr)
    reference_radius = max((sclera_radius_l + sclera_radius_r) * 0.5, 1e-12)

    iris_center_l, iris_center_r = _center(il), _center(ir)
    pupil_center_l, pupil_center_r = _center(pl), _center(pr)
    offset_l = pupil_center_l - iris_center_l
    offset_r = pupil_center_r - iris_center_r

    pupil_offset_l = float(np.linalg.norm(offset_l) / sclera_radius_l)
    pupil_offset_r = float(np.linalg.norm(offset_r) / sclera_radius_r)
    gaze_mismatch = float(np.linalg.norm(offset_l - offset_r) / reference_radius)
    size_mismatch = float(abs(sclera_radius_l - sclera_radius_r) / reference_radius)

    return {
        'midline_x': midline,
        'left': {
            'sclera_center': _center(sl).tolist(),
            'iris_center': iris_center_l.tolist(),
            'pupil_center': pupil_center_l.tolist(),
            'sclera_radius': sclera_radius_l,
            'pupil_to_iris_offset_ratio': pupil_offset_l,
        },
        'right': {
            'sclera_center': _center(sr).tolist(),
            'iris_center': iris_center_r.tolist(),
            'pupil_center': pupil_center_r.tolist(),
            'sclera_radius': sclera_radius_r,
            'pupil_to_iris_offset_ratio': pupil_offset_r,
        },
        'max_pupil_to_iris_offset_ratio': max(pupil_offset_l, pupil_offset_r),
        'gaze_mismatch_ratio': gaze_mismatch,
        'sclera_bilateral_size_mismatch_ratio': size_mismatch,
    }
