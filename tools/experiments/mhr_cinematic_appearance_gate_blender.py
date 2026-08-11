from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUT = ROOT / "artifacts" / "mhr-cinematic-appearance-gate"
OUT.mkdir(parents=True, exist_ok=True)
FBX = ROOT / "assets" / "lod1.fbx"


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def mesh_objects():
    return [o for o in bpy.context.scene.objects if o.type == "MESH"]


def world_vertices(obj):
    mw = obj.matrix_world
    return [mw @ v.co for v in obj.data.vertices]


def world_bounds(objects):
    pts = [obj.matrix_world @ Vector(c) for obj in objects for c in obj.bound_box]
    if not pts:
        raise RuntimeError("No mesh geometry")
    return Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))), Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))


def anatomical_head_bounds(meshes, center, bmax, extent):
    z_floor = bmax.z - extent.z * 0.145
    x_limit = extent.z * 0.085
    pts = [p for obj in meshes for p in world_vertices(obj) if p.z >= z_floor and abs(p.x-center.x) <= x_limit]
    if len(pts) < 100:
        raise RuntimeError(f"Insufficient head samples: {len(pts)}")
    return Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))), Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))


def principled_input(bsdf, name, value):
    s = bsdf.inputs.get(name)
    if s is not None:
        s.default_value = value


def make_simple_material(name, rgb, roughness=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    principled_input(b, "Base Color", (*rgb, 1.0))
    principled_input(b, "Roughness", roughness)
    return m


def make_skin_material():
    m = make_simple_material("CinematicSkin", (0.285, 0.112, 0.060), 0.52)
    nodes, links = m.node_tree.nodes, m.node_tree.links
    b = nodes.get("Principled BSDF")
    principled_input(b, "IOR", 1.42)
    principled_input(b, "Subsurface Weight", 0.07)
    n = nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 145.0
    n.inputs["Detail"].default_value = 5.0
    n.inputs["Roughness"].default_value = 0.70
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    bump.inputs["Distance"].default_value = 0.0009
    links.new(n.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def make_hair_material():
    m = make_simple_material("HairDarkBrown", (0.009, 0.0035, 0.002), 0.52)
    nodes, links = m.node_tree.nodes, m.node_tree.links
    b = nodes.get("Principled BSDF")
    n = nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 210.0
    n.inputs["Detail"].default_value = 3.2
    n.inputs["Roughness"].default_value = 0.80
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.20
    bump.inputs["Distance"].default_value = 0.0011
    links.new(n.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def assign_material(objects, material):
    for o in objects:
        o.data.materials.clear()
        o.data.materials.append(material)


def add_uv_sphere(name, loc, scale, mat, segments=48, rings=24):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def find_head_bone(arm):
    if not arm:
        return None
    names = [b.name for b in arm.data.bones]
    for n in ["c_head", "head", "Head", "HEAD", "b_head", "joint_head"]:
        if n in names:
            return n
    return next((n for n in names if "head" in n.lower() and "end" not in n.lower()), None)


def parent_to_bone_keep_world(obj, arm, bone):
    if not arm or not bone:
        return False
    mw = obj.matrix_world.copy()
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    obj.matrix_world = mw
    return True


def add_eye(side, hmin, hmax, arm, head_bone, mats):
    hs = hmax-hmin
    sx = 1 if side == "L" else -1
    x = (hmin.x+hmax.x)*0.5 + sx*hs.x*0.135
    z = hmax.z - hs.z*0.430
    cy = hmin.y + hs.y*0.250
    rx, ry, rz = hs.x*0.045, hs.y*0.040, hs.z*0.044
    sclera = add_uv_sphere(f"Eye_{side}_Sclera", (x,cy,z), (rx,ry,rz), mats["sclera"])
    iris_y = cy-ry*0.92
    iris = add_uv_sphere(f"Eye_{side}_Iris", (x,iris_y,z), (rx*0.38,ry*0.10,rz*0.42), mats["iris"],40,20)
    pupil = add_uv_sphere(f"Eye_{side}_Pupil", (x,iris_y-ry*0.08,z), (rx*0.15,ry*0.05,rz*0.17), mats["pupil"],32,16)
    catch = add_uv_sphere(f"Eye_{side}_Catchlight", (x-sx*rx*0.18,iris_y-ry*0.12,z+rz*0.22), (rx*0.055,ry*0.030,rz*0.065), mats["catch"],24,12)
    for o in (sclera,iris,pupil,catch): parent_to_bone_keep_world(o,arm,head_bone)
    return [sclera,iris,pupil,catch], Vector((x,cy,z)), Vector((rx,ry,rz))


def add_poly_curve(name, points, mat, bevel):
    d=bpy.data.curves.new(name,type="CURVE"); d.dimensions="3D"; d.bevel_depth=bevel; d.bevel_resolution=3
    s=d.splines.new("BEZIER"); s.bezier_points.add(len(points)-1)
    for bp,co in zip(s.bezier_points,points): bp.co=co; bp.handle_left_type="AUTO"; bp.handle_right_type="AUTO"
    o=bpy.data.objects.new(name,d); bpy.context.scene.collection.objects.link(o); o.data.materials.append(mat)
    bpy.context.view_layer.objects.active=o; o.select_set(True); bpy.ops.object.convert(target="MESH")
    return o


def add_eyebrows(hmin,hmax,arm,head_bone,hair_mat):
    hs=hmax-hmin; cx0=(hmin.x+hmax.x)*0.5; y=hmin.y+hs.y*0.105; z=hmax.z-hs.z*0.300
    out=[]
    for side,sx in (("L",1),("R",-1)):
        cx=cx0+sx*hs.x*0.135
        pts=[(cx-sx*hs.x*0.065,y+0.001,z-0.002),(cx-sx*hs.x*0.020,y,z+0.0035),(cx+sx*hs.x*0.028,y+0.0004,z+0.003),(cx+sx*hs.x*0.073,y+0.0015,z-0.002)]
        o=add_poly_curve(f"Brow_{side}",pts,hair_mat,hs.x*0.0025); parent_to_bone_keep_world(o,arm,head_bone); out.append(o)
    return out


def add_hair_cap(hmin,hmax,bmax,extent,arm,head_bone,hair_mat):
    hc=(hmin+hmax)*0.5; hs=hmax-hmin
    center=Vector((hc.x,hc.y+hs.y*0.012,hc.z+hs.z*0.012)); radii=Vector((hs.x*0.490,hs.y*0.490,hs.z*0.495))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=72,ring_count=36,location=center)
    cap=bpy.context.object; cap.name="CloseCroppedHairCap"; cap.scale=radii
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    mesh=cap.data; bpy.context.view_layer.objects.active=cap; cap.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="DESELECT"); bpy.ops.object.mode_set(mode="OBJECT")
    lower_back=bmax.z-extent.z*0.070
    front_hairline=bmax.z-extent.z*0.024
    front_split_y=hc.y-hs.y*0.030
    for v in mesh.vertices:
        wp=cap.matrix_world@v.co
        if wp.z<lower_back or (wp.y<front_split_y and wp.z<front_hairline): v.select=True
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.delete(type="VERT"); bpy.ops.object.mode_set(mode="OBJECT")
    sol=cap.modifiers.new("HairThickness","SOLIDIFY"); sol.thickness=0.0016; sol.offset=0.0
    bev=cap.modifiers.new("HairSoftEdge","BEVEL"); bev.width=0.0006; bev.segments=2
    cap.data.materials.append(hair_mat); bpy.ops.object.shade_smooth(); parent_to_bone_keep_world(cap,arm,head_bone)
    return cap


def setup_render_scene(center,extent):
    scene=bpy.context.scene
    try: scene.render.engine="BLENDER_EEVEE_NEXT"
    except Exception: scene.render.engine="BLENDER_EEVEE"
    scene.render.resolution_x=800; scene.render.resolution_y=1000; scene.render.resolution_percentage=100; scene.render.image_settings.file_format="PNG"; scene.world.color=(0.010,0.012,0.018)
    try: scene.view_settings.look="AgX - Medium High Contrast"
    except Exception: pass
    cd=bpy.data.cameras.new("CinematicCamera"); cam=bpy.data.objects.new("CinematicCamera",cd); scene.collection.objects.link(cam); scene.camera=cam; cd.type="PERSP"; cd.lens=72
    def area(name,loc,energy,size,color):
        d=bpy.data.lights.new(name,"AREA"); d.energy=energy; d.shape="DISK"; d.size=size; d.color=color
        o=bpy.data.objects.new(name,d); scene.collection.objects.link(o); o.location=loc; o.rotation_euler=(center-o.location).to_track_quat("-Z","Y").to_euler()
    area("Key",center+Vector((-2.4,-3.2,2.2)),900,2.3,(1.0,0.80,0.69)); area("Fill",center+Vector((2.3,-2.2,1.2)),410,2.0,(0.61,0.75,1.0)); area("Rim",center+Vector((1.4,2.7,2.5)),780,1.7,(0.75,0.84,1.0)); area("TopSoft",center+Vector((0.0,0.2,3.8)),310,2.7,(1.0,0.94,0.88))
    return cam


def point_camera(cam,loc,target):
    cam.location=loc; cam.rotation_euler=(target-loc).to_track_quat("-Z","Y").to_euler()


def render_ring(cam,center,extent,prefix,target_z,radius_factor,angles):
    out=[]; radius=max(extent.x,extent.y)*radius_factor; target=Vector((center.x,center.y-0.015,target_z))
    for deg in angles:
        a=math.radians(deg); loc=Vector((center.x+radius*math.sin(a),center.y-radius*math.cos(a),target_z+extent.z*0.015)); point_camera(cam,loc,target)
        p=OUT/f"{prefix}_{deg:03d}.png"; bpy.context.scene.render.filepath=str(p); bpy.ops.render.render(write_still=True); out.append(p.name)
    return out


def export_glb():
    p=OUT/"mhr_v1.0.1_cinematic_appearance_prototype.glb"
    bpy.ops.export_scene.gltf(filepath=str(p),export_format="GLB",export_apply=False,export_animations=True,export_skins=True,export_morph=True)
    return p


def main():
    if not FBX.exists(): raise FileNotFoundError(FBX)
    reset_scene(); bpy.ops.import_scene.fbx(filepath=str(FBX),use_anim=True,automatic_bone_orientation=False)
    meshes=mesh_objects(); bmin,bmax=world_bounds(meshes); center=(bmin+bmax)*0.5; extent=bmax-bmin; hmin,hmax=anatomical_head_bounds(meshes,center,bmax,extent)
    arms=[o for o in bpy.context.scene.objects if o.type=="ARMATURE"]; arm=arms[0] if arms else None; head_bone=find_head_bone(arm)
    mats={"skin":make_skin_material(),"sclera":make_simple_material("Sclera",(0.76,0.77,0.73),0.22),"iris":make_simple_material("IrisBrown",(0.050,0.016,0.006),0.31),"pupil":make_simple_material("Pupil",(0.0025,0.0025,0.0025),0.08),"catch":make_simple_material("Catchlight",(0.96,0.96,0.96),0.04),"hair":make_hair_material()}
    assign_material(meshes,mats["skin"])
    lp,lc,er=add_eye("L",hmin,hmax,arm,head_bone,mats); rp,rc,_=add_eye("R",hmin,hmax,arm,head_bone,mats); brows=add_eyebrows(hmin,hmax,arm,head_bone,mats["hair"]); hair=add_hair_cap(hmin,hmax,bmax,extent,arm,head_bone,mats["hair"])
    cam=setup_render_scene(center,extent); full=render_ring(cam,center,extent,"view",center.z+extent.z*0.03,2.85,[0,45,90,135,180,225,270,315]); face=render_ring(cam,center,extent,"face",bmax.z-extent.z*0.09,0.48,[0,45,90,180,270,315])
    glb=export_glb(); fbx_copy=OUT/"mhr_v1.0.1_lod1_source_rigged.fbx"; shutil.copy2(FBX,fbx_copy)
    shape_keys=sum(max(0,len(o.data.shape_keys.key_blocks)-1) for o in meshes if o.data.shape_keys and o.data.shape_keys.key_blocks)
    metrics={"model":"Meta Momentum Human Rig (MHR)","source_version":"v1.0.1","prototype":"cinematic_appearance_v4","mesh_object_count_source":len(meshes),"armature_object_count":len(arms),"bone_count":sum(len(a.data.bones) for a in arms),"shape_key_count":shape_keys,"head_bone":head_bone,"estimated_head_bounds_min":list(hmin),"estimated_head_bounds_max":list(hmax),"left_eye_center":list(lc),"right_eye_center":list(rc),"eye_radii":list(er),"added_objects":[o.name for o in lp+rp+brows+[hair]],"materials":[m.name for m in mats.values()],"full_body_views":full,"face_views":face,"glb":glb.name,"source_fbx_copy":fbx_copy.name,"gate_status":"READY_FOR_GPT_CINEMATIC_APPEARANCE_REVIEW","formal_final_character":False,"limitations":["No identity/reference face fitting was performed.","Hair remains a procedural scalp prototype, not production groom.","Procedural skin/hair microdetail is render evidence; portable glTF needs baked production maps.","Full deformation/animation acceptance remains a later gate."]}
    (OUT/"appearance_metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8"); (OUT/"README.txt").write_text("MHR v1.0.1 Cinematic Appearance Prototype Gate v4\nEye-fit convergence + raised frontal hairline. Source topology/rig/morphs remain intact. Not final identity.\n",encoding="utf-8"); print(json.dumps(metrics,indent=2))


if __name__=="__main__": main()
