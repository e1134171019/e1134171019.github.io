import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Vector

# Reuse the previously verified geometry/joint/skin bind pipeline in the same Blender process.
# This intentionally regenerates the diagnostic bind outputs before look-dev so the appearance
# gate cannot silently drift from the tested MHR/GNM foundation.
exec(compile(Path('tools/experiments/gnm_mhr_head_bind_gate.py').read_text(encoding='utf-8'), 'gnm_mhr_head_bind_gate.py', 'exec'), globals())

APP_OUT = Path('artifacts/gnm-mhr-appearance-gate')
APP_OUT.mkdir(parents=True, exist_ok=True)

head = bpy.data.objects.get('GNM_Head_Bound_To_MHR')
armature = next((o for o in bpy.context.scene.objects if o.type == 'ARMATURE'), None)
body_visual = bpy.data.objects.get('MHR_Body_Cropped_Visual')
if head is None or armature is None:
    raise RuntimeError('Verified bound GNM head / MHR armature missing after bind bootstrap')

GNM_MODEL_PATH = Path(os.environ.get('GNM_MODEL', '/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
with np.load(GNM_MODEL_PATH, allow_pickle=False) as d:
    tris = np.asarray(d['triangles'], dtype=np.int64)
    tri_uvs = np.asarray(d['triangle_uvs'], dtype=np.float64)
    vg = np.asarray(d['vertex_groups'], dtype=np.float64)
    vg_names = [str(x) for x in d['vertex_group_names']]

if tri_uvs.shape[:2] != (len(tris), 3) or tri_uvs.shape[2] != 2:
    raise RuntimeError(f'Unexpected triangle_uvs shape: {tri_uvs.shape}')
if len(head.data.polygons) != len(tris):
    raise RuntimeError(f'Head topology drift: mesh polys={len(head.data.polygons)} GNM tris={len(tris)}')

# Install the official GNM triangulated UV layout onto the bound mesh.
if head.data.uv_layers:
    uv_layer = head.data.uv_layers[0]
    uv_layer.name = 'GNM_UV'
else:
    uv_layer = head.data.uv_layers.new(name='GNM_UV')
for poly in head.data.polygons:
    for corner, loop_index in enumerate(poly.loop_indices):
        uv = tri_uvs[poly.index, corner]
        uv_layer.data[loop_index].uv = (float(uv[0]), float(uv[1]))

# Helpers --------------------------------------------------------------------
def principled_input(bsdf, aliases, value):
    for name in aliases:
        sock = bsdf.inputs.get(name)
        if sock is not None:
            sock.default_value = value
            return name
    return None


def node_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (700, 0)
    return m, nt, out


def make_skin():
    m, nt, out = node_mat('GNM_Skin_Appearance_v1')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (430, 0)
    principled_input(bsdf, ['Roughness'], 0.46)
    principled_input(bsdf, ['Subsurface Weight', 'Subsurface'], 0.105)
    principled_input(bsdf, ['Subsurface Radius'], (1.0, 0.42, 0.24))
    principled_input(bsdf, ['IOR'], 1.43)
    principled_input(bsdf, ['IOR Level', 'Specular IOR Level'], 0.34)
    principled_input(bsdf, ['Coat Weight', 'Clearcoat'], 0.065)
    principled_input(bsdf, ['Coat Roughness', 'Clearcoat Roughness'], 0.23)

    tex = nt.nodes.new('ShaderNodeTexCoord')
    tex.location = (-900, 0)

    macro = nt.nodes.new('ShaderNodeTexNoise')
    macro.location = (-680, 140)
    macro.inputs['Scale'].default_value = 5.5
    macro.inputs['Detail'].default_value = 4.0
    macro.inputs['Roughness'].default_value = 0.72
    nt.links.new(tex.outputs['UV'], macro.inputs['Vector'])

    tone = nt.nodes.new('ShaderNodeValToRGB')
    tone.location = (-430, 150)
    tone.color_ramp.elements[0].position = 0.18
    tone.color_ramp.elements[0].color = (0.115, 0.038, 0.022, 1.0)
    tone.color_ramp.elements[1].position = 0.82
    tone.color_ramp.elements[1].color = (0.46, 0.205, 0.105, 1.0)
    mid = tone.color_ramp.elements.new(0.52)
    mid.color = (0.275, 0.095, 0.052, 1.0)
    nt.links.new(macro.outputs['Fac'], tone.inputs['Fac'])
    nt.links.new(tone.outputs['Color'], bsdf.inputs['Base Color'])

    pores = nt.nodes.new('ShaderNodeTexNoise')
    pores.location = (-680, -170)
    pores.inputs['Scale'].default_value = 235.0
    pores.inputs['Detail'].default_value = 2.2
    pores.inputs['Roughness'].default_value = 0.78
    nt.links.new(tex.outputs['UV'], pores.inputs['Vector'])

    rough = nt.nodes.new('ShaderNodeValToRGB')
    rough.location = (-410, -110)
    rough.color_ramp.elements[0].color = (0.34, 0.34, 0.34, 1)
    rough.color_ramp.elements[1].color = (0.58, 0.58, 0.58, 1)
    nt.links.new(pores.outputs['Fac'], rough.inputs['Fac'])
    nt.links.new(rough.outputs['Color'], bsdf.inputs['Roughness'])

    bump = nt.nodes.new('ShaderNodeBump')
    bump.location = (180, -160)
    bump.inputs['Strength'].default_value = 0.20
    bump.inputs['Distance'].default_value = 0.00016
    nt.links.new(pores.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return m


def make_sclera():
    m, nt, out = node_mat('GNM_Sclera_Appearance_v1')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (360, 0)
    principled_input(bsdf, ['Base Color'], (0.69, 0.58, 0.53, 1))
    principled_input(bsdf, ['Roughness'], 0.31)
    principled_input(bsdf, ['Subsurface Weight', 'Subsurface'], 0.035)
    principled_input(bsdf, ['IOR'], 1.38)
    principled_input(bsdf, ['IOR Level', 'Specular IOR Level'], 0.29)
    tex = nt.nodes.new('ShaderNodeTexCoord'); tex.location=(-720,0)
    noise = nt.nodes.new('ShaderNodeTexNoise'); noise.location=(-520,0)
    noise.inputs['Scale'].default_value=95.0; noise.inputs['Detail'].default_value=2.0; noise.inputs['Roughness'].default_value=0.7
    nt.links.new(tex.outputs['UV'],noise.inputs['Vector'])
    bump=nt.nodes.new('ShaderNodeBump'); bump.location=(100,-110); bump.inputs['Strength'].default_value=0.055; bump.inputs['Distance'].default_value=0.00005
    nt.links.new(noise.outputs['Fac'],bump.inputs['Height']); nt.links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])
    return m


def make_iris():
    m, nt, out = node_mat('GNM_Iris_Appearance_v1')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location=(390,0)
    principled_input(bsdf,['Roughness'],0.27); principled_input(bsdf,['IOR'],1.38); principled_input(bsdf,['IOR Level','Specular IOR Level'],0.22)
    tex=nt.nodes.new('ShaderNodeTexCoord'); tex.location=(-760,0)
    noise=nt.nodes.new('ShaderNodeTexNoise'); noise.location=(-560,70); noise.inputs['Scale'].default_value=72.0; noise.inputs['Detail'].default_value=3.5; noise.inputs['Roughness'].default_value=0.7
    nt.links.new(tex.outputs['UV'],noise.inputs['Vector'])
    ramp=nt.nodes.new('ShaderNodeValToRGB'); ramp.location=(-300,100)
    ramp.color_ramp.elements[0].color=(0.006,0.020,0.008,1); ramp.color_ramp.elements[0].position=0.18
    ramp.color_ramp.elements[1].color=(0.20,0.095,0.018,1); ramp.color_ramp.elements[1].position=0.84
    e=ramp.color_ramp.elements.new(0.48); e.color=(0.022,0.12,0.055,1)
    nt.links.new(noise.outputs['Fac'],ramp.inputs['Fac']); nt.links.new(ramp.outputs['Color'],bsdf.inputs['Base Color'])
    bump=nt.nodes.new('ShaderNodeBump'); bump.location=(120,-130); bump.inputs['Strength'].default_value=0.16; bump.inputs['Distance'].default_value=0.00006
    nt.links.new(noise.outputs['Fac'],bump.inputs['Height']); nt.links.new(bump.outputs['Normal'],bsdf.inputs['Normal'])
    nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])
    return m


def make_pupil():
    m, nt, out = node_mat('GNM_Pupil_Appearance_v1')
    bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location=(340,0)
    principled_input(bsdf,['Base Color'],(0.001,0.001,0.001,1)); principled_input(bsdf,['Roughness'],0.12); principled_input(bsdf,['IOR Level','Specular IOR Level'],0.16)
    nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])
    return m


def make_cornea():
    m, nt, out = node_mat('GNM_Cornea_Appearance_v1')
    bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location=(350,0)
    principled_input(bsdf,['Base Color'],(0.82,0.92,1.0,1)); principled_input(bsdf,['Roughness'],0.025); principled_input(bsdf,['IOR'],1.376)
    principled_input(bsdf,['Transmission Weight','Transmission'],0.98); principled_input(bsdf,['Alpha'],0.16); principled_input(bsdf,['IOR Level','Specular IOR Level'],0.5)
    nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])
    if hasattr(m,'blend_method'):
        try: m.blend_method='BLEND'
        except Exception: pass
    if hasattr(m,'surface_render_method'):
        try: m.surface_render_method='DITHERED'
        except Exception: pass
    if hasattr(m,'use_screen_refraction'):
        try: m.use_screen_refraction=True
        except Exception: pass
    return m


def simple_principled(name, color, rough, sss=0.0):
    m, nt, out=node_mat(name); bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location=(350,0)
    principled_input(bsdf,['Base Color'],color); principled_input(bsdf,['Roughness'],rough); principled_input(bsdf,['Subsurface Weight','Subsurface'],sss)
    nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface']); return m

materials={
    'skin':make_skin(),
    'sclera':make_sclera(),
    'iris':make_iris(),
    'pupil':make_pupil(),
    'cornea':make_cornea(),
    'teeth':simple_principled('GNM_Teeth_Appearance_v1',(0.72,0.64,0.52,1),0.26,0.02),
    'tongue':simple_principled('GNM_Tongue_Appearance_v1',(0.33,0.055,0.055,1),0.40,0.07),
}

# Semantic face partition. GNM eye masks are nested, so keep the verified pupil > iris > sclera priority.
idx={n:i for i,n in enumerate(vg_names)}
required=['skin','eye_interiors','eye_exteriors','irises','pupils','upper_teeth_and_gums','lower_teeth_and_gums','tongue']
missing=[n for n in required if n not in idx]
if missing:
    raise RuntimeError(f'Missing GNM semantic groups: {missing}')

def vmask(name): return vg[idx[name]] > 0.5
def fany(name): return vmask(name)[tris].any(axis=1)

eye=fany('eye_interiors')
iris=eye & fany('irises')
pupil=eye & fany('pupils')
sclera=eye & ~iris
iris=iris & ~pupil
cornea=fany('eye_exteriors')
teeth=fany('upper_teeth_and_gums') | fany('lower_teeth_and_gums')
tongue=fany('tongue')
skin=fany('skin') & ~eye & ~cornea & ~teeth & ~tongue
masks={'skin':skin,'sclera':sclera,'iris':iris,'pupil':pupil,'cornea':cornea,'teeth':teeth,'tongue':tongue}
counts={k:int(v.sum()) for k,v in masks.items()}
for critical in ['skin','sclera','iris','pupil','cornea']:
    if counts[critical] <= 0:
        raise RuntimeError(f'Appearance partition lost critical component {critical}: {counts}')

head.data.materials.clear()
slot={}
for key in ['skin','sclera','iris','pupil','cornea','teeth','tongue']:
    slot[key]=len(head.data.materials)
    head.data.materials.append(materials[key])
for pi,poly in enumerate(head.data.polygons):
    if cornea[pi]: poly.material_index=slot['cornea']
    elif pupil[pi]: poly.material_index=slot['pupil']
    elif iris[pi]: poly.material_index=slot['iris']
    elif sclera[pi]: poly.material_index=slot['sclera']
    elif teeth[pi]: poly.material_index=slot['teeth']
    elif tongue[pi]: poly.material_index=slot['tongue']
    else: poly.material_index=slot['skin']

# Studio look-dev setup -------------------------------------------------------
scene=bpy.context.scene
scene.render.engine='BLENDER_EEVEE'
scene.render.resolution_x=960
scene.render.resolution_y=960
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.world.color=(0.012,0.014,0.019)
scene.view_settings.exposure=-0.85

# Remove bind diagnostic lights/cameras only; preserve geometry and rig.
for obj in list(scene.objects):
    if obj.type in {'LIGHT','CAMERA'}:
        bpy.data.objects.remove(obj,do_unlink=True)

def add_area(name, loc, energy, size, color=(1,1,1)):
    ld=bpy.data.lights.new(name,type='AREA'); ld.energy=energy; ld.shape='DISK'; ld.size=size; ld.color=color
    ob=bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(ob); ob.location=Vector(loc); return ob

neutral_pts=evaluated_vertices_world(head)
hmin,hmax=neutral_pts.min(0),neutral_pts.max(0)
hcenter=(hmin+hmax)/2
hext=hmax-hmin
head_scale=float(max(hext))

def around(direction, distance):
    return Vector(hcenter)+Vector(direction).normalized()*distance

key=add_area('Appearance_Key',around((1.3,-1.6,1.0),head_scale*2.2),75.0,head_scale*0.55,(1.0,0.78,0.68))
fill=add_area('Appearance_Fill',around((-1.2,-0.9,0.3),head_scale*2.0),28.0,head_scale*0.72,(0.62,0.74,1.0))
rim=add_area('Appearance_Rim',around((0.2,1.4,1.0),head_scale*2.0),48.0,head_scale*0.42,(0.75,0.86,1.0))
for l in [key,fill,rim]:
    l.rotation_euler=(Vector(hcenter)-l.location).to_track_quat('-Z','Y').to_euler()

camd=bpy.data.cameras.new('AppearanceCamera'); cam=bpy.data.objects.new('AppearanceCamera',camd); bpy.context.collection.objects.link(cam); scene.camera=cam; cam.data.type='ORTHO'; cam.data.lens=72

def render(name, axis, target, ortho_scale):
    axis=Vector(axis).normalized(); target=Vector(target)
    cam.location=target+axis*head_scale*2.5
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.ortho_scale=ortho_scale
    scene.render.filepath=str((APP_OUT/name).resolve())
    bpy.ops.render.render(write_still=True)

# MHR coordinate convention from the verified bind gate: -Y is front.
front=(0,-1,0); threeq=(0.68,-1,0); side=(1,0,0)
head_target=Vector(hcenter)
eye_target=Vector((target_world['left_eye']+target_world['right_eye'])/2)

# Head views: evaluate skin response, proportions and eye integration.
if body_visual is not None: body_visual.hide_render=True
render('appearance_head_front.png',front,head_target,float(max(hext[0],hext[2])*1.16))
render('appearance_head_three_quarter.png',threeq,head_target,float(max(hext[0],hext[2])*1.16))
render('appearance_head_side.png',side,head_target,float(max(hext[1],hext[2])*1.16))

# Eye close-ups: verify layered sclera/iris/pupil/cornea under the final material stack.
eye_sep=float(np.linalg.norm(target_world['left_eye']-target_world['right_eye']))
eye_view=max(eye_sep*1.6, head_scale*0.32)
render('appearance_eye_front.png',front,eye_target,eye_view)
render('appearance_eye_three_quarter.png',threeq,eye_target,eye_view)

# Grazing-light micro-surface diagnostic. Reposition the key to emphasize pores/roughness response.
key.location=around((1.7,-0.15,0.35),head_scale*2.0)
key.rotation_euler=(Vector(hcenter)-key.location).to_track_quat('-Z','Y').to_euler(); key.data.energy=92.0
fill.data.energy=9.0; rim.data.energy=18.0
render('appearance_micro_grazing.png',threeq,head_target,float(max(hext[0],hext[2])*0.72))

# Bust context with MHR carrier visible; this is still a diagnostic seam view, not a topology merge claim.
if body_visual is not None:
    body_visual.hide_render=False
    # Give the MHR body a neutral skin-adjacent material so the head/body scale transition is visible without pretending texture continuity.
    body_visual.data.materials.clear(); body_visual.data.materials.append(simple_principled('MHR_Body_Context',(0.13,0.055,0.035,1),0.54,0.04))
    bpts=np.array([(body_visual.matrix_world @ v.co)[:] for v in body_visual.data.vertices],dtype=np.float64)
    bmin,bmax=bpts.min(0),bpts.max(0); bcenter=(bmin+bmax)/2; bscale=float(max(bmax-bmin))
    render('appearance_bust_front.png',front,Vector(bcenter),bscale*0.72)
    render('appearance_bust_three_quarter.png',threeq,Vector(bcenter),bscale*0.72)

# Export a GLB as a portability diagnostic. Blender procedural Noise/Bump nodes are not assumed to survive glTF;
# this artifact is used to inspect skin/material structure and confirms geometry/rig remain exportable.
bpy.ops.object.select_all(action='DESELECT'); head.select_set(True); armature.select_set(True); bpy.context.view_layer.objects.active=armature
bpy.ops.export_scene.gltf(filepath=str((APP_OUT/'gnm_mhr_appearance_prototype.glb').resolve()),export_format='GLB',use_selection=True)

metrics={
    'foundation':{
        'GNM_commit':'98450b3c943101d5859ac1ceb7331ec918ebc321',
        'MHR_version':'v1.0.1',
        'bind_gate':'reused tools/experiments/gnm_mhr_head_bind_gate.py in-process',
    },
    'uv':{'name':uv_layer.name,'loops':int(len(uv_layer.data)),'triangle_uv_shape':list(tri_uvs.shape)},
    'face_partition_counts':counts,
    'materials':list(materials.keys()),
    'skin_features':['macro color variation','roughness variation','micro pore bump','subsurface scattering','IOR/specular control','coat secondary lobe'],
    'eye_features':['sclera micro surface','iris color/micro bump','black pupil','separate transmissive cornea IOR 1.376'],
    'render_engine':'BLENDER_EEVEE',
    'research_asset_policy':{
        'FFHQ_UV_Intrinsics':'REJECT_FORMAL_ROUTE_CC_BY_NC_ND',
        '3DTextures_Human_Skin_001_002':'KEEP_CC0_CANDIDATE_NOT_IMPORTED_IN_THIS_GATE',
        'Pixar_RenderMan_Skin_Presets':'KEEP_SHADER_REFERENCE_NOT_DIRECT_RUNTIME_DEPENDENCY',
    },
    'portability_note':'Procedural Blender shader nodes are an offline appearance pipeline gate. They are not claimed to export losslessly to glTF/WebGL. Texture baking / Web shader parity is the next gate.',
    'final_cinematic_asset_claim':False,
    'gate_claim':'PBR/SSS/micro-surface/complete layered-eye look-dev pipeline on the verified rigged GNM head; not final 4K/8K identity texture, tearline, hair, wrinkles, or production neck merge.',
}
(APP_OUT/'gnm_mhr_appearance_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
print(json.dumps(metrics,indent=2))
