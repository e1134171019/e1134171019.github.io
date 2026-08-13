import json
from pathlib import Path

from tools.experiments.cornea_material_contract import wet_cornea_contract

BASE = Path('tools/experiments/gnm_final_eye_gate.py')
source = BASE.read_text(encoding='utf-8')
contract = wet_cornea_contract()

# Keep the failed final-eye gate immutable as the visual baseline.  This wrapper
# redirects outputs and replaces only the cornea material block.
source = source.replace('artifacts/gnm-final-eye-gate', 'artifacts/gnm-cornea-catchlight-gate')
source = source.replace('00_gnm_final_eye_review_contact_sheet.jpg', '00_gnm_cornea_catchlight_review_contact_sheet.jpg')
source = source.replace("'gate': 'GNM_FINAL_EYE_GATE'", "'gate': 'GNM_CORNEA_CATCHLIGHT_GATE'")

old_cornea = r'''# Clear low-roughness corneal shell. Alpha keeps Eevee compatibility while preserving a visible wet catchlight.
cornea_mat, cornea_bsdf = _principled('GNM_Final_Cornea', (0.015, 0.020, 0.024, 1.0), 0.035)
if cornea_bsdf.inputs.get('IOR'):
    cornea_bsdf.inputs['IOR'].default_value = 1.376
spec_socket = cornea_bsdf.inputs.get('Specular IOR Level') or cornea_bsdf.inputs.get('Specular')
if spec_socket is not None:
    spec_socket.default_value = 0.55
trans_socket = cornea_bsdf.inputs.get('Transmission Weight') or cornea_bsdf.inputs.get('Transmission')
if trans_socket is not None:
    trans_socket.default_value = 0.10
if cornea_bsdf.inputs.get('Alpha'):
    cornea_bsdf.inputs['Alpha'].default_value = 0.20
if hasattr(cornea_mat, 'surface_render_method'):
    try:
        cornea_mat.surface_render_method = 'DITHERED'
    except Exception:
        pass
if hasattr(cornea_mat, 'blend_method'):
    try:
        cornea_mat.blend_method = 'BLEND'
        cornea_mat.show_transparent_back = False
    except Exception:
        pass
'''

new_cornea = rf'''# Bounded correction: transparent base plus explicit Fresnel reflection lobe.
# Geometry, gaze, iris, skin, lights and cameras are intentionally unchanged.
from tools.experiments.cornea_material_contract import wet_cornea_contract
_cornea_cfg = wet_cornea_contract()
cornea_mat = bpy.data.materials.new('GNM_Final_Cornea_Wet_Fresnel')
cornea_mat.use_nodes = True
ctree = cornea_mat.node_tree
ctree.nodes.clear()
cout = ctree.nodes.new('ShaderNodeOutputMaterial')
transparent = ctree.nodes.new('ShaderNodeBsdfTransparent')
reflective = ctree.nodes.new('ShaderNodeBsdfPrincipled')
reflective.inputs['Base Color'].default_value = (1.0, 1.0, 1.0, 1.0)
reflective.inputs['Roughness'].default_value = float(_cornea_cfg['roughness'])
if reflective.inputs.get('Metallic'):
    reflective.inputs['Metallic'].default_value = 1.0
fresnel = ctree.nodes.new('ShaderNodeFresnel')
fresnel.inputs['IOR'].default_value = float(_cornea_cfg['ior'])
boost = ctree.nodes.new('ShaderNodeMath')
boost.operation = 'MULTIPLY'
boost.use_clamp = True
boost.inputs[1].default_value = float(_cornea_cfg['fresnel_boost'])
mix = ctree.nodes.new('ShaderNodeMixShader')
ctree.links.new(fresnel.outputs['Fac'], boost.inputs[0])
ctree.links.new(boost.outputs[0], mix.inputs[0])
ctree.links.new(transparent.outputs['BSDF'], mix.inputs[1])
ctree.links.new(reflective.outputs['BSDF'], mix.inputs[2])
ctree.links.new(mix.outputs['Shader'], cout.inputs['Surface'])
'''

if source.count(old_cornea) != 1:
    raise RuntimeError('final-eye cornea block drifted; refusing non-bounded correction')
source = source.replace(old_cornea, new_cornea, 1)

old_metrics = "'cornea': {'roughness': 0.035, 'ior': 1.376, 'alpha': 0.20, 'transmission_requested': 0.10},"
new_metrics = (
    "'cornea': {"
    f"'roughness': {contract['roughness']!r}, "
    f"'ior': {contract['ior']!r}, "
    f"'fresnel_boost': {contract['fresnel_boost']!r}, "
    "'transparent_base': True, 'alpha_blending': False, "
    f"'reflection_lobe': {contract['reflection_lobe']!r}"
    "},"
)
if source.count(old_metrics) != 1:
    raise RuntimeError('final-eye cornea metrics marker drifted')
source = source.replace(old_metrics, new_metrics, 1)

ns = {'__name__': '__main__', '__file__': str(BASE)}
exec(compile(source, str(BASE) + '::CORNEA_CATCHLIGHT', 'exec'), ns, ns)

out = Path('artifacts/gnm-cornea-catchlight-gate')
metrics_path = out / 'eye_metrics.json'
metrics = json.loads(metrics_path.read_text(encoding='utf-8'))
metrics['correction'] = {
    'parent_visual_status': 'FAIL_EYE_STAGE_CONCRETE_DEFECT_CORNEA_CATCHLIGHT',
    'scope': 'cornea_material_only',
    'hypothesis': 'remove low-alpha attenuation and restore visible Fresnel wet-surface reflection',
    'contract': contract,
    'geometry_changed': False,
    'gaze_changed': False,
    'iris_changed': False,
    'skin_changed': False,
    'lighting_changed': False,
    'camera_changed': False,
}
metrics['decision']['status'] = 'PASS_READY_FOR_GPT_CORNEA_VISUAL_REVIEW'
metrics['decision']['visual_decision'] = 'PENDING_GPT_VISUAL_REVIEW'
metrics['decision']['next_if_visual_pass'] = 'PASS_FREEZE_EYE_STAGE_THEN_MOVE_TO_BROWS_LASHES'
metrics['decision']['next_if_visual_fail'] = 'FAIL_EYE_STAGE_CORNEA_CORRECTION_EXHAUSTED'
metrics_path.write_text(json.dumps(metrics, indent=2), encoding='utf-8')

print(json.dumps(metrics, indent=2))
