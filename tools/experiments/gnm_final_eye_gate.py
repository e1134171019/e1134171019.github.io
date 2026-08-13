import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

AUTHORED = Path('tools/experiments/drl_gnm_authored_skin_gate.py')
source = AUTHORED.read_text(encoding='utf-8')

# Run the accepted authored-skin pipeline unchanged, but isolate all outputs for this eye gate.
source = source.replace('artifacts/drl-gnm-authored-skin-gate', 'artifacts/gnm-final-eye-gate')
source = source.replace('00_gnm_authored_skin_contact_sheet.jpg', '00_gnm_final_eye_contact_sheet.jpg')

needle = "text = BASE.read_text(encoding='utf-8')\n"
if source.count(needle) != 1:
    raise RuntimeError('authored-skin base-load marker drifted')

injection = r'''
# FINAL EYE LAYER ONLY. Preserve authored skin and replace the old neutral diagnostic eye block.
old_eye = """# Add GNM real eye anatomy as neutral materials so facial transfer can be reviewed in context.
sclera_mat = simple_material('GNM_Sclera', (0.65, 0.62, 0.58, 1), 0.28)
iris_mat = simple_material('GNM_Iris', (0.09, 0.13, 0.12, 1), 0.32)
pupil_mat = simple_material('GNM_Pupil', (0.002, 0.002, 0.002, 1), 0.18)
cornea_mat = simple_material('GNM_Cornea_Diagnostic', (0.12, 0.15, 0.17, 1), 0.08)
for group_name, material in [
    ('scleras', sclera_mat),
    ('irises', iris_mat),
    ('pupils', pupil_mat),
    ('eye_exteriors', cornea_mat),
]:
    if group_name in idx:
        make_semantic_object('GNM_' + group_name, G, gt, vg[idx[group_name]] > 0.5, material)
"""
new_eye = r"""# Final-eye candidate: nested eye semantics with a separate cornea shell.
from tools.experiments.eye_gate_math import measure_eye_alignment, priority_eye_partition

for required_eye_group in ('eye_interiors', 'eye_exteriors', 'scleras', 'irises', 'pupils'):
    if required_eye_group not in idx:
        raise RuntimeError(f'GNM final eye group missing: {required_eye_group}')

def _face_any(group_name):
    return (vg[idx[group_name]] > 0.5)[gt].any(axis=1)

parts = priority_eye_partition(
    _face_any('eye_interiors'),
    _face_any('irises'),
    _face_any('pupils'),
    _face_any('eye_exteriors'),
    _face_any('skin'),
)
part_counts = {name: int(mask.sum()) for name, mask in parts.items()}
for required_part in ('sclera', 'iris', 'pupil', 'cornea'):
    if part_counts[required_part] <= 0:
        raise RuntimeError(f'final eye partition produced zero {required_part}: {part_counts}')

alignment = measure_eye_alignment(
    G[vg[idx['scleras']] > 0.5],
    G[vg[idx['irises']] > 0.5],
    G[vg[idx['pupils']] > 0.5],
)
if alignment['max_pupil_to_iris_offset_ratio'] > 0.35:
    raise RuntimeError(f'pupil/iris centering escaped contract: {alignment}')
if alignment['gaze_mismatch_ratio'] > 0.12:
    raise RuntimeError(f'bilateral gaze mismatch escaped contract: {alignment}')
if alignment['sclera_bilateral_size_mismatch_ratio'] > 0.12:
    raise RuntimeError(f'sclera bilateral size mismatch escaped contract: {alignment}')

def _principled(name, color, roughness):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = color
    b.inputs['Roughness'].default_value = roughness
    if b.inputs.get('Metallic'):
        b.inputs['Metallic'].default_value = 0.0
    return m, b

# Warm off-white sclera; explicitly non-emissive and not pure white.
sclera_mat, sclera_bsdf = _principled('GNM_Final_Sclera', (0.56, 0.49, 0.43, 1.0), 0.36)
if sclera_bsdf.inputs.get('Subsurface Weight'):
    sclera_bsdf.inputs['Subsurface Weight'].default_value = 0.025

# Neutral dark-brown iris with deterministic micro-variation; no identity-specific eye color is claimed.
iris_mat, iris_bsdf = _principled('GNM_Final_Iris_Neutral', (0.050, 0.020, 0.009, 1.0), 0.27)
intree = iris_mat.node_tree
texcoord = intree.nodes.new('ShaderNodeTexCoord')
noise = intree.nodes.new('ShaderNodeTexNoise')
noise.inputs['Scale'].default_value = 32.0
noise.inputs['Detail'].default_value = 3.0
noise.inputs['Roughness'].default_value = 0.68
ramp = intree.nodes.new('ShaderNodeValToRGB')
ramp.color_ramp.elements[0].position = 0.22
ramp.color_ramp.elements[0].color = (0.010, 0.003, 0.001, 1.0)
ramp.color_ramp.elements[1].position = 0.78
ramp.color_ramp.elements[1].color = (0.16, 0.055, 0.012, 1.0)
intree.links.new(texcoord.outputs['Generated'], noise.inputs['Vector'])
intree.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
intree.links.new(ramp.outputs['Color'], iris_bsdf.inputs['Base Color'])
iris_bump = intree.nodes.new('ShaderNodeBump')
iris_bump.inputs['Strength'].default_value = 0.10
iris_bump.inputs['Distance'].default_value = 0.00006
intree.links.new(noise.outputs['Fac'], iris_bump.inputs['Height'])
intree.links.new(iris_bump.outputs['Normal'], iris_bsdf.inputs['Normal'])

pupil_mat, pupil_bsdf = _principled('GNM_Final_Pupil', (0.0015, 0.0015, 0.0015, 1.0), 0.16)

# Clear low-roughness corneal shell. Alpha keeps Eevee compatibility while preserving a visible wet catchlight.
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

def _make_faces(name, mask, material):
    faces = gt[np.asarray(mask, dtype=bool)]
    mesh = bpy.data.meshes.new(name + '_Mesh')
    mesh.from_pydata(G.tolist(), [], faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj

_make_faces('GNM_Final_Sclera', parts['sclera'], sclera_mat)
_make_faces('GNM_Final_Iris', parts['iris'], iris_mat)
_make_faces('GNM_Final_Pupil', parts['pupil'], pupil_mat)
_make_faces('GNM_Final_Cornea', parts['cornea'], cornea_mat)

os.environ['FINAL_EYE_METRICS_JSON'] = json.dumps({
    'semantic_partition': part_counts,
    'alignment': alignment,
    'materials': {
        'sclera': {'base_color': [0.56, 0.49, 0.43], 'roughness': 0.36, 'emission_used': False},
        'iris': {'identity_specific_color': False, 'neutral_dark_brown': True, 'roughness': 0.27, 'procedural_variation': 'deterministic Noise Texture'},
        'pupil': {'roughness': 0.16},
        'cornea': {'roughness': 0.035, 'ior': 1.376, 'alpha': 0.20, 'transmission_requested': 0.10},
    },
})
"""
if text.count(old_eye) != 1:
    raise RuntimeError('neutral diagnostic eye block drifted')
text = text.replace(old_eye, new_eye, 1)
'''
source = source.replace(needle, needle + injection, 1)

ns = {'__name__': '__main__', '__file__': str(AUTHORED)}
exec(compile(source, str(AUTHORED) + '::FINAL_EYE', 'exec'), ns, ns)

out = Path('artifacts/gnm-final-eye-gate')
skin_metrics_path = out / 'authored_skin_metrics.json'
if not skin_metrics_path.is_file():
    raise RuntimeError('frozen authored-skin metrics missing from final eye gate')
skin_metrics = json.loads(skin_metrics_path.read_text(encoding='utf-8'))
eye = json.loads(os.environ['FINAL_EYE_METRICS_JSON'])

alignment = eye['alignment']
counts = eye['semantic_partition']
numeric_pass = (
    bool(skin_metrics['decision']['pass'])
    and all(int(counts[name]) > 0 for name in ('sclera', 'iris', 'pupil', 'cornea'))
    and float(alignment['max_pupil_to_iris_offset_ratio']) <= 0.35
    and float(alignment['gaze_mismatch_ratio']) <= 0.12
    and float(alignment['sclera_bilateral_size_mismatch_ratio']) <= 0.12
    and skin_metrics['appearance_decomposition']['micro_surface_selection'] == 'bilateral32'
)

metrics = {
    'gate': 'GNM_FINAL_EYE_GATE',
    'source': {
        'target': 'Google GNM v3',
        'gnm_commit': '98450b3c943101d5859ac1ceb7331ec918ebc321',
        'gnm_npz_sha256': '868075bbb172fc6574ece89338e21fdc0efe0be91ca4e6e5c3166a1a97840055',
        'eye_partition_method': 'pupil > iris > sclera; cornea separate exterior shell',
    },
    'frozen_parent': {
        'status': 'PASS_FREEZE_SKIN_MATERIAL_STAGE',
        'skin_numeric_pass': bool(skin_metrics['decision']['pass']),
        'micro_surface': skin_metrics['appearance_decomposition']['micro_surface_selection'],
        'skin_frozen': True,
    },
    'eye': eye,
    'decision_contract': {
        'maximum_pupil_to_iris_offset_ratio': 0.35,
        'maximum_gaze_mismatch_ratio': 0.12,
        'maximum_sclera_bilateral_size_mismatch_ratio': 0.12,
        'single_eye_candidate_only': True,
        'skin_must_remain_frozen': True,
        'final_character_adopted': False,
        'visual_decision': 'PENDING_GPT_VISUAL_REVIEW',
    },
    'decision': {
        'pass': bool(numeric_pass),
        'status': 'PASS_READY_FOR_GPT_FINAL_EYE_VISUAL_REVIEW' if numeric_pass else 'FAIL_BLOCKED',
        'visual_decision': 'PENDING_GPT_VISUAL_REVIEW',
        'next_if_visual_pass': 'PASS_FREEZE_EYE_STAGE_THEN_MOVE_TO_BROWS_LASHES',
        'next_if_visual_fail': 'FAIL_EYE_STAGE_WITH_CONCRETE_DEFECT_ONLY',
    },
    'not_claimed': [
        'final character adoption',
        'final brows/lashes',
        'final hair',
        'web runtime material parity',
        'formal cinematic master asset',
    ],
}
(out / 'eye_metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')

# Rebuild a compact eye-review sheet from actual gate renders.
review_names = ['front.png', 'three_quarter_right.png', 'face_close.png', 'face_3q_close.png']
thumb = 420
sheet = Image.new('RGB', (thumb * 2, (thumb + 34) * 2), 'white')
draw = ImageDraw.Draw(sheet)
for i, name in enumerate(review_names):
    p = out / name
    if not p.is_file():
        raise RuntimeError(f'missing final eye review render: {name}')
    im = Image.open(p).convert('RGB')
    im.thumbnail((thumb, thumb), Image.Resampling.LANCZOS)
    x = (i % 2) * thumb
    y = (i // 2) * (thumb + 34)
    sheet.paste(im, (x, y + 34))
    draw.text((x + 8, y + 9), name.replace('.png', ''), fill='black')
sheet.save(out / '00_gnm_final_eye_review_contact_sheet.jpg', quality=95)

print(json.dumps(metrics, indent=2))
if not numeric_pass:
    raise RuntimeError('final eye numeric contract failed')
