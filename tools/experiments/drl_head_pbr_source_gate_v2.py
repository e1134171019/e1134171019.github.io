import bpy, json, os
from pathlib import Path
import numpy as np
from mathutils import Vector

OBJ=Path(os.environ['DRL_OBJ']); DIFF=Path(os.environ['DRL_DIFFUSE']); NORMAL=Path(os.environ['DRL_NORMAL']); GLOSS=Path(os.environ['DRL_GLOSS']); SPEC=Path(os.environ['DRL_SPECULAR'])
OUT=Path('artifacts/drl-head-pbr-source-gate-v2'); OUT.mkdir(parents=True,exist_ok=True)
for p in [OBJ,DIFF,NORMAL,GLOSS,SPEC]:
    if not p.is_file() or p.stat().st_size<=0: raise RuntimeError(f'missing source {p}')

bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
try: bpy.ops.wm.obj_import(filepath=str(OBJ.resolve()))
except Exception: bpy.ops.import_scene.obj(filepath=str(OBJ.resolve()))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes: raise RuntimeError('OBJ import yielded no mesh')

# DRL OBJ is authored in centimeter-scale units (~37 units tall). Normalize to meters for physically sensible lighting.
SOURCE_TO_METERS=0.01
for o in meshes:
    o.scale=(SOURCE_TO_METERS,)*3
    for p in o.data.polygons: p.use_smooth=True
head=max(meshes,key=lambda o:len(o.data.polygons)); head.name='DRL_Marcus_Head_Source_v2'

def img_node(nt,tex,path,name,loc,noncolor=False):
    img=bpy.data.images.load(str(path.resolve()),check_existing=False)
    if noncolor: img.colorspace_settings.name='Non-Color'
    n=nt.nodes.new('ShaderNodeTexImage'); n.name=name; n.image=img; n.location=loc; n.interpolation='Linear'; nt.links.new(tex.outputs['UV'],n.inputs['Vector'])
    return n,img

def input_socket(bsdf,*names):
    for n in names:
        if bsdf.inputs.get(n) is not None: return bsdf.inputs[n]
    return None

mat=bpy.data.materials.new('DRL_Marcus_RealPBR_v2'); mat.use_nodes=True; nt=mat.node_tree; nt.nodes.clear()
out=nt.nodes.new('ShaderNodeOutputMaterial'); out.location=(760,0)
bsdf=nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location=(500,0)
bsdf.inputs['Roughness'].default_value=0.42
if input_socket(bsdf,'Subsurface Weight','Subsurface'): input_socket(bsdf,'Subsurface Weight','Subsurface').default_value=0.055
if input_socket(bsdf,'Subsurface Radius'): input_socket(bsdf,'Subsurface Radius').default_value=(1.0,0.42,0.24)
if input_socket(bsdf,'IOR'): input_socket(bsdf,'IOR').default_value=1.43
tex=nt.nodes.new('ShaderNodeTexCoord'); tex.location=(-1050,0)
diff,diff_img=img_node(nt,tex,DIFF,'Real_Diffuse',(-820,250),False)
norm,norm_img=img_node(nt,tex,NORMAL,'Real_Normal',(-820,25),True)
gloss,gloss_img=img_node(nt,tex,GLOSS,'Real_Glossiness',(-820,-210),True)
spec,spec_img=img_node(nt,tex,SPEC,'Real_Specular',(-820,-425),True)
nt.links.new(diff.outputs['Color'],bsdf.inputs['Base Color'])
nm=nt.nodes.new('ShaderNodeNormalMap'); nm.location=(170,-15); nm.inputs['Strength'].default_value=0.72; nt.links.new(norm.outputs['Color'],nm.inputs['Color']); nt.links.new(nm.outputs['Normal'],bsdf.inputs['Normal'])
inv=nt.nodes.new('ShaderNodeMath'); inv.operation='SUBTRACT'; inv.location=(-270,-210); inv.inputs[0].default_value=1.0; nt.links.new(gloss.outputs['Color'],inv.inputs[1])
mapr=nt.nodes.new('ShaderNodeMapRange'); mapr.location=(20,-210); mapr.inputs['From Min'].default_value=0; mapr.inputs['From Max'].default_value=1; mapr.inputs['To Min'].default_value=0.20; mapr.inputs['To Max'].default_value=0.62; mapr.clamp=True; nt.links.new(inv.outputs[0],mapr.inputs['Value']); nt.links.new(mapr.outputs['Result'],bsdf.inputs['Roughness'])
sps=input_socket(bsdf,'IOR Level','Specular IOR Level')
if sps:
    mult=nt.nodes.new('ShaderNodeMath'); mult.operation='MULTIPLY'; mult.location=(170,-410); mult.inputs[1].default_value=0.8; nt.links.new(spec.outputs['Color'],mult.inputs[0]); nt.links.new(mult.outputs[0],sps)
nt.links.new(bsdf.outputs['BSDF'],out.inputs['Surface']); head.data.materials.clear(); head.data.materials.append(mat)

# Neutral material only for any auxiliary mesh pieces. Never fabricate identity detail on them.
def neutral(name,color,rough):
    m=bpy.data.materials.new(name); m.use_nodes=True; b=m.node_tree.nodes.get('Principled BSDF'); b.inputs['Base Color'].default_value=color; b.inputs['Roughness'].default_value=rough; return m
for o in meshes:
    if o==head: continue
    o.data.materials.clear(); o.data.materials.append(neutral('DRL_Aux_'+o.name,(0.12,0.12,0.12,1),0.35))

pts=np.asarray([(o.matrix_world@v.co)[:] for o in meshes for v in o.data.vertices],dtype=np.float64); vmin,vmax=pts.min(0),pts.max(0); center=(vmin+vmax)/2; extent=vmax-vmin
hp=np.asarray([(head.matrix_world@v.co)[:] for v in head.data.vertices],dtype=np.float64); hmin,hmax=hp.min(0),hp.max(0); hcenter=(hmin+hmax)/2; hext=hmax-hmin; hscale=float(max(hext))
if not (0.25 <= hscale <= 0.50): raise RuntimeError(f'normalized DRL head scale implausible: {hscale} m')

scene=bpy.context.scene; scene.render.engine='BLENDER_EEVEE'; scene.render.resolution_x=920; scene.render.resolution_y=920; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'; scene.world.color=(0.025,0.028,0.034); scene.view_settings.exposure=0.45

def area(name,direction,energy,size,color):
    ld=bpy.data.lights.new(name,type='AREA'); ld.energy=energy; ld.shape='DISK'; ld.size=size; ld.color=color
    ob=bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(ob); ob.location=Vector(hcenter)+Vector(direction).normalized()*hscale*1.65; ob.rotation_euler=(Vector(hcenter)-ob.location).to_track_quat('-Z','Y').to_euler(); return ob
area('Key',(1.2,-1.45,0.8),780,hscale*0.72,(1.0,0.82,0.72)); area('Fill',(-1.15,-0.8,0.25),210,hscale*0.90,(0.70,0.80,1.0)); area('Rim',(0.25,1.25,0.8),430,hscale*0.58,(0.78,0.88,1.0))
camd=bpy.data.cameras.new('DRLSourceCamera_v2'); cam=bpy.data.objects.new('DRLSourceCamera_v2',camd); bpy.context.collection.objects.link(cam); scene.camera=cam; cam.data.type='ORTHO'

def render(name,axis,ortho=1.14):
    axis=Vector(axis).normalized(); cam.location=Vector(hcenter)+axis*hscale*2.25; cam.rotation_euler=(Vector(hcenter)-cam.location).to_track_quat('-Z','Y').to_euler(); cam.data.ortho_scale=hscale*ortho; scene.render.filepath=str((OUT/name).resolve()); bpy.ops.render.render(write_still=True)

views={'neg_y':(0,-1,0),'pos_y':(0,1,0),'pos_x':(1,0,0),'neg_x':(-1,0,0),'pos_z':(0,0,1),'neg_z':(0,0,-1)}
for tag,axis in views.items(): render('source_'+tag+'.png',axis,1.16)
for i,axis in enumerate([(0.66,-1,0),(0.66,1,0),(-0.66,-1,0),(-0.66,1,0)]): render(f'diagonal_{i}.png',axis,0.88)

metrics={'source':'Digital Reality Lab Head PBR Scan Sample / Marcus','source_to_meters':SOURCE_TO_METERS,'mesh_objects':[{'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons),'uv_layers':[u.name for u in o.data.uv_layers]} for o in meshes],'head_object':head.name,'head_bbox_m':{'min':hmin.tolist(),'max':hmax.tolist(),'extent':hext.tolist()},'render_maps':{'diffuse':{'size':list(diff_img.size)},'normal':{'size':list(norm_img.size)},'glossiness':{'size':list(gloss_img.size)},'specular':{'size':list(spec_img.size)}},'rendered_source_stack':['diffuse','normal','glossiness','specular'],'confirmed_archive_map_not_rendered':['Marcus_38_Displace.exr'],'redistribution_policy':'No original DRL mesh or source textures are copied into the workflow artifact.','gate_claim':'Exposure-corrected real DRL source PBR visual quality gate before GNM transfer.','not_claimed':['GNM texture transfer','final cinematic master adoption','browser runtime parity']}
(OUT/'drl_head_pbr_source_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8'); print(json.dumps(metrics,indent=2))
