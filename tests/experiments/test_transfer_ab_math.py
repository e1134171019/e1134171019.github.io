import unittest

import numpy as np


class TransferABMathContractTest(unittest.TestCase):
    def test_triangle_rasterization_returns_pixel_centers_and_barycentrics(self):
        try:
            from tools.experiments.transfer_ab_math import rasterize_uv_triangle
        except ModuleNotFoundError as exc:
            self.fail(f"transfer A/B helper missing: {exc}")

        uv = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
        xy, bary = rasterize_uv_triangle(uv, 4)
        self.assertGreater(len(xy), 0)
        self.assertEqual(xy.shape[1], 2)
        self.assertEqual(bary.shape, (len(xy), 3))
        np.testing.assert_allclose(bary.sum(axis=1), 1.0, atol=1e-10)
        self.assertTrue(np.all(bary >= -1e-10))

    def test_bidirectional_choice_prefers_only_hit_then_nearest_hit(self):
        from tools.experiments.transfer_ab_math import choose_bidirectional_hits

        plus = np.array([0.003, np.nan, 0.010, np.nan])
        minus = np.array([np.nan, 0.004, 0.006, np.nan])
        choice, dist = choose_bidirectional_hits(plus, minus)

        self.assertEqual(choice.tolist(), [1, -1, -1, 0])
        np.testing.assert_allclose(dist[:3], [0.003, 0.004, 0.006])
        self.assertTrue(np.isnan(dist[3]))


if __name__ == "__main__":
    unittest.main()
