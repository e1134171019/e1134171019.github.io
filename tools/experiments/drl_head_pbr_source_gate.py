import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Vector

OBJ=Path(os.environ['DRL_OBJ'])
DIFF=Path(os.environ['DRL_DIFFUSE'])
NORMAL=Path(os.environ['DRL_NORMAL'])
GLOSS=Path(os.environ['DRL_GLOSS'])
SPEC=Path(os.environ['DRL_SPECULAR'])
OUT=Path('artifacts/drl-head-pbr-source-gate')
OUT.mkdir(parents=True,exist_ok=True)

for p in [OBJ,DIFF,NORMAL,GLOSS,SPEC]:
    if not p.is_file() or p.stat().st_size<=0:
        raise RuntimeError(f'Missing DRL source input: {p}')

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.wm.obj_import(filepath=str(OBJ.resolve()))
except Exception:
    bpy.ops.import_scene.obj(filepath=str(OBJ.resolve()))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:
    raise RuntimeError('DRL OBJ import produced no mesh objects')

# Largest surface is the head/skin carrier. Keep any separate eye/hair pieces intact for source review.
head=max(meshes,key=lambda o:len(o.data.polygons))
head.name='DRL_Marcus_Head_Source'
for o in meshes:
    for p in o.data.polygons:
        p.use_smooth=True

# Build a physically-based diagnostic material from REAL scan maps.
mat=bpy.data.materials.new('DRL_Marcus_RealPBR')
mat.use_nodes=True
nt=mat.node_tree
nt.nodes.clear()
out=nt.nodes.new('ShaderNodeOutputMaterial'); out.location=(780,0)
bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location=(500,0)

def set_input(names,val):
    for n in names:
        s=bsdf.inputs.get(n)
        if s is not None:
            s.default_value=val
            return n
    return None
set_input(['Roughness'],0.43)
set_input(['Subsurface Weight','Subsurface'],0.08)
set_input(['IOR'],1.43)
set_input(['IOR Level','Specular IOR Level'],0.32)
tex=nt.nodes.new('ShaderNodeTexCoord'); tex.location=(-1050,0)

def image_node(path,name,loc,noncolor=False):
    img=bpy.data.images.load(str(path.resolve()),check_existing=False)
    if noncolor:
        img.colorspace_settings.name='Non-Color'
    n=nt.nodes.new('ShaderNodeTexImage'); n.name=name; n.image=img; n.location=loc; n.interpolation='Linear'
    nt.links.new(tex.outputs['UV'],n.inputs['Vector'])
    return n,img

diff_n,diff_img=image_node(DIFF,'Real_Diffuse',(-800,250),False)
normal_n,normal_img=image_node(NORMAL,'Real_Normal',(-800,20),True)
gloss_n,gloss_img=image_node(GLOSS,'Real_Glossiness',(-800,-220),True)
spec_n,spec_img=image_node(SPEC,'Real_Specular',(-800,-430),True)
nt.links.new(diff_n.outputs['Color'],bsdf.inputs['Base Color'])

nmap=nt.nodes.new('ShaderNodeNormalMap'); nmap.location=(190,-30); nmap.inputs['Strength'].default_value=0.78
nt.links.new(normal_n.outputs['Color'],nmap.inputs['Color'])
nt.links.new(nmap.outputs['Normal'],bsdf.inputs['Normal'])

# Source is glossiness; invert to roughness. Clamp through Map Range for a stable look-dev range.
inv=nt.nodes.new('ShaderNodeMath'); inv.operation='SUBTRACT'; inv.location=(-270,-210); inv.inputs[0].default_value=1.0
nt.links.new(gloss_n.outputs['Color'],inv.inputs[1])
mapr=nt.nodes.new('ShaderNodeMapRange'); mapr.location=(40,-210)
mapr.inputs['From Min'].default_value=0.0; mapr.inputs['From Max'].default_value=1.0
mapr.inputs['To Min'].default_value=0.24; mapr.inputs['To Max'].default_value=0.66
mapr.clamp=True
nt.links.new(inv.outputs[0],mapr.inputs['Value'])
nt.links.new(mapr.outputs['Result'],bsdf.inputs['Roughness'])

# Specular intensity drives IOR-level/specular-level when available.
spec_socket=bsdf.inputs.get('IOR Level') or bsdf.inputs.get('Specular IOR Level')
if spec_socket is not None:
    mult=nt.nodes.new('ShaderNodeMath'); mult.operation='MULTIPLY'; mult.location=(160,-410); mult.inputs[1].default_value=0.68
    nt.links.new(spec_n.outputs['Color'],mult.inputs[0]); nt.links.new(mult.outputs[0],spec_socket)
nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])

head.data.materials.clear(); head.data.materials.append(mat)

# Separate pieces get neutral diagnostic materials rather than fake scan maps.
def simple(name,color,rough,metal=0.0):
    m=bpy.data.materials.new(name); m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value=color; b.inputs['Roughness'].default_value=rough
    if b.inputs.get('Metallic'): b.inputs['Metallic'].default_value=metal
    return m
neutral_eye=simple('DRL_Source_Eye_Neutral',(0.35,0.38,0.39,1),0.16)
neutral_dark=simple('DRL_Source_Aux_Dark',(0.012,0.008,0.006,1),0.5)
for o in meshes:
    if o==head: continue
    n=o.name.lower()
    o.data.materials.clear()
    o.data.materials.append(neutral_eye if any(k in n for k in ('eye','iris','sclera','cornea')) else neutral_dark)

# Combined bounds and head metrics.
all_world=[]
for o in meshes:
    all_world.extend([(o.matrix_world@v.co)[:] for v in o.data.vertices])
pts=np.asarray(all_world,dtype=np.float64)
vmin,vmax=pts.min(0),pts.max(0); center=(vmin+vmax)/2; extent=vmax-vmin; scale=float(max(extent))
head_pts=np.asarray([(head.matrix_world@v.co)[:] for v in head.data.vertices],dtype=np.float64)
hmin,hmax=head_pts.min(0),head_pts.max(0); hcenter=(hmin+hmax)/2; hext=hmax-hmin; hscale=float(max(hext))

scene=bpy.context.scene
scene.render.engine='BLENDER_EEVEE'
scene.render.resolution_x=920; scene.render.resolution_y=920; scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.world.color=(0.007,0.009,0.013)
scene.view_settings.exposure=-0.65

# Studio lighting.
def add_area(name,direction,energy,size,color):
    ld=bpy.data.lights.new(name,type='AREA'); ld.energy=energy; ld.shape='DISK'; ld.size=size; ld.color=color
    ob=bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(ob)
    ob.location=Vector(hcenter)+Vector(direction).normalized()*hscale*2.0
    ob.rotation_euler=(Vector(hcenter)-ob.location).to_track_quat('-Z','Y').to_euler()
    return ob
add_area('Key',(1.25,-1.45,0.85),62,hscale*0.62,(1.0,0.82,0.72))
add_area('Fill',(-1.15,-0.75,0.25),19,hscale*0.8,(0.68,0.78,1.0))
add_area('Rim',(0.25,1.3,0.75),34,hscale*0.52,(0.76,0.87,1.0))
camd=bpy.data.cameras.new('DRLSourceCamera'); cam=bpy.data.objects.new('DRLSourceCamera',camd); bpy.context.collection.objects.link(cam); scene.camera=cam; cam.data.type='ORTHO'

def render(name,axis,target,ortho):
    axis=Vector(axis).normalized(); target=Vector(target)
    cam.location=target+axis*hscale*2.4
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.ortho_scale=ortho
    scene.render.filepath=str((OUT/name).resolve())
    bpy.ops.render.render(write_still=True)

views={'neg_y':(0,-1,0),'pos_y':(0,1,0),'pos_x':(1,0,0),'neg_x':(-1,0,0),'pos_z':(0,0,1),'neg_z':(0,0,-1)}
for tag,axis in views.items(): render(f'source_{tag}.png',axis,hcenter,hscale*1.18)
# Diagonal closeups for surface response, without assuming which principal direction is front.
for i,axis in enumerate([(0.66,-1,0),(0.66,1,0),(-0.66,-1,0),(-0.66,1,0)]):
    render(f'diagonal_{i}.png',axis,hcenter,hscale*0.88)

metrics={
    'source':'Digital Reality Lab Head PBR Scan Sample / Marcus',
    'mesh_objects':[{'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),'uv_layers':[u.name for u in o.data.uv_layers]} for o in meshes],
    'head_object':head.name,
    'head_bbox':{'min':hmin.tolist(),'max':hmax.tolist(),'extent':hext.tolist()},
    'combined_bbox':{'min':vmin.tolist(),'max':vmax.tolist(),'extent':extent.tolist()},
    'render_maps':{
        'diffuse':{'file':DIFF.name,'size':list(diff_img.size),'bytes':DIFF.stat().st_size},
        'normal':{'file':NORMAL.name,'size':list(normal_img.size),'bytes':NORMAL.stat().st_size},
        'glossiness':{'file':GLOSS.name,'size':list(gloss_img.size),'bytes':GLOSS.stat().st_size},
        'specular':{'file':SPEC.name,'size':list(spec_img.size),'bytes':SPEC.stat().st_size},
    },
    'source_archive_maps_not_rendered_in_this_gate':['Marcus_38_Displace.exr'],
    'gate_claim':'Visual source-quality verification using the real DRL scan diffuse/normal/glossiness/specular stack before any GNM projection or baking.',
    'redistribution_policy':'No original DRL mesh or source textures are copied into the workflow artifact.',
    'not_claimed':['GNM texture transfer','final cinematic master adoption','browser runtime parity'],
}
(OUT/'drl_head_pbr_source_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
print(json.dumps(metrics,indent=2))
