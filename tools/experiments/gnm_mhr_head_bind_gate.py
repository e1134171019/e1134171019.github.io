import bpy
import json
import math
import os
from pathlib import Path

import numpy as np
from mathutils import Matrix, Vector

GNM_MODEL = Path(os.environ.get("GNM_MODEL", "/tmp/GNM/gnm/shape/data/versions/v3_0/gnm_head.npz"))
MHR_FBX = Path(os.environ.get("MHR_FBX", "assets/lod1.fbx"))
OUT = Path("artifacts/gnm-mhr-head-bind-gate")
OUT.mkdir(parents=True, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def umeyama(src, dst):
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    ms, md = src.mean(0), dst.mean(0)
    xs, xd = src-ms, dst-md
    cov = xd.T @ xs / len(src)
    u, s, vt = np.linalg.svd(cov)
    sign = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        sign[-1] = -1
    r = u @ np.diag(sign) @ vt
    scale = float(np.sum(s * sign) / np.mean(np.sum(xs*xs, axis=1)))
    t = md - scale * (r @ ms)
    return scale, r, t


def apply_similarity(points, scale, r, t):
    return (scale * (r @ np.asarray(points, dtype=np.float64).T)).T + t


def make_mat(name, color, roughness):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return m


def create_mesh(name, vertices, triangles):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(np.asarray(vertices).tolist(), [], np.asarray(triangles, dtype=np.int64).tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = True
    return obj


clear_scene()
bpy.ops.import_scene.fbx(filepath=str(MHR_FBX.resolve()), use_anim=False)
arm = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
body = max((o for o in bpy.context.scene.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices), default=None)
if arm is None or body is None:
    raise RuntimeError("MHR armature/body not found")

# Resolve exact MHR target bones.
def rb(*names):
    for n in names:
        b = arm.data.bones.get(n)
        if b is not None:
            return b
    raise RuntimeError(f"Missing MHR bone aliases: {names}")

target_bones = {
    "neck": rb("c_neck", "neck"),
    "head": rb("c_head", "head"),
    "left_eye": rb("l_eye", "l_eye_null", "left_eye"),
    "right_eye": rb("r_eye", "r_eye_null", "right_eye"),
}
target_world = {}
for role,b in target_bones.items():
    p = arm.matrix_world @ b.head_local
    target_world[role] = np.array([p.x,p.y,p.z], dtype=np.float64)

with np.load(GNM_MODEL, allow_pickle=False) as d:
    verts = np.asarray(d["template_vertex_positions"], dtype=np.float64)
    tris = np.asarray(d["triangles"], dtype=np.int64)
    joint_positions_all = np.asarray(d["template_joint_positions"], dtype=np.float64)
    joint_names = [str(x) for x in d["joint_names"]]
    skinning = np.asarray(d["skinning_weights"], dtype=np.float64)
    vg = np.asarray(d["vertex_groups"], dtype=np.float64)
    vg_names = [str(x) for x in d["vertex_group_names"]]

if skinning.shape == (len(verts), len(joint_names)):
    skinning = skinning.T
if skinning.shape != (len(joint_names), len(verts)):
    raise RuntimeError(f"Unexpected GNM skinning shape {skinning.shape}, joints={len(joint_names)}, verts={len(verts)}")
if not np.isfinite(skinning).all():
    raise RuntimeError("Non-finite GNM skinning weights")
weight_sums = skinning.sum(axis=0)
if np.any(weight_sums <= 1e-8):
    raise RuntimeError("GNM has vertices with zero total skin weight")
skinning = skinning / weight_sums[None,:]

jidx = {n:i for i,n in enumerate(joint_names)}
roles = ["neck","head","left_eye","right_eye"]
if any(r not in jidx for r in roles):
    raise RuntimeError(f"GNM joints unavailable: {joint_names}")
source_joints = np.stack([joint_positions_all[jidx[r]] for r in roles])
target_joints = np.stack([target_world[r] for r in roles])
scale,r,t = umeyama(source_joints,target_joints)
fit_joints = apply_similarity(source_joints,scale,r,t)
fit_resid = np.linalg.norm(fit_joints-target_joints,axis=1)
world_verts = apply_similarity(verts,scale,r,t)

# Convert transformed world coordinates into MHR armature local space.
inv_arm = arm.matrix_world.inverted()
local_verts = []
for p in world_verts:
    q = inv_arm @ Vector(p.tolist())
    local_verts.append((q.x,q.y,q.z))

head_obj = create_mesh("GNM_Head_Bound_To_MHR", local_verts, tris)
head_obj.matrix_world = arm.matrix_world.copy()
head_obj.data.materials.append(make_mat("GNM_Head_Bind_Diagnostic", (0.43,0.20,0.12,1), 0.55))

# Map GNM 4-joint weights directly to the corresponding MHR bones.
role_to_source_index = {r:jidx[r] for r in roles}
for role in roles:
    group = head_obj.vertex_groups.new(name=target_bones[role].name)
    w = skinning[role_to_source_index[role]]
    ids = np.flatnonzero(w > 1e-7)
    # Blender API assigns one weight at a time when values vary.
    for vi in ids.tolist():
        group.add([int(vi)], float(w[vi]), "REPLACE")

modifier = head_obj.modifiers.new(name="MHR_Armature", type="ARMATURE")
modifier.object = arm
head_obj.parent = arm
head_obj.parent_type = "OBJECT"

# Diagnostic eye materials on overlapping semantic masks using face material slots.
vgidx = {n:i for i,n in enumerate(vg_names)}
for req in ["eye_interiors","eye_exteriors","irises","pupils"]:
    if req not in vgidx:
        raise RuntimeError(f"Missing GNM group {req}")

def vmask(name): return vg[vgidx[name]] > 0.5
def fany(name): return vmask(name)[tris].any(axis=1)
eye = fany("eye_interiors")
iris = eye & fany("irises")
pupil = eye & fany("pupils")
sclera = eye & ~iris
iris = iris & ~pupil
cornea = fany("eye_exteriors")
materials = [
    head_obj.data.materials[0],
    make_mat("GNM_Sclera_Bind", (0.72,0.69,0.63,1), 0.35),
    make_mat("GNM_Iris_Bind", (0.03,0.27,0.12,1), 0.24),
    make_mat("GNM_Pupil_Bind", (0.002,0.002,0.002,1), 0.18),
    make_mat("GNM_Cornea_Bind", (0.07,0.24,0.42,1), 0.08),
]
for m in materials[1:]: head_obj.data.materials.append(m)
for pi,poly in enumerate(head_obj.data.polygons):
    if pupil[pi]: poly.material_index=3
    elif iris[pi]: poly.material_index=2
    elif sclera[pi]: poly.material_index=1
    elif cornea[pi]: poly.material_index=4

# Hide imported native MHR head visually by making a cropped static body diagnostic copy.
body_world = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices],dtype=np.float64)
body_faces = np.array([list(p.vertices) for p in body.data.polygons],dtype=np.int64)
head_z = float(target_world["head"][2]); neck_z = float(target_world["neck"][2])
centers = body_world[body_faces].mean(axis=1)
keep = centers[:,2] <= head_z + 0.008
# Convert crop world to armature local only for visual reference; it does not participate in skin test.
crop_local=[]
for p in body_world:
    q=inv_arm @ Vector(p.tolist()); crop_local.append((q.x,q.y,q.z))
crop_obj=create_mesh("MHR_Body_Cropped_Visual",crop_local,body_faces[keep])
crop_obj.matrix_world=arm.matrix_world.copy()
crop_obj.data.materials.append(make_mat("MHR_Body_Bind_Visual",(0.06,0.10,0.16,1),0.58))
body.hide_render=True

# Helper to measure evaluated head after pose.
def evaluated_vertices_world(obj):
    dg=bpy.context.evaluated_depsgraph_get()
    eo=obj.evaluated_get(dg)
    em=eo.to_mesh()
    pts=np.array([(eo.matrix_world @ v.co)[:] for v in em.vertices],dtype=np.float64)
    eo.to_mesh_clear()
    return pts

neutral_eval=evaluated_vertices_world(head_obj)

# Pose tests are deliberately small: they validate binding only, not animation quality.
def reset_pose():
    for pb in arm.pose.bones:
        pb.rotation_mode='XYZ'
        pb.rotation_euler=(0.0,0.0,0.0)
        pb.location=(0.0,0.0,0.0)
        pb.scale=(1.0,1.0,1.0)
    bpy.context.view_layer.update()

def set_pose(kind):
    reset_pose()
    if kind=="head_turn":
        pb=arm.pose.bones.get(target_bones["head"].name)
        pb.rotation_mode='XYZ'; pb.rotation_euler[1]=math.radians(15.0)
    elif kind=="head_tilt":
        pb=arm.pose.bones.get(target_bones["head"].name)
        pb.rotation_mode='XYZ'; pb.rotation_euler[2]=math.radians(10.0)
    elif kind=="eye_aim":
        for role,sgn in [("left_eye",1.0),("right_eye",1.0)]:
            pb=arm.pose.bones.get(target_bones[role].name)
            pb.rotation_mode='XYZ'; pb.rotation_euler[0]=math.radians(8.0)*sgn
    bpy.context.view_layer.update()

pose_metrics={}
for kind in ["head_turn","head_tilt","eye_aim"]:
    set_pose(kind)
    pts=evaluated_vertices_world(head_obj)
    disp=np.linalg.norm(pts-neutral_eval,axis=1)
    pose_metrics[kind]={
        "mean_vertex_displacement_mm":float(disp.mean()*1000.0),
        "max_vertex_displacement_mm":float(disp.max()*1000.0),
        "nontrivial_vertices_gt_0_1mm":int((disp>0.0001).sum()),
        "finite":bool(np.isfinite(pts).all()),
    }
    if not np.isfinite(pts).all() or float(disp.max()) > 1.0:
        raise RuntimeError(f"Binding exploded for {kind}: {pose_metrics[kind]}")
reset_pose()

# Render neutral + three small rig tests.
scene=bpy.context.scene
scene.render.engine="BLENDER_EEVEE"
scene.render.resolution_x=900; scene.render.resolution_y=900; scene.render.resolution_percentage=100
scene.render.image_settings.file_format="PNG"
scene.world.color=(0.009,0.011,0.015)
scene.view_settings.exposure=-0.65
combined_min=np.minimum(body_world.min(0),neutral_eval.min(0)); combined_max=np.maximum(body_world.max(0),neutral_eval.max(0))
center=(combined_min+combined_max)/2; extent=combined_max-combined_min; maxe=float(max(extent))
for lname,direction,energy,size in [("Key",(1.2,-1.4,1.3),60,0.5),("Fill",(-1,-0.7,0.5),22,0.65),("Rim",(0,1.2,1),32,0.45)]:
    ld=bpy.data.lights.new(lname,type="AREA"); lo=bpy.data.objects.new(lname,ld); bpy.context.collection.objects.link(lo)
    lo.location=Vector(center)+Vector(direction).normalized()*maxe*1.8; ld.energy=energy; ld.size=size
camd=bpy.data.cameras.new("BindCamera"); cam=bpy.data.objects.new("BindCamera",camd); bpy.context.collection.objects.link(cam); scene.camera=cam; cam.data.type="ORTHO"

def render(name,axis,target,scale_view):
    axis=Vector(axis).normalized(); target=Vector(target)
    cam.location=target+axis*maxe*2.0; cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler(); cam.data.ortho_scale=scale_view
    scene.render.filepath=str((OUT/name).resolve()); bpy.ops.render.render(write_still=True)

front=(0,-1,0); threeq=(0.7,-1,0)
head_target=(target_world["head"]+target_world["neck"])/2
head_view=float(max(neutral_eval[:,0].ptp(),neutral_eval[:,2].ptp())*1.7)

for kind in ["neutral","head_turn","head_tilt","eye_aim"]:
    if kind=="neutral": reset_pose()
    else: set_pose(kind)
    render(f"{kind}_front.png",front,head_target,head_view)
    render(f"{kind}_three_quarter.png",threeq,head_target,head_view)
reset_pose()

# Export neutral rigged GNM head with the actual MHR armature.
bpy.ops.object.select_all(action='DESELECT')
head_obj.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.gltf(
    filepath=str((OUT/"gnm_head_bound_to_mhr_rig.glb").resolve()),
    export_format='GLB',
    use_selection=True,
)

# Validate weight mapping numerically.
max_weight_sum_error=float(np.max(np.abs(skinning.sum(axis=0)-1.0)))
metrics={
    "sources":{
        "GNM":{"commit":"98450b3c943101d5859ac1ceb7331ec918ebc321","npz_sha256":"868075bbb172fc6574ece89338e21fdc0efe0be91ca4e6e5c3166a1a97840055"},
        "MHR":{"version":"v1.0.1","assets_zip_sha256":"e4f4f205cd87c0fa106577ba1de4fc763e4eb197c924461d2ef7e6944e9d6b94"},
    },
    "joint_map":{r:target_bones[r].name for r in roles},
    "fit_rms_mm":float(np.sqrt(np.mean(fit_resid**2))*1000.0),
    "fit_per_joint_mm":{r:float(fit_resid[i]*1000.0) for i,r in enumerate(roles)},
    "skinning_shape":list(skinning.shape),
    "max_normalized_weight_sum_error":max_weight_sum_error,
    "mapped_vertex_groups":[target_bones[r].name for r in roles],
    "pose_metrics":pose_metrics,
    "head_vertices":int(len(verts)),
    "head_triangles":int(len(tris)),
    "contract":"GNM linear-skinning bind to MHR neck/head/eye bones only. No GNM expression-basis conversion, final neck topology merge, cinematic shading, or gameplay animation claim.",
}
(OUT/"gnm_mhr_head_bind_metrics.json").write_text(json.dumps(metrics,indent=2),encoding='utf-8')
print(json.dumps(metrics,indent=2))
