import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Vector

OBJ=Path(os.environ.get('TEN24_OBJ','/tmp/ten24/Ten24_Sample_100k.OBJ'))
COLOR=Path(os.environ.get('TEN24_COLOR','/tmp/ten24/Colour_8k.jpg'))
NORMAL=Path(os.environ.get('TEN24_NORMAL','/tmp/ten24/Level_01_Normal.PSD'))
OUT=Path('artifacts/ten24-source-visual-gate')
OUT.mkdir(parents=True,exist_ok=True)

for p in [OBJ,COLOR,NORMAL]:
    if not p.is_file() or p.stat().st_size==0:
        raise RuntimeError(f'Missing Ten24 source file: {p}')

bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
try:
    bpy.ops.wm.obj_import(filepath=str(OBJ.resolve()))
except Exception:
    bpy.ops.import_scene.obj(filepath=str(OBJ.resolve()))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes: raise RuntimeError('Ten24 OBJ import yielded no mesh')
# Join imported mesh parts only for this source diagnostic.
bpy.ops.object.select_all(action='DESELECT')
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active=max(meshes,key=lambda o:len(o.data.vertices))
if len(meshes)>1: bpy.ops.object.join()
obj=bpy.context.view_layer.objects.active
obj.name='Ten24_Sample_100k_Source'
for p in obj.data.polygons: p.use_smooth=True

# Physical-ish skin source material: identity comes from the real 8K scan color and source normal.
mat=bpy.data.materials.new('Ten24_Source_Skin'); mat.use_nodes=True
nt=mat.node_tree; nt.nodes.clear()
out=nt.nodes.new('ShaderNodeOutputMaterial'); out.location=(700,0)
bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location=(430,0)
for name,val in [('Roughness',0.46),('IOR',1.43)]:
    if bsdf.inputs.get(name): bsdf.inputs[name].default_value=val
for name,val in [('Subsurface Weight',0.085),('Subsurface',0.085),('IOR Level',0.32),('Specular IOR Level',0.32)]:
    if bsdf.inputs.get(name): bsdf.inputs[name].default_value=val
texcoord=nt.nodes.new('ShaderNodeTexCoord'); texcoord.location=(-900,0)
color_img=bpy.data.images.load(str(COLOR.resolve()),check_existing=False)
color_node=nt.nodes.new('ShaderNodeTexImage'); color_node.image=color_img; color_node.location=(-650,120); color_node.interpolation='Linear'
nt.links.new(texcoord.outputs['UV'],color_node.inputs['Vector']); nt.links.new(color_node.outputs['Color'],bsdf.inputs['Base Color'])
normal_img=bpy.data.images.load(str(NORMAL.resolve()),check_existing=False)
normal_img.colorspace_settings.name='Non-Color'
normal_node=nt.nodes.new('ShaderNodeTexImage'); normal_node.image=normal_img; normal_node.location=(-650,-180); normal_node.interpolation='Linear'
nt.links.new(texcoord.outputs['UV'],normal_node.inputs['Vector'])
nmap=nt.nodes.new('ShaderNodeNormalMap'); nmap.location=(120,-160); nmap.inputs['Strength'].default_value=0.62
nt.links.new(normal_node.outputs['Color'],nmap.inputs['Color']); nt.links.new(nmap.outputs['Normal'],bsdf.inputs['Normal'])
nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface'])
obj.data.materials.clear(); obj.data.materials.append(mat)

# Geometry/image metrics.
verts_world=np.array([(obj.matrix_world@v.co)[:] for v in obj.data.vertices],dtype=np.float64)
vmin,vmax=verts_world.min(0),verts_world.max(0); extent=vmax-vmin; center=(vmin+vmax)/2
vertical_axis=int(np.argmax(extent)); vertical_span=float(extent[vertical_axis])
# Ten24 sample is expected to be a full body. Choose upper extremity candidate for close-up, but preserve six-axis overview to avoid orientation assumptions.
upper=center.copy(); upper[vertical_axis]=vmax[vertical_axis]-0.12*vertical_span
lower=center.copy(); lower[vertical_axis]=vmin[vertical_axis]+0.12*vertical_span

scene=bpy.context.scene; scene.render.engine='BLENDER_EEVEE'; scene.render.resolution_x=900; scene.render.resolution_y=900; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'; scene.world.color=(0.008,0.010,0.014); scene.view_settings.exposure=-0.75
maxe=float(max(extent))
for name,direction,energy,size,color in [
    ('Key',(1.3,-1.5,1.0),70,maxe*0.26,(1.0,0.80,0.70)),
    ('Fill',(-1.2,-0.8,0.3),25,maxe*0.34,(0.68,0.78,1.0)),
    ('Rim',(0.2,1.3,1.0),40,maxe*0.24,(0.76,0.86,1.0)),
]:
    ld=bpy.data.lights.new(name,type='AREA'); ld.energy=energy; ld.size=size; ld.color=color
    lo=bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(lo); lo.location=Vector(center)+Vector(direction).normalized()*maxe*1.5; lo.rotation_euler=(Vector(center)-lo.location).to_track_quat('-Z','Y').to_euler()
camd=bpy.data.cameras.new('Ten24GateCamera'); cam=bpy.data.objects.new('Ten24GateCamera',camd); bpy.context.collection.objects.link(cam); scene.camera=cam; cam.data.type='ORTHO'

def render(name,axis,target,scale):
    axis=Vector(axis).normalized(); target=Vector(target); cam.location=target+axis*maxe*2.0; cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler(); cam.data.ortho_scale=scale; scene.render.filepath=str((OUT/name).resolve()); bpy.ops.render.render(write_still=True)

# Six principal axis views establish actual orientation without guessing.
views={'neg_y':(0,-1,0),'pos_y':(0,1,0),'pos_x':(1,0,0),'neg_x':(-1,0,0),'pos_z':(0,0,1),'neg_z':(0,0,-1)}
for name,axis in views.items(): render(f'source_{name}.png',axis,center,maxe*1.08)
# Upper/lower extremity close-ups help identify which end is the head if source axis conventions differ.
for tag,target in [('upper',upper),('lower',lower)]:
    for name,axis in [('neg_y',(0,-1,0)),('threeq',(0.65,-1,0))]: render(f'{tag}_{name}.png',axis,target,maxe*0.28)

# Export a compact source diagnostic GLB with only the 100k mesh. Texture embedding may increase size but proves UV/material loading.
bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active=obj
bpy.ops.export_scene.gltf(filepath=str((OUT/'ten24_source_100k_diagnostic.glb').resolve()),export_format='GLB',use_selection=True)

metrics={
    'source':'Ten24 Sample Scan OBJ Package',
    'source_url':'https://ten24.info/sample-scan/',
    'mesh':{'vertices':len(obj.data.vertices),'polygons':len(obj.data.polygons),'bbox_min':vmin.tolist(),'bbox_max':vmax.tolist(),'extent':extent.tolist(),'vertical_axis_by_extent':vertical_axis},
    'images':{
        'color':{'path':COLOR.name,'width':color_img.size[0],'height':color_img.size[1],'bytes':COLOR.stat().st_size},
        'normal':{'path':NORMAL.name,'width':normal_img.size[0],'height':normal_img.size[1],'bytes':NORMAL.stat().st_size},
    },
    'uv_layers':[u.name for u in obj.data.uv_layers],
    'gate_claim':'Materialize and visually verify permissively usable Ten24 identity scan source before any GNM texture-transfer attempt.',
    'not_claimed':['GNM texture transfer','final cinematic character adoption','web runtime optimization'],
}
(OUT/'ten24_source_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
print(json.dumps(metrics,indent=2))
