import json
import os
import runpy
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from tools.experiments.transfer_ab_math import build_feather_alpha

# Reuse the already-verified CPU correspondence implementation verbatim. It executes
# registration + bidirectional rays + the fixed 15 mm / 60 degree safe fallback and
# writes only safe masks/metrics; it never loads an identity texture.
runpy.run_path('tools/experiments/drl_gnm_cpu_fallback_gate.py', run_name='__safe_core_source_gate__')

SRC = Path('artifacts/drl-gnm-cpu-fallback-gate')
OUT = Path('artifacts/drl-gnm-safe-core-feather-gate')
OUT.mkdir(parents=True, exist_ok=True)
FEATHER_WIDTH = 16
MIN_SUPPORT_FRACTION = 0.90
MIN_CORE_FRACTION = 0.50

src_metrics = json.loads((SRC / 'cpu_fallback_metrics.json').read_text(encoding='utf-8'))
expected = np.asarray(Image.open(SRC / 'expected_hockey_uv.png').convert('L')) > 127
valid = np.asarray(Image.open(SRC / 'hybrid_coverage.png').convert('L')) > 127

if expected.shape != valid.shape:
    raise RuntimeError('expected and hybrid masks have different dimensions')
if expected.shape != (1024, 1024):
    raise RuntimeError(f'unexpected diagnostic mask shape: {expected.shape}')
if np.any(valid & ~expected):
    raise RuntimeError('valid correspondence leaked outside hockey UV footprint')

alpha, core = build_feather_alpha(valid, expected, width=FEATHER_WIDTH)
feather = valid & ~core
base_only = expected & ~valid

expected_count = int(expected.sum())
valid_count = int(valid.sum())
core_count = int(core.sum())
feather_count = int(feather.sum())
base_only_count = int(base_only.sum())

support_fraction = float(valid_count / max(expected_count, 1))
core_fraction = float(core_count / max(expected_count, 1))
feather_fraction = float(feather_count / max(expected_count, 1))
base_only_fraction = float(base_only_count / max(expected_count, 1))

invalid_nonzero_alpha = int(np.count_nonzero(alpha[~valid] > 0.0))
outside_nonzero_alpha = int(np.count_nonzero(alpha[~expected] > 0.0))
core_not_full_alpha = int(np.count_nonzero(alpha[core] < 1.0 - 1e-6))
valid_zero_alpha = int(np.count_nonzero(alpha[valid] <= 0.0))

# Save only masks. No DRL identity pixels are present anywhere in this artifact.
Image.fromarray((expected.astype(np.uint8) * 255), mode='L').save(OUT / 'expected_hockey_uv.png')
Image.fromarray((valid.astype(np.uint8) * 255), mode='L').save(OUT / 'donor_valid_support.png')
Image.fromarray((core.astype(np.uint8) * 255), mode='L').save(OUT / 'safe_full_alpha_core.png')
Image.fromarray(np.clip(alpha * 255.0, 0, 255).astype(np.uint8), mode='L').save(OUT / 'feather_alpha.png')
Image.fromarray((base_only.astype(np.uint8) * 255), mode='L').save(OUT / 'base_only_region.png')

# Green = full donor core; cyan = legal donor feather; dark red = base GNM only.
diag = np.zeros((*expected.shape, 3), dtype=np.uint8)
diag[core] = (40, 190, 70)
diag[feather] = (40, 190, 220)
diag[base_only] = (165, 55, 45)
Image.fromarray(diag, mode='RGB').save(OUT / 'safe_core_feather_comparison.png')

# Mapping safety is the gate. We deliberately do not require donor to cover 100%:
# invalid source correspondence is filled by the base GNM skin, not invented donor data.
safety_pass = (
    support_fraction >= MIN_SUPPORT_FRACTION
    and core_fraction >= MIN_CORE_FRACTION
    and invalid_nonzero_alpha == 0
    and outside_nonzero_alpha == 0
    and core_not_full_alpha == 0
    and valid_zero_alpha == 0
    and abs(support_fraction - src_metrics['hybrid']['coverage_fraction']) <= 1e-12
)

metrics = {
    'gate': 'DRL_GNM_SAFE_FACIAL_CORE_FEATHER_SEAM',
    'resolution': int(expected.shape[0]),
    'pre_registered_contract': {
        'feather_width_pixels_at_1024': FEATHER_WIDTH,
        'equivalent_pixels_at_4096': FEATHER_WIDTH * 4,
        'minimum_legal_donor_support_fraction': MIN_SUPPORT_FRACTION,
        'minimum_full_alpha_core_fraction': MIN_CORE_FRACTION,
        'invalid_correspondence_must_have_zero_donor_alpha': True,
        'thresholds_fixed_before_real_data_run': True,
    },
    'source_correspondence': {
        'expected_hockey_uv_pixels': expected_count,
        'legal_donor_support_pixels': valid_count,
        'legal_donor_support_fraction': support_fraction,
        'source_cpu_hybrid_fraction': src_metrics['hybrid']['coverage_fraction'],
        'base_bidirectional_fraction': src_metrics['base_bidirectional_ray']['coverage_fraction'],
        'safe_nearest_fallback_pixels': src_metrics['fixed_nearest_fallback']['accepted_count'],
        'fallback_max_distance_mm': src_metrics['fixed_nearest_fallback']['max_distance_mm'],
        'fallback_normal_angle_limit_deg': src_metrics['fixed_nearest_fallback']['normal_angle_limit_deg'],
    },
    'blend_partition': {
        'full_alpha_core_pixels': core_count,
        'full_alpha_core_fraction_of_expected': core_fraction,
        'legal_feather_pixels': feather_count,
        'legal_feather_fraction_of_expected': feather_fraction,
        'base_gnm_only_pixels': base_only_count,
        'base_gnm_only_fraction_of_expected': base_only_fraction,
        'partition_sum_pixels': core_count + feather_count + base_only_count,
    },
    'safety_assertions': {
        'invalid_pixels_with_nonzero_donor_alpha': invalid_nonzero_alpha,
        'outside_hockey_pixels_with_nonzero_donor_alpha': outside_nonzero_alpha,
        'core_pixels_not_full_alpha': core_not_full_alpha,
        'valid_support_pixels_with_zero_alpha': valid_zero_alpha,
    },
    'decision': {
        'pass': bool(safety_pass),
        'selected_strategy': 'CPU_CORRESPONDENCE_SAFE_CORE_FEATHER_BLEND' if safety_pass else 'NONE_BLOCKED',
        'real_diffuse_only_gate_allowed_next': bool(safety_pass),
        'important_semantics': 'Base GNM skin fills unsafe donor-correspondence pixels; donor identity is sampled only where correspondence is legal.',
    },
    'source_protection': {
        'raw_drl_obj_uploaded': False,
        'raw_identity_texture_used': False,
        'identity_texture_uploaded': False,
    },
}

(OUT / 'safe_core_feather_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
# Preserve source CPU coverage metrics as evidence, without its DRL source.
shutil.copy2(SRC / 'cpu_fallback_metrics.json', OUT / 'source_cpu_fallback_metrics.json')
print(json.dumps(metrics, indent=2))
