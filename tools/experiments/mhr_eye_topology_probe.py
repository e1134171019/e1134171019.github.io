from __future__ import annotations

import json
import math
from collections import Counter, deque
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
FBX = ROOT / "assets" / "lod1.fbx"
OUT = ROOT / "artifacts" / "mhr-eye-topology-probe"
OUT.mkdir(parents=True, exist_ok=True)

EYE_BONES = ["l_eye", "r_eye", "l_eye_null", "r_eye_null", "c_head"]
MORPH_TERMS = ("eye", "iris", "siris", "blink", "lid", "look", "squint", "pupil", "gaze")


def v3(v):
    return [float(v.x), float(v.y), float(v.z)]


def bone_world_head(armature, name):
    if not armature:
        return None
    bone = armature.data.bones.get(name)
    if bone is None:
        return None
    return armature.matrix_world @ bone.head_local


def bone_info(armature, name):
    if not armature:
        return None
    bone = armature.data.bones.get(name)
    if bone is None:
        return None
    head = armature.matrix_world @ bone.head_local
    tail = armature.matrix_world @ bone.tail_local
    return {
        "head_world": v3(head),
        "tail_world": v3(tail),
        "parent": bone.parent.name if bone.parent else None,
    }


def bounds_for_world_points(points):
    if not points:
        return None
    pmin = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    pmax = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (pmin + pmax) * 0.5
    return {
        "min": v3(pmin),
        "max": v3(pmax),
        "center": v3(center),
        "extents": v3(pmax - pmin),
    }


def build_connected_components(obj):
    vertex_count = len(obj.data.vertices)
    adjacency = [[] for _ in range(vertex_count)]
    for edge in obj.data.edges:
        a, b = edge.vertices
        adjacency[a].append(b)
        adjacency[b].append(a)

    seen = bytearray(vertex_count)
    components = []
    for start in range(vertex_count):
        if seen[start]:
            continue
        q = deque([start])
        seen[start] = 1
        comp = []
        while q:
            i = q.popleft()
            comp.append(i)
            for nxt in adjacency[i]:
                if not seen[nxt]:
                    seen[nxt] = 1
                    q.append(nxt)
        components.append(comp)
    return components


def component_summary(obj, indices, eye_points, component_index):
    index_set = set(indices)
    points = [obj.matrix_world @ obj.data.vertices[i].co for i in indices]
    bounds = bounds_for_world_points(points)
    center = Vector(bounds["center"])
    polygon_count = 0
    for poly in obj.data.polygons:
        if all(i in index_set for i in poly.vertices):
            polygon_count += 1

    eye_distances = {}
    for name, eye_point in eye_points.items():
        if eye_point is not None:
            eye_distances[name] = min((p - eye_point).length for p in points)

    return {
        "component_index": component_index,
        "vertex_count": len(indices),
        "polygon_count": polygon_count,
        "bounds": bounds,
        "distance_to_eye_points_min": eye_distances,
        "center_distance_to_l_eye": (center - eye_points["l_eye"]).length if eye_points.get("l_eye") else None,
        "center_distance_to_r_eye": (center - eye_points["r_eye"]).length if eye_points.get("r_eye") else None,
        "sample_vertex_indices": indices[:20],
    }


def nearest_vertices(obj, point, limit=30):
    ranked = []
    mw = obj.matrix_world
    for v in obj.data.vertices:
        wp = mw @ v.co
        ranked.append(((wp - point).length, v.index, wp))
    ranked.sort(key=lambda x: x[0])
    return [
        {"index": idx, "distance": float(distance), "world": v3(wp)}
        for distance, idx, wp in ranked[:limit]
    ]


def polygon_local_probe(obj, point, radius=0.035, limit=80):
    mw = obj.matrix_world
    candidates = []
    for poly in obj.data.polygons:
        center_world = mw @ poly.center
        distance = (center_world - point).length
        if distance <= radius:
            normal_world = (mw.to_3x3() @ poly.normal).normalized()
            candidates.append({
                "polygon_index": poly.index,
                "distance": float(distance),
                "center_world": v3(center_world),
                "normal_world": v3(normal_world),
                "vertices": list(poly.vertices),
                "material_index": poly.material_index,
            })
    candidates.sort(key=lambda item: item["distance"])
    return candidates[:limit]


def shape_key_probe(obj):
    if not obj.data.shape_keys or not obj.data.shape_keys.key_blocks:
        return {"count_excluding_basis": 0, "all_names": [], "eye_related": []}
    names = [key.name for key in obj.data.shape_keys.key_blocks]
    eye_related = [name for name in names if any(term in name.lower() for term in MORPH_TERMS)]
    return {
        "count_excluding_basis": max(0, len(names) - 1),
        "all_names": names,
        "eye_related": eye_related,
    }


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(FBX), use_anim=True, automatic_bone_orientation=False)

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    arms = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    arm = arms[0] if arms else None
    eye_points = {name: bone_world_head(arm, name) for name in EYE_BONES}

    result = {
        "mesh_count": len(meshes),
        "armature_count": len(arms),
        "bone_count": sum(len(a.data.bones) for a in arms),
        "bones": {name: bone_info(arm, name) for name in EYE_BONES},
        "interpretation_contract": {
            "goal": "Determine whether the neutral MHR eye-looking surface is a disconnected mesh island or part of the continuous body mesh, and expose native eye-related morph controls.",
            "no_geometry_mutation": True,
        },
        "meshes": [],
    }

    for obj in meshes:
        components = build_connected_components(obj)
        component_summaries = [component_summary(obj, comp, eye_points, i) for i, comp in enumerate(components)]
        component_summaries.sort(key=lambda item: item["vertex_count"], reverse=True)

        mesh_info = {
            "name": obj.name,
            "vertex_count": len(obj.data.vertices),
            "edge_count": len(obj.data.edges),
            "polygon_count": len(obj.data.polygons),
            "material_slots": [m.name if m else None for m in obj.data.materials],
            "material_histogram": dict(Counter(str(p.material_index) for p in obj.data.polygons)),
            "connected_component_count": len(components),
            "connected_components": component_summaries[:40],
            "shape_keys": shape_key_probe(obj),
            "nearest_vertices": {},
            "nearby_polygons": {},
        }
        for name in ["l_eye", "r_eye", "l_eye_null", "r_eye_null"]:
            point = eye_points.get(name)
            if point is not None:
                mesh_info["nearest_vertices"][name] = nearest_vertices(obj, point, 30)
                mesh_info["nearby_polygons"][name] = polygon_local_probe(obj, point, 0.035, 80)
        result["meshes"].append(mesh_info)

    out = OUT / "mhr_eye_topology_probe.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    compact = {
        "bone_heads": {name: (result["bones"].get(name) or {}).get("head_world") for name in EYE_BONES},
        "meshes": [
            {
                "name": mesh["name"],
                "vertex_count": mesh["vertex_count"],
                "polygon_count": mesh["polygon_count"],
                "connected_component_count": mesh["connected_component_count"],
                "component_sizes": [c["vertex_count"] for c in mesh["connected_components"][:12]],
                "eye_related_shape_keys": mesh["shape_keys"]["eye_related"],
                "nearest_l_eye": mesh["nearest_vertices"].get("l_eye", [])[:8],
                "nearest_r_eye": mesh["nearest_vertices"].get("r_eye", [])[:8],
                "nearest_l_eye_null": mesh["nearest_vertices"].get("l_eye_null", [])[:8],
                "nearest_r_eye_null": mesh["nearest_vertices"].get("r_eye_null", [])[:8],
            }
            for mesh in result["meshes"]
        ],
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
