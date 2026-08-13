import unittest

import numpy as np


class RayGeometryMathContractTest(unittest.TestCase):
    def test_signed_offsets_classify_side_distance_and_tangential_residual(self):
        try:
            from tools.experiments.ray_geometry_math import summarize_signed_offsets
        except ModuleNotFoundError as exc:
            self.fail(f"ray geometry helper missing: {exc}")

        points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ])
        normals = np.array([
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, 1.0],
        ])
        nearest = np.array([
            [0.0, 0.0, 0.002],   # +N, 2 mm
            [0.003, 0.0, 0.004], # +N, 5 mm total, 3 mm tangential
            [0.0, 0.0, -0.006],  # -N, 6 mm
            [0.0, 0.0, -0.012],  # -N, 12 mm
        ])

        out = summarize_signed_offsets(points, normals, nearest)

        self.assertEqual(out["count"], 4)
        self.assertAlmostEqual(out["plus_fraction"], 0.5)
        self.assertAlmostEqual(out["minus_fraction"], 0.5)
        self.assertAlmostEqual(out["zero_fraction"], 0.0)
        self.assertEqual(out["distance_buckets_mm"]["0_2"], 1)
        self.assertEqual(out["distance_buckets_mm"]["2_5"], 1)
        self.assertEqual(out["distance_buckets_mm"]["5_10"], 1)
        self.assertEqual(out["distance_buckets_mm"]["10_20"], 1)
        self.assertEqual(out["distance_buckets_mm"]["gt20"], 0)
        self.assertAlmostEqual(out["max_tangential_mm"], 3.0, places=6)
        self.assertEqual(out["decision"], "MIXED_SIGN")


if __name__ == "__main__":
    unittest.main()
