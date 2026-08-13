import numpy as np

from tools.experiments.authored_skin_math import (
    author_low_frequency_skin,
    gloss_to_roughness,
    specular_to_level,
)


def test_authored_skin_suppresses_checker_detail_but_keeps_broad_color_field():
    h = w = 128
    yy, xx = np.indices((h, w))
    base = np.zeros((h, w, 3), dtype=np.float64)
    base[:] = np.array([154.0, 94.0, 74.0])
    base[:, w // 2 :, 0] += 22.0
    checker = np.where((xx + yy) % 2 == 0, -24.0, 24.0)
    source = np.clip(base + checker[..., None], 0, 255).astype(np.uint8)

    authored, stats = author_low_frequency_skin(source)

    parity = (xx + yy) % 2 == 0
    source_contrast = abs(source[parity].mean() - source[~parity].mean()) / 255.0
    authored_contrast = abs(authored[parity].mean() - authored[~parity].mean())
    broad_red_delta = authored[:, w // 2 :, 0].mean() - authored[:, : w // 2, 0].mean()

    assert authored.shape == source.shape
    assert np.isfinite(authored).all()
    assert float(authored.min()) >= 0.0
    assert float(authored.max()) <= 1.0
    assert authored_contrast < source_contrast * 0.20
    assert broad_red_delta > 0.01
    assert 0.0 <= stats['high_frequency_energy_ratio'] < 0.25


def test_gloss_to_roughness_is_inverse_monotonic_and_skin_bounded():
    gloss = np.tile(np.linspace(0, 255, 256, dtype=np.float64), (16, 1))

    roughness, stats = gloss_to_roughness(gloss)

    assert np.isfinite(roughness).all()
    assert float(roughness.min()) >= 0.38 - 1e-9
    assert float(roughness.max()) <= 0.62 + 1e-9
    assert roughness[:, 0].mean() > roughness[:, -1].mean()
    assert stats['output_min'] >= 0.38 - 1e-9
    assert stats['output_max'] <= 0.62 + 1e-9


def test_specular_to_level_is_monotonic_and_dielectric_bounded():
    specular = np.tile(np.linspace(0, 255, 256, dtype=np.float64), (16, 1))

    level, stats = specular_to_level(specular)

    assert np.isfinite(level).all()
    assert float(level.min()) >= 0.35 - 1e-9
    assert float(level.max()) <= 0.55 + 1e-9
    assert level[:, 0].mean() < level[:, -1].mean()
    assert stats['output_min'] >= 0.35 - 1e-9
    assert stats['output_max'] <= 0.55 + 1e-9


def test_constant_material_inputs_stay_finite_and_centered():
    diffuse = np.full((64, 64, 3), [150, 90, 70], dtype=np.uint8)
    scalar = np.full((64, 64), 128.0, dtype=np.float64)

    authored, skin_stats = author_low_frequency_skin(diffuse)
    roughness, rough_stats = gloss_to_roughness(scalar)
    specular, spec_stats = specular_to_level(scalar)

    assert np.isfinite(authored).all()
    assert np.isfinite(roughness).all()
    assert np.isfinite(specular).all()
    assert np.allclose(roughness, 0.50)
    assert np.allclose(specular, 0.45)
    assert skin_stats['input_shape'] == [64, 64, 3]
    assert rough_stats['robust_span'] == 0.0
    assert spec_stats['robust_span'] == 0.0
