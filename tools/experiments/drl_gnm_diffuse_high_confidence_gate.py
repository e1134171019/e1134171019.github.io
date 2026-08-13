import json
import runpy
from pathlib import Path

SOURCE = Path('tools/experiments/drl_gnm_diffuse_transfer_gate.py')
text = SOURCE.read_text(encoding='utf-8')

# This diagnostic deliberately reuses the verified diffuse transfer implementation,
# changing only the correspondence acceptance contract. Both normal-ray hits and
# nearest-surface fallback must satisfy the same <=15 mm / <=60 degree rule.
old_ray = """        if normal_dot >= BASE_NORMAL_FLOOR:\n            chosen = (distance, loc, face_index, method)\n            break\n"""
new_ray = """        if bool(accept_nearest_fallback(\n            np.asarray([distance]),\n            np.asarray([normal_dot]),\n            max_distance=FALLBACK_MAX_DISTANCE,\n            min_abs_dot=FALLBACK_NORMAL_FLOOR,\n        )[0]):\n            chosen = (distance, loc, face_index, method)\n            break\n"""
if text.count(old_ray) != 1:
    raise RuntimeError(f'expected exactly one ray acceptance block, found {text.count(old_ray)}')
text = text.replace(old_ray, new_ray)

# This is a diagnostic-render threshold, not a claim of final coverage quality.
# It is fixed before seeing the high-confidence run result so the job can render a
# deliberately smaller but safer donor core for GPT visual review.
text = text.replace("'minimum_correspondence_fraction': 0.90,", "'minimum_correspondence_fraction': 0.70,")
text = text.replace("'minimum_full_alpha_core_fraction': 0.50,", "'minimum_full_alpha_core_fraction': 0.30,")
text = text.replace("        'maximum_reference_drift': 0.005,", "        'maximum_reference_drift': None,")
text = text.replace("    valid_fraction >= 0.90\n", "    valid_fraction >= 0.70\n")
text = text.replace("    and float(core.sum() / expected_count) >= 0.50\n", "    and float(core.sum() / expected_count) >= 0.30\n")
text = text.replace("    and abs(valid_fraction - REFERENCE_HYBRID) <= 0.005\n", "")

code = compile(text, str(SOURCE) + '::HIGH_CONFIDENCE', 'exec')
ns = {'__name__': '__main__', '__file__': str(SOURCE)}
exec(code, ns, ns)

out = Path('artifacts/drl-gnm-diffuse-transfer-gate/diffuse_transfer_metrics.json')
m = json.loads(out.read_text(encoding='utf-8'))
m['gate'] = 'DRL_GNM_REAL_DIFFUSE_HIGH_CONFIDENCE_DIAGNOSTIC'
m['high_confidence_contract'] = {
    'ray_and_nearest_max_distance_mm': 15.0,
    'ray_and_nearest_normal_angle_limit_deg': 60.0,
    'ray_and_nearest_normal_abs_dot_floor': 0.5,
    'diagnostic_minimum_support_fraction': 0.70,
    'diagnostic_minimum_full_alpha_core_fraction': 0.30,
    'thresholds_fixed_before_real_data_run': True,
    'quality_policy': 'Prefer base GNM skin over any DRL sample that fails high-confidence geometry.',
}
m['decision']['status'] = 'PASS_READY_FOR_GPT_HIGH_CONFIDENCE_VISUAL_REVIEW' if m['decision']['pass'] else 'FAIL_BLOCKED'
m['decision']['next_if_visual_pass'] = 'ACCEPT_HIGH_CONFIDENCE_DIFFUSE_PLACEMENT_THEN_TRANSFER_NORMAL_GLOSS_SPECULAR'
m['decision']['next_if_visual_fail'] = 'REJECT_DIRECT_DRl_IDENTITY_TRANSFER_OR_ADD_EXPLICIT_ANATOMICAL_LANDMARK_SEGMENTATION'
out.write_text(json.dumps(m, indent=2), encoding='utf-8')
print(json.dumps(m, indent=2))
