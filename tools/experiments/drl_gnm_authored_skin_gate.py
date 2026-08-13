import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from tools.experiments.authored_skin_math import author_low_frequency_skin
from tools.experiments.transfer_ab_math import micro_height_from_lowpass

INPUT_DIFFUSE = Path(os.environ['DRL_DIFFUSE'])
INPUT_GLOSSINESS = Path(os.environ['DRL_GLOSSINESS'])
INPUT_SPECULAR = Path(os.environ['DRL_SPECULAR'])
SOURCE_DISP = Path(os.environ['DRL_DISPLACE_PROXY'])
LOWPASS_DISP = Path(os.environ['DRL_DISPLACE_LOWPASS'])

for p in (INPUT_DIFFUSE, INPUT_GLOSSINESS, INPUT_SPECULAR, SOURCE_DISP, LOWPASS_DISP):
    if not p.is_file() or p.stat().st_size <= 0:
        raise RuntimeError(f'missing authored-skin input: {p}')

TMP = Path('/tmp/drl-gnm-authored-skin')
TMP.mkdir(parents=True, exist_ok=True)

# Author a low-frequency skin base. The source scan supplies broad chromatic variation only;
# identity-scale high-frequency diffuse detail is deliberately suppressed.
source_diffuse = np.asarray(Image.open(INPUT_DIFFUSE).convert('RGB'), dtype=np.uint8)
authored_unit, authored_stats = author_low_frequency_skin(source_diffuse)
authored_u8 = np.clip(np.rint(authored_unit * 255.0), 0, 255).astype(np.uint8)
authored_path = TMP / 'authored_base_rgb.png'
Image.fromarray(authored_u8, mode='RGB').save(authored_path)

# Freeze the already accepted Bilateral32 displacement residual as the only micro-normal layer.
src = np.asarray(Image.open(SOURCE_DISP), dtype=np.float64)
low = np.asarray(Image.open(LOWPASS_DISP), dtype=np.float64)
if src.ndim == 3:
    src = src[..., 0]
if low.ndim == 3:
    low = low[..., 0]
if src.shape != low.shape or min(src.shape) < 2048:
    raise RuntimeError(f'unexpected displacement proxy shapes: {src.shape} / {low.shape}')
micro, micro_stats = micro_height_from_lowpass(src, low, percentile=99.5)
if float(np.std(micro)) < 0.01:
    raise RuntimeError('accepted Bilateral32 micro residual became unexpectedly flat')
micro_u8 = np.clip(np.rint((micro * 0.5 + 0.5) * 255.0), 0, 255).astype(np.uint8)
micro_rgb = np.repeat(micro_u8[:, :, None], 3, axis=2)
micro_path = TMP / 'micro_height_bilateral32_rgb.png'
Image.fromarray(micro_rgb, mode='RGB').save(micro_path)

os.environ['DRL_DIFFUSE'] = str(authored_path)
os.environ['DRL_MICRO_HEIGHT'] = str(micro_path)
os.environ['AUTHORED_SKIN_STATS_JSON'] = json.dumps(authored_stats)
os.environ['MICRO_STATS_JSON'] = json.dumps(micro_stats)

BASE = Path('tools/experiments/drl_gnm_diffuse_transfer_gate.py')
text = BASE.read_text(encoding='utf-8')
text = (
    "from tools.experiments.authored_skin_math import gloss_to_roughness, specular_to_level\n"
    + text
)
text = text.replace(
    "OUT = Path('artifacts/drl-gnm-diffuse-transfer-gate')",
    "OUT = Path('artifacts/drl-gnm-authored-skin-gate')",
    1,
)

# Keep the accepted high-confidence correspondence contract used by the micro-surface gate.
old_ray = '''        if normal_dot >= BASE_NORMAL_FLOOR:
            chosen = (distance, loc, face_index, method)
            break
'''
new_ray = '''        if bool(accept_nearest_fallback(
            np.asarray([distance]),
            np.asarray([normal_dot]),
            max_distance=FALLBACK_MAX_DISTANCE,
            min_abs_dot=FALLBACK_NORMAL_FLOOR,
        )[0]):
            chosen = (distance, loc, face_index, method)
            break
'''
if text.count(old_ray) != 1:
    raise RuntimeError('base ray acceptance block drifted')
text = text.replace(old_ray, new_ray)

sample_start = "# ---------------- sample real DRL diffuse (4K diagnostic proxy) ----------------"
sample_end = "# ---------------- render actual GNM geometry with GNM UV ----------------"
if sample_start not in text or sample_end not in text:
    raise RuntimeError('base sample/composition markers drifted')
sample_block = r'''# ---------------- sample authored material channels through accepted donor UV ----------------
diffuse_img = np.asarray(Image.open(DRL_DIFFUSE).convert('RGB'), dtype=np.uint8)
gloss_gray = np.asarray(Image.open(Path(os.environ['DRL_GLOSSINESS'])).convert('L'), dtype=np.uint8)
spec_gray = np.asarray(Image.open(Path(os.environ['DRL_SPECULAR'])).convert('L'), dtype=np.uint8)
micro_img = np.asarray(Image.open(Path(os.environ['DRL_MICRO_HEIGHT'])).convert('RGB'), dtype=np.uint8)
gloss_img = np.repeat(gloss_gray[:, :, None], 3, axis=2)
spec_img = np.repeat(spec_gray[:, :, None], 3, axis=2)

valid_yx = np.argwhere(valid)
uv_samples = donor_uv_map[valid]
rgb_samples = sample_image_bilinear(diffuse_img, uv_samples)
gloss_samples_raw = sample_image_bilinear(gloss_img, uv_samples)[:, 0]
spec_samples_raw = sample_image_bilinear(spec_img, uv_samples)[:, 0]
micro_samples = sample_image_bilinear(micro_img, uv_samples)[:, 0] / 255.0 * 2.0 - 1.0

if len(rgb_samples) < 100000 or float(np.std(rgb_samples)) < 1.0:
    raise RuntimeError('authored broad-color donor samples are unexpectedly flat or sparse')
rough_samples, rough_stats = gloss_to_roughness(gloss_samples_raw)
spec_level_samples, spec_stats = specular_to_level(spec_samples_raw)

# All maps are composed on the target GNM UV. Invalid correspondence receives neutral authored defaults.
base_rgb = np.median(rgb_samples, axis=0)
base_map = np.zeros((RES, RES, 3), dtype=np.float64)
base_map[:] = base_rgb
base_map[valid] = rgb_samples
blend = alpha[:, :, None]
final_rgb = np.clip(base_map * blend + base_rgb[None, None, :] * (1.0 - blend), 0, 255).astype(np.uint8)
base_path = TMP / 'gnm_authored_base_1024.png'
Image.fromarray(final_rgb, mode='RGB').save(base_path)

rough_map = np.full((RES, RES), 0.50, dtype=np.float64)
rough_map[valid] = rough_samples
rough_map = rough_map * alpha + 0.50 * (1.0 - alpha)
rough_min = float(rough_map[expected].min())
rough_max = float(rough_map[expected].max())
rough_u8 = np.clip(np.rint(rough_map * 255.0), 0, 255).astype(np.uint8)
rough_path = TMP / 'gnm_authored_roughness_1024.png'
Image.fromarray(rough_u8, mode='L').save(rough_path)

spec_map = np.full((RES, RES), 0.45, dtype=np.float64)
spec_map[valid] = spec_level_samples
spec_map = spec_map * alpha + 0.45 * (1.0 - alpha)
spec_min = float(spec_map[expected].min())
spec_max = float(spec_map[expected].max())
spec_u8 = np.clip(np.rint(spec_map * 255.0), 0, 255).astype(np.uint8)
spec_path = TMP / 'gnm_authored_specular_level_1024.png'
Image.fromarray(spec_u8, mode='L').save(spec_path)

height_signed = np.zeros((RES, RES), dtype=np.float64)
height_signed[valid] = micro_samples
height_signed *= alpha
height_u8 = np.clip(np.rint((height_signed * 0.5 + 0.5) * 255.0), 0, 255).astype(np.uint8)
height_path = TMP / 'gnm_bilateral32_micro_height_1024.png'
Image.fromarray(height_u8, mode='L').save(height_path)

authored_stats = json.loads(os.environ['AUTHORED_SKIN_STATS_JSON'])
micro_stats = json.loads(os.environ['MICRO_STATS_JSON'])

'''
a = text.index(sample_start)
b = text.index(sample_end, a)
text = text[:a] + sample_block + text[b:]

shader_start = "skin_mat = bpy.data.materials.new('GNM_Real_DRL_Diffuse_Only')"
shader_end = "skin_obj.data.materials.append(skin_mat)"
if shader_start not in text or shader_end not in text:
    raise RuntimeError('base skin shader block drifted')
shader_block = r'''skin_mat = bpy.data.materials.new('GNM_Authored_Skin_PBR')
skin_mat.use_nodes = True
nt = skin_mat.node_tree
bsdf = nt.nodes.get('Principled BSDF')

base_tex = nt.nodes.new('ShaderNodeTexImage')
base_tex.image = bpy.data.images.load(str(base_path))
base_tex.interpolation = 'Linear'
nt.links.new(base_tex.outputs['Color'], bsdf.inputs['Base Color'])

rough_tex = nt.nodes.new('ShaderNodeTexImage')
rough_tex.image = bpy.data.images.load(str(rough_path))
rough_tex.image.colorspace_settings.name = 'Non-Color'
rough_tex.interpolation = 'Linear'
nt.links.new(rough_tex.outputs['Color'], bsdf.inputs['Roughness'])

spec_tex = nt.nodes.new('ShaderNodeTexImage')
spec_tex.image = bpy.data.images.load(str(spec_path))
spec_tex.image.colorspace_settings.name = 'Non-Color'
spec_tex.interpolation = 'Linear'
spec_input = bsdf.inputs.get('Specular IOR Level') or bsdf.inputs.get('Specular')
if spec_input is not None:
    nt.links.new(spec_tex.outputs['Color'], spec_input)

height_tex = nt.nodes.new('ShaderNodeTexImage')
height_tex.image = bpy.data.images.load(str(height_path))
height_tex.image.colorspace_settings.name = 'Non-Color'
height_tex.interpolation = 'Linear'
bump = nt.nodes.new('ShaderNodeBump')
bump.inputs['Strength'].default_value = 0.32
bump.inputs['Distance'].default_value = 0.00035
nt.links.new(height_tex.outputs['Color'], bump.inputs['Height'])
nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

if bsdf.inputs.get('Subsurface Weight'):
    bsdf.inputs['Subsurface Weight'].default_value = 0.060
if bsdf.inputs.get('Metallic'):
    bsdf.inputs['Metallic'].default_value = 0.0
skin_obj.data.materials.append(skin_mat)'''
a = text.index(shader_start)
b = text.index(shader_end, a) + len(shader_end)
text = text[:a] + shader_block + text[b:]

cleanup_start = "# Never publish raw or derived identity texture; remove it before artifact collection."
cleanup_end = "# Render validity metrics."
if cleanup_start not in text or cleanup_end not in text:
    raise RuntimeError('base cleanup markers drifted')
cleanup_block = r'''# Temporary authored channel maps remain private and are deleted before artifact collection.
import hashlib
derived_hashes = {}
for label, path in {
    'authored_base': base_path,
    'roughness': rough_path,
    'specular_level': spec_path,
    'bilateral32_micro_height': height_path,
}.items():
    with path.open('rb') as f:
        derived_hashes[label] = hashlib.sha256(f.read()).hexdigest()
    path.unlink()
'''
a = text.index(cleanup_start)
b = text.index(cleanup_end, a)
text = text[:a] + cleanup_block + "\n" + text[b:]

metrics_start = "\nmetrics = {"
if metrics_start not in text:
    raise RuntimeError('base metrics block drifted')
metrics_block = r'''
metrics = {
    'gate': 'DRL_GNM_AUTHORED_SKIN_PBR_GATE',
    'source': {
        'donor': 'Digital Reality Lab Marcus PBR sample',
        'channels_used': {
            'base_color_broad_variation': 'Textures/Marcus_38_diffuse.png -> authored low-frequency only',
            'roughness': 'Textures/Marcus_38_glossiness.png -> bounded inverse gloss',
            'specular_level': 'Textures/Marcus_01_specular.png -> bounded dielectric response',
            'micro_surface': 'Textures/Marcus_38_Displace.exr -> Bilateral32 high-frequency residual',
        },
        'normal_map_used': False,
        'raw_or_derived_material_texture_uploaded': False,
        'temporary_target_texture_sha256_not_uploaded': derived_hashes,
    },
    'target': {
        'model': 'Google GNM v3',
        'semantic_scope': 'skin ∩ hockey_mask',
        'transfer_resolution': RES,
        'expected_hockey_pixels': expected_count,
        'outward_normal_fraction': outward_fraction,
    },
    'registration': {
        'rigid_iterations': rigid_iterations,
        'nonrigid_iterations': 7,
        'max_cumulative_deformation_mm': 24.0,
    },
    'correspondence': {
        'valid_pixels': valid_count,
        'valid_fraction': valid_fraction,
        'ray_accepted_pixels': ray_accepted,
        'safe_nearest_fallback_pixels': fallback_accepted,
        'invalid_face_index_count': invalid_face_index,
        'donor_uv_outside_unit_count_before_clamp': donor_uv_outside_unit,
        'barycentric_sum_error_max': float(max(bary_sum_errors)) if bary_sum_errors else None,
        'barycentric_min_p01': float(np.percentile(bary_min_values, 1)) if bary_min_values else None,
    },
    'blend': {
        'feather_width_pixels_at_1024': FEATHER_WIDTH,
        'full_alpha_core_pixels': int(core.sum()),
        'full_alpha_core_fraction': float(core.sum() / expected_count),
        'invalid_correspondence_nonzero_alpha': int(np.count_nonzero(alpha[~valid] > 0)),
    },
    'appearance_decomposition': {
        'authored_base_skin': authored_stats,
        'roughness_mapping': rough_stats,
        'roughness_target_range': [rough_min, rough_max],
        'specular_mapping': spec_stats,
        'specular_target_range': [spec_min, spec_max],
        'micro_surface_selection': 'bilateral32',
        'micro_height_stats': micro_stats,
        'bump_distance_mm': 0.35,
        'bump_strength': 0.32,
        'subsurface_weight_diagnostic': 0.060,
        'sss_calibrated': False,
    },
    'renders': render_stats,
    'decision_contract': {
        'minimum_correspondence_fraction': 0.70,
        'minimum_full_alpha_core_fraction': 0.30,
        'roughness_bounds': [0.38, 0.62],
        'specular_level_bounds': [0.35, 0.55],
        'must_not_sample_invalid_correspondence': True,
        'micro_surface_frozen': 'bilateral32',
        'single_material_candidate_only': True,
        'final_character_adopted': False,
        'visual_decision': 'PENDING_GPT_VISUAL_REVIEW',
    },
    'not_claimed': [
        'final character adoption',
        'final eye appearance',
        'final hair/brow/lash appearance',
        'calibrated tissue SSS',
        'web runtime material parity',
        'formal cinematic master asset',
    ],
}
pass_gate = (
    valid_fraction >= 0.70
    and float(core.sum() / expected_count) >= 0.30
    and int(np.count_nonzero(alpha[~valid] > 0)) == 0
    and invalid_face_index == 0
    and (max(bary_sum_errors) if bary_sum_errors else 1.0) <= 1e-5
    and len(rgb_samples) > 100000
    and np.isfinite(rough_map).all()
    and np.isfinite(spec_map).all()
    and rough_min >= 0.38 - 1e-6
    and rough_max <= 0.62 + 1e-6
    and spec_min >= 0.35 - 1e-6
    and spec_max <= 0.55 + 1e-6
)
metrics['decision'] = {
    'pass': bool(pass_gate),
    'status': 'PASS_READY_FOR_GPT_AUTHORED_SKIN_VISUAL_REVIEW' if pass_gate else 'FAIL_BLOCKED',
    'visual_decision': 'PENDING_GPT_VISUAL_REVIEW',
    'next_if_visual_pass': 'PASS_FREEZE_SKIN_MATERIAL_STAGE_THEN_MOVE_TO_EYES_HAIR',
    'next_if_visual_fail': 'FAIL_MATERIAL_STAGE_WITH_CONCRETE_DEFECT_ONLY',
}
(OUT / 'authored_skin_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
print(json.dumps(metrics, indent=2))
if not pass_gate:
    raise RuntimeError('authored-skin numeric contract failed')
'''
a = text.index(metrics_start)
text = text[:a] + "\n" + metrics_block

ns = {'__name__': '__main__', '__file__': str(BASE)}
exec(compile(text, str(BASE) + '::AUTHORED_SKIN', 'exec'), ns, ns)

out = Path('artifacts/drl-gnm-authored-skin-gate')
old_sheet = out / '00_drl_gnm_diffuse_transfer_contact_sheet.jpg'
new_sheet = out / '00_gnm_authored_skin_contact_sheet.jpg'
if old_sheet.is_file():
    old_sheet.replace(new_sheet)

# The source working maps are private /tmp inputs and are never part of the artifact directory.
for p in (authored_path, micro_path):
    if p.exists():
        p.unlink()
