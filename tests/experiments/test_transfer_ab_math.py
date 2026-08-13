import unittest

import numpy as np


class TransferABMathContractTest(unittest.TestCase):
    def test_triangle_rasterization_returns_pixel_centers_and_barycentrics(self):
        from tools.experiments.transfer_ab_math import rasterize_uv_triangle
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

    def test_nearest_fallback_uses_fixed_15mm_and_60degree_contract(self):
        from tools.experiments.transfer_ab_math import accept_nearest_fallback
        distance = np.array([0.014, 0.016, 0.010, 0.015])
        normal_abs_dot = np.array([0.50, 0.99, 0.49, 0.50])
        accepted = accept_nearest_fallback(distance, normal_abs_dot)
        self.assertEqual(accepted.tolist(), [True, False, False, True])

    def test_feather_alpha_never_uses_invalid_correspondence(self):
        from tools.experiments.transfer_ab_math import build_feather_alpha
        expected = np.ones((9, 9), dtype=bool)
        valid = np.ones((9, 9), dtype=bool)
        valid[4, 4] = False
        alpha, core = build_feather_alpha(valid, expected, width=2)
        self.assertEqual(float(alpha[4, 4]), 0.0)
        self.assertTrue(np.all(alpha[~valid] == 0.0))
        self.assertTrue(np.all(alpha[~expected] == 0.0))
        self.assertTrue(np.any(core))
        self.assertTrue(np.all(alpha[core] == 1.0))
        self.assertGreater(float(alpha[4, 3]), 0.0)
        self.assertLess(float(alpha[4, 3]), 1.0)

    def test_3d_barycentric_recovers_known_triangle_coordinates(self):
        from tools.experiments.transfer_ab_math import barycentric_coordinates_3d
        tri = np.array([[0.,0.,0.],[2.,0.,0.],[0.,2.,0.]])
        p = np.array([0.5,0.75,0.0])
        b = barycentric_coordinates_3d(p, tri)
        np.testing.assert_allclose(b, [0.375,0.25,0.375], atol=1e-10)
        np.testing.assert_allclose(b @ tri, p, atol=1e-10)

    def test_bilinear_uv_sampling_uses_bottom_left_uv_convention(self):
        from tools.experiments.transfer_ab_math import sample_image_bilinear
        img = np.array([[[255,0,0],[0,255,0]],[[0,0,255],[255,255,255]]], dtype=np.uint8)
        rgb = sample_image_bilinear(img, np.array([[0.0,0.0],[1.0,1.0]]))
        np.testing.assert_allclose(rgb[0], [0,0,255], atol=1e-6)
        np.testing.assert_allclose(rgb[1], [0,255,0], atol=1e-6)

    def test_anatomical_anchor_rejects_source_that_was_pulled_from_neck(self):
        from tools.experiments.transfer_ab_math import accept_anatomical_anchor
        target = np.array([[0.0, 0.0, 0.10], [0.0, 0.0, 0.10], [0.0, 0.0, 0.10]])
        donor_rigid = np.array([[0.01, 0.02, 0.08], [0.04, 0.01, 0.09], [0.01, 0.01, 0.06]])
        accepted = accept_anatomical_anchor(target, donor_rigid)
        self.assertEqual(accepted.tolist(), [True, False, False])

    def test_semantic_region_pair_requires_same_region_and_both_near_reference(self):
        try:
            from tools.experiments.transfer_ab_math import accept_semantic_region_pair
        except ImportError as exc:
            self.fail(f"semantic region helper missing: {exc}")
        target_label = np.array([3, 3, 5, 7])
        donor_label = np.array([3, 5, 5, 7])
        target_dist = np.array([0.004, 0.003, 0.013, 0.006])
        donor_dist = np.array([0.010, 0.004, 0.005, 0.014])
        accepted = accept_semantic_region_pair(target_label, donor_label, target_dist, donor_dist)
        self.assertEqual(accepted.tolist(), [True, False, False, False])


if __name__ == "__main__":
    unittest.main()
