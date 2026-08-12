import json
import os
import runpy
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path('artifacts/drl-gnm-bake-coverage-diagnose')
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path('/tmp/drl-gnm-hockey-bake')
GNM_MODEL = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
BAKE_SIZE = int(os.environ.get('BAKE_SIZE', '2048'))

# Reproduce the exact failed bake path first. The old gate is expected to raise only
# after Cycles has written coverage.png and the raw diffuse bake into /tmp.
reproduced_error = None
try:
    runpy.run_path('tools/experiments/drl_gnm_hockey_diffuse_bake_gate.py', run_name='__main__')
except RuntimeError as exc:
    reproduced_error = str(exc)
    if 'diffuse bake has no valid pixels' not in reproduced_error:
        raise

coverage_path = TMP / 'coverage.png'
diffuse_path = TMP / 'gnm_hockey_drl_diffuse.png'
if not coverage_path.is_file():
    raise RuntimeError('coverage.png was not produced by the reproduced Cycles bake')

# Reconstruct the expected GNM hockey-mask UV footprint from the same pinned NPZ.
with np.load(GNM_MODEL, allow_pickle=False) as d:
    triangles = np.asarray(d['triangles'], dtype=np.int64)
    triangle_uvs = np.asarray(d['triangle_uvs'], dtype=np.float64)
    vertex_groups = np.asarray(d['vertex_groups'], dtype=np.float64)
    names = [str(x) for x in d['vertex_group_names']]
idx = {n: i for i, n in enumerate(names)}
for name in ('skin', 'hockey_mask'):
    if name not in idx:
        raise RuntimeError(f'missing GNM semantic group {name}')
skin = vertex_groups[idx['skin']] > 0.5
hockey = vertex_groups[idx['hockey_mask']] > 0.5
face_mask = (skin & hockey)[triangles].all(axis=1)
uvs = triangle_uvs[face_mask]

expected = Image.new('L', (BAKE_SIZE, BAKE_SIZE), 0)
draw = ImageDraw.Draw(expected)
for tri in uvs:
    pts = [
        (
            int(np.clip(uv[0], 0, 1) * (BAKE_SIZE - 1)),
            int((1.0 - np.clip(uv[1], 0, 1)) * (BAKE_SIZE - 1)),
        )
        for uv in tri
    ]
    draw.polygon(pts, fill=255)
expected_np = np.asarray(expected) > 127
expected.save(OUT / 'expected_uv_mask.png')

# Preserve only the identity-free white coverage diagnostic.
cov_rgba = Image.open(coverage_path).convert('RGBA')
cov_rgba.save(OUT / 'actual_cycles_coverage_rgba.png')
cov_rgb = np.asarray(cov_rgba)[..., :3]
cov_alpha = np.asarray(cov_rgba)[..., 3]
# Treat any sufficiently bright RGB pixel as a Cycles hit. Record alpha separately.
cov_luma = 0.2126 * cov_rgb[..., 0] + 0.7152 * cov_rgb[..., 1] + 0.0722 * cov_rgb[..., 2]
cov_np = cov_luma > 127
Image.fromarray((cov_np.astype(np.uint8) * 255), mode='L').save(OUT / 'actual_cycles_coverage_mask.png')


def bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def centroid(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return [float(xs.mean()), float(ys.mean())]


def overlap(candidate):
    inter = int((expected_np & candidate).sum())
    union = int((expected_np | candidate).sum())
    return {
        'intersection_pixels': inter,
        'expected_recall': float(inter / max(int(expected_np.sum()), 1)),
        'actual_precision': float(inter / max(int(candidate.sum()), 1)),
        'iou': float(inter / max(union, 1)),
    }

variants = {
    'direct': cov_np,
    'flip_v': np.flipud(cov_np),
    'flip_u': np.fliplr(cov_np),
    'flip_uv': np.flipud(np.fliplr(cov_np)),
}
overlaps = {name: overlap(mask) for name, mask in variants.items()}
best_name = max(overlaps, key=lambda n: overlaps[n]['expected_recall'])

# Safe composite: expected red, actual coverage blue, intersection green.
composite = np.zeros((BAKE_SIZE, BAKE_SIZE, 3), dtype=np.uint8)
composite[expected_np] = (220, 45, 35)
composite[cov_np] = (35, 90, 220)
composite[expected_np & cov_np] = (40, 190, 70)
Image.fromarray(composite).resize((1024, 1024), Image.Resampling.NEAREST).save(
    OUT / 'direct_overlap_composite.png'
)

# Also render the best orientation overlap, without changing the actual bake.
best_mask = variants[best_name]
best_comp = np.zeros((BAKE_SIZE, BAKE_SIZE, 3), dtype=np.uint8)
best_comp[expected_np] = (220, 45, 35)
best_comp[best_mask] = (35, 90, 220)
best_comp[expected_np & best_mask] = (40, 190, 70)
Image.fromarray(best_comp).resize((1024, 1024), Image.Resampling.NEAREST).save(
    OUT / 'best_orientation_overlap_composite.png'
)

# The raw diffuse bake is not redistributed; only report whether Cycles wrote nonzero RGB.
diffuse_diag = None
if diffuse_path.is_file():
    diff = np.asarray(Image.open(diffuse_path).convert('RGB'))
    diff_luma = 0.2126 * diff[..., 0] + 0.7152 * diff[..., 1] + 0.0722 * diff[..., 2]
    diffuse_diag = {
        'file_exists': True,
        'nonblack_pixels': int((diff_luma > 2).sum()),
        'mean_luma_all_pixels': float(diff_luma.mean()),
        'max_luma': float(diff_luma.max()),
    }
else:
    diffuse_diag = {'file_exists': False}

actual_count = int(cov_np.sum())
expected_count = int(expected_np.sum())
metrics = {
    'reproduced_original_failure': reproduced_error,
    'bake_size': BAKE_SIZE,
    'expected': {
        'pixels': expected_count,
        'bbox_xyxy': bbox(expected_np),
        'centroid_xy': centroid(expected_np),
    },
    'actual_cycles_coverage': {
        'bright_rgb_pixels': actual_count,
        'bbox_xyxy': bbox(cov_np),
        'centroid_xy': centroid(cov_np),
        'alpha_nonzero_pixels': int((cov_alpha > 0).sum()),
        'alpha_opaque_pixels': int((cov_alpha > 250).sum()),
        'rgb_channel_min': [int(x) for x in cov_rgb.reshape(-1, 3).min(axis=0)],
        'rgb_channel_max': [int(x) for x in cov_rgb.reshape(-1, 3).max(axis=0)],
    },
    'overlap_variants': overlaps,
    'best_orientation': best_name,
    'best_expected_recall': overlaps[best_name]['expected_recall'],
    'raw_diffuse_bake_diagnostic_only': diffuse_diag,
    'diagnosis': None,
    'gate_claim': 'Root-cause diagnostic only. No cage/ray parameter change and no raw DRL identity texture redistribution.',
}

if actual_count == 0:
    metrics['diagnosis'] = 'ACTUAL_CYCLES_COVERAGE_ZERO'
elif overlaps[best_name]['expected_recall'] >= 0.80 and best_name != 'direct':
    metrics['diagnosis'] = 'UV_IMAGE_ORIENTATION_MISMATCH'
elif overlaps['direct']['expected_recall'] >= 0.80:
    metrics['diagnosis'] = 'DIRECT_UV_COVERAGE_PRESENT_CONTRACT_BUG_ELSEWHERE'
else:
    metrics['diagnosis'] = 'CYCLES_COVERAGE_PRESENT_BUT_PROJECTION_OR_UV_FOOTPRINT_MISMATCH'

(OUT / 'coverage_root_cause_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
