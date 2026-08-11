import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

GNM_MODEL=Path(os.environ.get('GNM_MODEL','/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz'))
DRL_OBJ=Path(os.environ['DRL_OBJ'])
OUT=Path('artifacts/drl-gnm-alignment-gate'); OUT.mkdir(parents=True,exist_ok=True)

if not GNM_MODEL.is_file() or not DRL_OBJ.is_file():
    raise RuntimeError('GNM/DRL source missing')

# ------------------------- GNM semantic target -------------------------
with np.load(GNM_MODEL,allow_pickle=False) as d:
    gv=np.asarray(d['template_vertex_positions'],dtype=np.float64)
    gt=np.asarray(d['triangles'],dtype=np.int64)
    vg=np.asarray(d['vertex_groups'],dtype=np.float64)
    vg_names=[str(x) for x in d['vertex_group_names']]
idx={n:i for i,n in enumerate(vg_names)}
if 'skin' not in idx: raise RuntimeError('GNM skin semantic group missing')
gskin=vg[idx['skin']]>0.5
# GNM native: +Z front, +Y up, +X right. Canonical donor frame: -Y front, +Z up, +X right.
G=np.stack([gv[:,0],-gv[:,2],gv[:,1]],axis=1)
Gskin=G[gskin]
gmin,gmax=Gskin.min(0),Gskin.max(0); gc=(gmin+gmax)/2; ge=gmax-gmin
if np.any(ge<=0): raise RuntimeError(f'GNM canonical extent invalid: {ge}')

# Semantic face ROI: remove bust/back-scalp dominance so ICP is driven by face geometry.
gn=(Gskin-gmin)/ge
face_roi=(np.abs(gn[:,0]-0.5)<=0.45) & (gn[:,2]>=0.30) & (gn[:,2]<=0.96) & (gn[:,1]<=0.58)
Gface=Gskin[face_roi]
if len(Gface)<1500: raise RuntimeError(f'GNM face ROI too small: {len(Gface)}')

# ------------------------- DRL source geometry -------------------------
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
try: bpy.ops.wm.obj_import(filepath=str(DRL_OBJ.resolve()))
except Exception: bpy.ops.import_scene.obj(filepath=str(DRL_OBJ.resolve()))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes: raise RuntimeError('DRL OBJ import produced no mesh')
drl=max(meshes,key=lambda o:len(o.data.polygons)); drl.name='DRL_Donor_Aligned'
# DRL archive is authored in centimeters. Convert local points to meters numerically; object stays identity.
D=np.asarray([tuple(v.co) for v in drl.data.vertices],dtype=np.float64)*0.01
dmin,dmax=D.min(0),D.max(0); dc=(dmin+dmax)/2; de=dmax-dmin

# Uniform bbox initialization. Both sources are neutral bust/head carriers, but retain only a uniform scale.
valid=de>1e-8
scale0=float(np.median(ge[valid]/de[valid]))
if not 0.55<=scale0<=1.65: raise RuntimeError(f'Implausible initial DRL->GNM scale: {scale0}')
R=np.eye(3,dtype=np.float64)*scale0
t=gc-R@dc
D0=(D@R.T)+t

# Select DRL vertices that initially land inside the same facial envelope used by GNM.
dn=(D0-gmin)/ge
Dface_mask=(np.abs(dn[:,0]-0.5)<=0.48) & (dn[:,2]>=0.27) & (dn[:,2]<=0.98) & (dn[:,1]<=0.62)
Dface_local=D[Dface_mask]
if len(Dface_local)<2500: raise RuntimeError(f'DRL face ROI too small after init: {len(Dface_local)}')
# Deterministic sampling keeps ICP CPU-cheap while preserving surface coverage.
step=max(1,len(Dface_local)//7000)
Dsample=Dface_local[::step][:7000]

# KD target from GNM semantic face points.
kd=KDTree(len(Gface))
for i,p in enumerate(Gface): kd.insert(tuple(p),i)
kd.balance()

def rigid_fit(A,B):
    ma=A.mean(0); mb=B.mean(0)
    X=A-ma; Y=B-mb
    U,S,Vt=np.linalg.svd(X.T@Y)
    Q=Vt.T@U.T
    if np.linalg.det(Q)<0:
        Vt[-1,:]*=-1
        Q=Vt.T@U.T
    q=mb-Q@ma
    return Q,q

history=[]
prev=None
for it in range(18):
    cur=(Dsample@R.T)+t
    matches=np.empty_like(cur); dist=np.empty(len(cur),dtype=np.float64)
    for i,p in enumerate(cur):
        co,idx0,d=kd.find(tuple(p)); matches[i]=co; dist[i]=d
    cutoff=min(float(np.percentile(dist,72)),0.035)
    keep=dist<=cutoff
    if int(keep.sum())<900: raise RuntimeError(f'ICP inliers collapsed at iter {it}: {keep.sum()} cutoff={cutoff}')
    Q,q=rigid_fit(cur[keep],matches[keep])
    R=Q@R; t=Q@t+q
    rms=float(np.sqrt(np.mean(dist[keep]**2)))
    history.append({'iteration':it,'inliers':int(keep.sum()),'cutoff_mm':cutoff*1000,'rms_mm':rms*1000})
    if prev is not None and abs(prev-rms)<1e-5: break
    prev=rms

Dfit=(D@R.T)+t
Dface_fit=(Dface_local@R.T)+t

# Bidirectional nearest-vertex surface proxy metrics on the facial ROI.
def nearest_stats(query,reference,max_samples=9000):
    rstep=max(1,len(reference)//max_samples); ref=reference[::rstep][:max_samples]
    tree=KDTree(len(ref))
    for i,p in enumerate(ref): tree.insert(tuple(p),i)
    tree.balance()
    qstep=max(1,len(query)//max_samples); qs=query[::qstep][:max_samples]
    ds=[]
    for p in qs: ds.append(tree.find(tuple(p))[2])
    a=np.asarray(ds,dtype=np.float64)
    return {'samples':int(len(a)),'median_mm':float(np.median(a)*1000),'p90_mm':float(np.percentile(a,90)*1000),'p95_mm':float(np.percentile(a,95)*1000),'mean_mm':float(a.mean()*1000),'max_mm':float(a.max()*1000)}

drl_to_gnm=nearest_stats(Dface_fit,Gface)
gnm_to_drl=nearest_stats(Gface,Dface_fit)

# ------------------------- Blender overlay review -------------------------
# Replace imported DRL local coordinates with fitted canonical-meter points.
for v,p in zip(drl.data.vertices,Dfit): v.co=tuple(p)
for p in drl.data.polygons: p.use_smooth=True

# GNM target skin surface only.
skin_faces=gt[np.asarray(gskin[gt].any(axis=1),dtype=bool)]
gmesh=bpy.data.meshes.new('GNM_Target_Skin_Mesh'); gmesh.from_pydata(G.tolist(),[],skin_faces.tolist()); gmesh.update()
gobj=bpy.data.objects.new('GNM_Target_Skin',gmesh); bpy.context.collection.objects.link(gobj)
for p in gobj.data.polygons: p.use_smooth=True

# Materials: donor opaque neutral; target as cyan wireframe overlay to expose local misfit.
def pmat(name,color,rough=0.5):
    m=bpy.data.materials.new(name); m.use_nodes=True; b=m.node_tree.nodes.get('Principled BSDF'); b.inputs['Base Color'].default_value=color; b.inputs['Roughness'].default_value=rough; return m
drl.data.materials.clear(); drl.data.materials.append(pmat('DRL_Donor',(0.42,0.17,0.08,1),0.62))
gobj.data.materials.clear(); gobj.data.materials.append(pmat('GNM_Target_Wire',(0.02,0.42,0.65,1),0.42))
wire=gobj.modifiers.new('GNM_Target_Wireframe','WIREFRAME'); wire.thickness=max(ge)*0.0014; wire.use_replace=True

# Hide any small auxiliary DRL import objects to prevent confusing overlays.
for o in meshes:
    if o!=drl: o.hide_render=True

scene=bpy.context.scene; scene.render.engine='BLENDER_EEVEE'; scene.render.resolution_x=900; scene.render.resolution_y=900; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='PNG'; scene.world.color=(0.010,0.012,0.016); scene.view_settings.exposure=-0.7
cc=(gmin+gmax)/2; span=float(max(ge))
for name,direction,energy,size in [('Key',(1.1,-1.4,0.8),35,span*0.55),('Fill',(-1,-0.7,0.2),12,span*0.7),('Rim',(0,1.2,0.7),18,span*0.5)]:
    ld=bpy.data.lights.new(name,type='AREA'); ld.energy=energy; ld.size=size
    lo=bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(lo); lo.location=Vector(cc)+Vector(direction).normalized()*span*2.0; lo.rotation_euler=(Vector(cc)-lo.location).to_track_quat('-Z','Y').to_euler()
camd=bpy.data.cameras.new('AlignmentCamera'); cam=bpy.data.objects.new('AlignmentCamera',camd); bpy.context.collection.objects.link(cam); scene.camera=cam; cam.data.type='ORTHO'

def render(name,axis,scale=1.08):
    axis=Vector(axis).normalized(); cam.location=Vector(cc)+axis*span*2.5; cam.rotation_euler=(Vector(cc)-cam.location).to_track_quat('-Z','Y').to_euler(); cam.data.ortho_scale=span*scale; scene.render.filepath=str((OUT/name).resolve()); bpy.ops.render.render(write_still=True)
for name,axis in [('front',(0,-1,0)),('three_quarter',(0.55,-1,0)),('side',(1,0,0)),('back',(0,1,0))]: render(f'overlay_{name}.png',axis)
# Face closeups magnify eye/nose/mouth alignment.
face_center=Gface.mean(0); face_span=float(max(Gface.max(0)-Gface.min(0)))
for name,axis in [('front',(0,-1,0)),('three_quarter',(0.55,-1,0))]:
    axis=Vector(axis).normalized(); cam.location=Vector(face_center)+axis*span*2.1; cam.rotation_euler=(Vector(face_center)-cam.location).to_track_quat('-Z','Y').to_euler(); cam.data.ortho_scale=face_span*1.10; scene.render.filepath=str((OUT/f'face_overlay_{name}.png').resolve()); bpy.ops.render.render(write_still=True)

metrics={
    'sources':{'GNM':{'commit':'98450b3c943101d5859ac1ceb7331ec918ebc321'},'DRL':{'asset':'Marcus_PBR_Sample_01.obj','source_units':'centimeters','source_to_meters':0.01}},
    'coordinate_map':'GNM native (x,y,z) -> canonical (x,-z,y); canonical front=-Y, up=+Z',
    'gnm':{'skin_vertices':int(gskin.sum()),'face_roi_vertices':int(len(Gface)),'bbox_min':gmin.tolist(),'bbox_max':gmax.tolist(),'extent':ge.tolist()},
    'drl':{'vertices':int(len(D)),'face_roi_vertices':int(len(Dface_local)),'initial_bbox_extent_m':de.tolist()},
    'initial_uniform_scale':scale0,
    'final_linear_transform':R.tolist(),
    'final_translation_m':t.tolist(),
    'icp_history':history,
    'drl_to_gnm_face':drl_to_gnm,
    'gnm_to_drl_face':gnm_to_drl,
    'gate_thresholds':{'median_mm_max':15.0,'p90_mm_max':30.0},
    'gate_claim':'Rigid geometry alignment feasibility only. No texture baking, identity replacement, final asset adoption, or source redistribution.',
}
pass_numeric=(drl_to_gnm['median_mm']<=15 and drl_to_gnm['p90_mm']<=30 and gnm_to_drl['median_mm']<=15 and gnm_to_drl['p90_mm']<=30)
metrics['numeric_gate_pass']=bool(pass_numeric)
(OUT/'drl_gnm_alignment_metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
if not pass_numeric: raise RuntimeError(f'DRL->GNM alignment numeric gate failed: {json.dumps(metrics,indent=2)}')
print(json.dumps(metrics,indent=2))
