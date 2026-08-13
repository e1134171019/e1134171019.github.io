from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

ROUGHNESS_MIN = 0.38
ROUGHNESS_MAX = 0.62
SPECULAR_MIN = 0.35
SPECULAR_MAX = 0.55
AUTHORED_SKIN_BASE = np.asarray([0.58, 0.34, 0.27], dtype=np.float64)


def _as_unit_rgb(rgb: np.ndarray) -> np.ndarray:
    arr = np.asarray(rgb, dtype=np.float64)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f'expected HxWx3 RGB array, got {arr.shape}')
    if not np.isfinite(arr).all():
        raise ValueError('RGB input contains non-finite values')
    if float(arr.max(initial=0.0)) > 1.0:
        arr = arr / 255.0
    return np.clip(arr, 0.0, 1.0)


def _lowpass_rgb(unit_rgb: np.ndarray) -> np.ndarray:
    h, w, _ = unit_rgb.shape
    u8 = np.clip(np.rint(unit_rgb * 255.0), 0, 255).astype(np.uint8)
    image = Image.fromarray(u8, mode='RGB')
    small_w = max(8, w // 16)
    small_h = max(8, h // 16)
    small = image.resize((small_w, small_h), Image.Resampling.LANCZOS)
    small = small.filter(ImageFilter.GaussianBlur(radius=1.5))
    low = small.resize((w, h), Image.Resampling.BICUBIC)
    return np.asarray(low, dtype=np.float64) / 255.0


def _robust_unit(channel: np.ndarray) -> tuple[np.ndarray, dict]:
    arr = np.asarray(channel, dtype=np.float64)
    if arr.ndim not in (1, 2):
        raise ValueError(f'expected scalar material channel, got {arr.shape}')
    if not np.isfinite(arr).all():
        raise ValueError('material channel contains non-finite values')
    if float(arr.max(initial=0.0)) > 1.0:
        arr = arr / 255.0
    arr = np.clip(arr, 0.0, 1.0)
    low, high = np.percentile(arr, [5.0, 95.0])
    span = float(high - low)
    if span <= 1e-12:
        normalized = np.full_like(arr, 0.5, dtype=np.float64)
        span = 0.0
    else:
        normalized = np.clip((arr - low) / span, 0.0, 1.0)
    return normalized, {
        'robust_low': float(low),
        'robust_high': float(high),
        'robust_span': span,
    }


def author_low_frequency_skin(rgb: np.ndarray) -> tuple[np.ndarray, dict]:
    source = _as_unit_rgb(rgb)
    low = _lowpass_rgb(source)
    median = np.median(low.reshape(-1, 3), axis=0)
    broad_delta = np.clip(low - median[None, None, :], -0.14, 0.14)
    authored = np.clip(AUTHORED_SKIN_BASE[None, None, :] + 0.60 * broad_delta, 0.0, 1.0)

    source_high = source - low
    authored_low = _lowpass_rgb(authored)
    authored_high = authored - authored_low
    source_energy = float(np.mean(np.abs(source_high)))
    authored_energy = float(np.mean(np.abs(authored_high)))
    ratio = authored_energy / max(source_energy, 1e-12)
    if source_energy <= 1e-12:
        ratio = 0.0

    return authored, {
        'input_shape': [int(x) for x in source.shape],
        'authored_base_rgb': [float(x) for x in AUTHORED_SKIN_BASE],
        'source_high_frequency_energy': source_energy,
        'authored_high_frequency_energy': authored_energy,
        'high_frequency_energy_ratio': float(ratio),
        'broad_delta_abs_p95': float(np.percentile(np.abs(broad_delta), 95.0)),
    }


def gloss_to_roughness(gloss: np.ndarray) -> tuple[np.ndarray, dict]:
    normalized, stats = _robust_unit(gloss)
    roughness = ROUGHNESS_MAX - normalized * (ROUGHNESS_MAX - ROUGHNESS_MIN)
    stats.update({
        'output_min': float(roughness.min()),
        'output_max': float(roughness.max()),
        'mapping': 'inverse_gloss_to_skin_roughness',
    })
    return roughness, stats


def specular_to_level(specular: np.ndarray) -> tuple[np.ndarray, dict]:
    normalized, stats = _robust_unit(specular)
    level = SPECULAR_MIN + normalized * (SPECULAR_MAX - SPECULAR_MIN)
    stats.update({
        'output_min': float(level.min()),
        'output_max': float(level.max()),
        'mapping': 'robust_specular_to_dielectric_level',
    })
    return level, stats
