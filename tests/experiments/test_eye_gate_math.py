import numpy as np

from tools.experiments.eye_gate_math import measure_eye_alignment, priority_eye_partition


def test_priority_partition_pupil_overrides_iris_and_iris_overrides_sclera():
    eye = np.array([True, True, True, True, False])
    iris = np.array([False, True, True, False, False])
    pupil = np.array([False, False, True, False, False])
    cornea = np.array([False, False, False, False, True])
    skin = np.array([True, True, True, True, True])

    p = priority_eye_partition(eye, iris, pupil, cornea, skin)

    assert p['pupil'].tolist() == [False, False, True, False, False]
    assert p['iris'].tolist() == [False, True, False, False, False]
    assert p['sclera'].tolist() == [True, False, False, True, False]
    assert p['cornea'].tolist() == [False, False, False, False, True]
    assert not np.any(p['skin'] & (p['sclera'] | p['iris'] | p['pupil'] | p['cornea']))


def _cloud(center, rx=0.5, ry=0.25, rz=0.15):
    c = np.asarray(center, dtype=float)
    return c + np.array([
        [-rx, 0.0, 0.0], [rx, 0.0, 0.0],
        [0.0, -ry, 0.0], [0.0, ry, 0.0],
        [0.0, 0.0, -rz], [0.0, 0.0, rz],
    ])


def test_measure_eye_alignment_accepts_centered_symmetric_pair():
    sclera = np.vstack([_cloud((-1.0, 0, 0)), _cloud((1.0, 0, 0))])
    iris = np.vstack([_cloud((-1.0, 0, 0), 0.22, 0.12, 0.05), _cloud((1.0, 0, 0), 0.22, 0.12, 0.05)])
    pupil = np.vstack([_cloud((-1.0, 0, 0), 0.08, 0.05, 0.02), _cloud((1.0, 0, 0), 0.08, 0.05, 0.02)])

    m = measure_eye_alignment(sclera, iris, pupil)

    assert m['max_pupil_to_iris_offset_ratio'] < 1e-9
    assert m['gaze_mismatch_ratio'] < 1e-9
    assert m['sclera_bilateral_size_mismatch_ratio'] < 1e-9


def test_measure_eye_alignment_detects_cross_eye_like_mismatch():
    sclera = np.vstack([_cloud((-1.0, 0, 0)), _cloud((1.0, 0, 0))])
    iris = np.vstack([_cloud((-1.0, 0, 0), 0.22, 0.12, 0.05), _cloud((1.0, 0, 0), 0.22, 0.12, 0.05)])
    pupil = np.vstack([
        _cloud((-0.86, 0, 0), 0.08, 0.05, 0.02),
        _cloud((0.86, 0, 0), 0.08, 0.05, 0.02),
    ])

    m = measure_eye_alignment(sclera, iris, pupil)

    assert m['max_pupil_to_iris_offset_ratio'] > 0.20
    assert m['gaze_mismatch_ratio'] > 0.40
