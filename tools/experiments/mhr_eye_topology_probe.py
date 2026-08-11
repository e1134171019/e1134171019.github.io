from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
FBX = ROOT / "assets" / "lod1.fbx"
OUT = ROOT / "artifacts" / "mhr-eye-topology-probe"
OUT.mkdir(parents=True, exist_ok=True)


def weighted_vertex_indices(obj, group_name: str, threshold: float = 0.05):
    vg = obj.vertex_groups.get(group_name)
    if vg is None:
        return set(), None
    indices = set()
    weights = []
    for v in obj.data.vertices:
        for g in v.groups:
            if g.group == vg.index:
                weights.append((v.index, g.weight))
                if g.weight >= threshold:
                    indices.add(v.index)
                break
    return indices, weights


def world_bounds_for_vertices(obj, indices):
    if not indices:
        return None
    pts = [obj.matrix_world @ obj.data.vertices[i].co for i in indices]
    return {
        "min": [min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)],
        "max": [max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)],
        "center": [sum(p.x for p in pts)/len(pts), sum(p.y for p in pts)/len(pts), sum(p.z for p in pts)/len(pts)],
    }


def polygon_stats(obj, indices):
    if not indices:
        return {"all_vertices_in_group": 0, "majority_vertices_in_group": 0, "material_histogram_all": {}}
    full = []
    majority = []
    for p in obj.data.polygons:
        hits = sum(1 for i in p.vertices if i in indices)
        if hits == len(p.vertices):
            full.append(p)
        if hits >= max(1, (len(p.vertices)+1)//2):
            majority.append(p)
    return {
        "all_vertices_in_group": len(full),
        "majority_vertices_in_group": len(majority),
        "material_histogram_all": dict(Counter(str(p.material_index) for p in full)),
        "sample_polygon_indices": [p.index for p in full[:20]],
    }


def bone_info(armature, name):
    b = armature.data.bones.get(name) if armature else None
    if b is None:
        return None
    h = armature.matrix_world @ b.head_local
    t = armature.matrix_world @ b.tail_local
    return {
        "head_world": list(h),
        "tail_world": list(t),
        "length": b.length,
        "parent": b.parent.name if b.parent else None,
    }


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True, automatic_bone_orientation=False)

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    arm = arms[0] if arms else None

    result = {
        "mesh_count": len(meshes),
        "armature_count": len(arms),
        "bone_count": sum(len(a.data.bones) for a in arms),
        "bones": {name: bone_info(arm, name) for name in ["l_eye", "r_eye", "l_eye_null", "r_eye_null", "c_head"]},
        "meshes": [],
    }

    for obj in meshes:
        mesh_info = {
            "name": obj.name,
            "vertex_count": len(obj.data.vertices),
            "polygon_count": len(obj.data.polygons),
            "material_slots": [m.name if m else None for m in obj.data.materials],
            "material_histogram": dict(Counter(str(p.material_index) for p in obj.data.polygons)),
            "vertex_groups_matching_eye": [g.name for g in obj.vertex_groups if "eye" in g.name.lower()],
            "groups": {},
        }
        for group_name in ["l_eye", "r_eye", "l_eye_null", "r_eye_null"]:
            idx, weights = weighted_vertex_indices(obj, group_name, 0.05)
            mesh_info["groups"][group_name] = {
                "weighted_vertex_count": len(weights or []),
                "threshold_vertex_count": len(idx),
                "max_weight": max((w for _, w in (weights or [])), default=None),
                "min_positive_weight": min((w for _, w in (weights or []) if w > 0), default=None),
                "bounds": world_bounds_for_vertices(obj, idx),
                "polygons": polygon_stats(obj, idx),
            }
        result["meshes"].append(mesh_info)

    out = OUT / "mhr_eye_topology_probe.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
