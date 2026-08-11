from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import torch

ROOT = Path.cwd()
MODEL_PATH = ROOT / "assets" / "mhr_model.pt"
OUT = ROOT / "artifacts" / "mhr-official-expression-gate"
OUT.mkdir(parents=True, exist_ok=True)


def as_np(tensor):
    return tensor.detach().cpu().numpy().astype(np.float32)


def evaluate(model, identity, pose, expression, apply_correctives=True):
    with torch.inference_mode():
        vertices, skeleton = model(
            identity_coeffs=torch.from_numpy(identity[np.newaxis, :].copy()),
            model_parameters=torch.from_numpy(pose[np.newaxis, :].copy()),
            face_expr_coeffs=torch.from_numpy(expression[np.newaxis, :].copy()),
            apply_correctives=apply_correctives,
        )
    return as_np(vertices[0]), as_np(skeleton[0])


def find_joint_index(joint_names, candidates):
    for name in candidates:
        if name in joint_names:
            return joint_names.index(name), name
    lowered = [name.lower() for name in joint_names]
    for candidate in candidates:
        c = candidate.lower()
        for i, name in enumerate(lowered):
            if c in name:
                return i, joint_names[i]
    return None, None


def bounds(vertices):
    return {
        "min": vertices.min(axis=0).tolist(),
        "max": vertices.max(axis=0).tolist(),
        "extents": np.ptp(vertices, axis=0).tolist(),
    }


def eye_vertex_sets(vertices, eye_surface):
    # TorchScript MHR geometry is in centimeters, with Y as vertical.
    delta = vertices - eye_surface[np.newaxis, :3]
    local = (
        (np.abs(delta[:, 0]) <= 2.4)
        & (np.abs(delta[:, 1]) <= 1.6)
        & (np.abs(delta[:, 2]) <= 1.1)
    )
    local_indices = np.flatnonzero(local)
    if len(local_indices) < 50:
        # Slightly wider depth fallback for differing FBX/model conventions.
        local = (
            (np.abs(delta[:, 0]) <= 2.5)
            & (np.abs(delta[:, 1]) <= 1.8)
            & (np.abs(delta[:, 2]) <= 2.0)
        )
        local_indices = np.flatnonzero(local)
    upper = local_indices[vertices[local_indices, 1] >= eye_surface[1] + 0.12]
    lower = local_indices[vertices[local_indices, 1] <= eye_surface[1] - 0.12]
    return {
        "all": local_indices,
        "upper": upper,
        "lower": lower,
    }


def mean_y_displacement(candidate, neutral, indices):
    if len(indices) == 0:
        return 0.0
    return float(np.mean(candidate[indices, 1] - neutral[indices, 1]))


def mean_displacement(candidate, neutral, indices=None):
    if indices is None:
        delta = candidate - neutral
    else:
        delta = candidate[indices] - neutral[indices]
    if len(delta) == 0:
        return 0.0
    return float(np.mean(np.linalg.norm(delta, axis=1)))


def opening_metrics(candidate, neutral, sets):
    result = {}
    openings = []
    local_indices = []
    for side, group in sets.items():
        upper = mean_y_displacement(candidate, neutral, group["upper"])
        lower = mean_y_displacement(candidate, neutral, group["lower"])
        opening = upper - lower
        result[side] = {
            "upper_mean_dy_cm": upper,
            "lower_mean_dy_cm": lower,
            "opening_delta_cm": opening,
            "local_mean_displacement_cm": mean_displacement(candidate, neutral, group["all"]),
        }
        openings.append(opening)
        local_indices.extend(group["all"].tolist())
    local_unique = np.asarray(sorted(set(local_indices)), dtype=np.int64)
    bilateral = float(np.mean(openings))
    asymmetry = float(abs(openings[0] - openings[1])) if len(openings) == 2 else 0.0
    # Sparse whole-body sample is enough to detect expression components that unexpectedly affect the body.
    sample = np.arange(0, len(neutral), max(1, len(neutral) // 1600), dtype=np.int64)
    return {
        "bilateral_opening_delta_cm": bilateral,
        "bilateral_asymmetry_cm": asymmetry,
        "eye_local_mean_displacement_cm": mean_displacement(candidate, neutral, local_unique),
        "body_sample_mean_displacement_cm": mean_displacement(candidate, neutral, sample),
        "eyes": result,
    }


def save_obj(path, vertices_cm, faces):
    vertices_m = vertices_cm / 100.0
    with path.open("w", encoding="utf-8") as f:
        f.write("# MHR expression diagnostic mesh; meters\n")
        for x, y, z in vertices_m:
            f.write(f"v {x:.8f} {y:.8f} {z:.8f}\n")
        for a, b, c in faces:
            # OBJ indices are one-based.
            f.write(f"f {int(a)+1} {int(b)+1} {int(c)+1}\n")


def ridge_solution(response_matrix, target, ridge):
    # Minimum-norm coefficient vector for A c ~= target.
    a = response_matrix
    eye = np.eye(a.shape[0], dtype=np.float32)
    coeff = a.T @ np.linalg.solve(a @ a.T + ridge * eye, target)
    max_abs = float(np.max(np.abs(coeff)))
    if max_abs > 1.0:
        coeff = coeff / max_abs
    return np.clip(coeff, -1.0, 1.0).astype(np.float32)


def main():
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(MODEL_PATH)

    model = torch.jit.load(str(MODEL_PATH), map_location="cpu").eval()
    identity_count = int(model.get_num_identity_blendshapes())
    parameter_names = list(model.get_parameter_names())
    pose_count = len(parameter_names) - identity_count
    joint_names = list(model.get_joint_names())
    expression_count = 72

    identity = np.zeros(identity_count, dtype=np.float32)
    pose = np.zeros(pose_count, dtype=np.float32)
    expression = np.zeros(expression_count, dtype=np.float32)
    neutral_vertices, neutral_skeleton = evaluate(model, identity, pose, expression)
    faces = as_np(model.character_torch.mesh.faces).astype(np.int64)

    # Prefer the surface locator joints; fall back to actual eye joints.
    li, left_locator_name = find_joint_index(joint_names, ["l_eye_null", "left_eye_null", "l_eye"])
    ri, right_locator_name = find_joint_index(joint_names, ["r_eye_null", "right_eye_null", "r_eye"])
    if li is None or ri is None:
        raise RuntimeError("Could not find MHR eye locator joints")
    left_locator = neutral_skeleton[li, :3]
    right_locator = neutral_skeleton[ri, :3]

    sets = {
        "left": eye_vertex_sets(neutral_vertices, left_locator),
        "right": eye_vertex_sets(neutral_vertices, right_locator),
    }
    for side, group in sets.items():
        if len(group["upper"]) < 10 or len(group["lower"]) < 10:
            raise RuntimeError(
                f"Eye-local set too small for {side}: all={len(group['all'])} upper={len(group['upper'])} lower={len(group['lower'])}"
            )

    component_results = []
    response_rows = []
    component_vertices = {}
    for index in range(expression_count):
        best = None
        plus_response = None
        for value in (1.0, -1.0):
            expr = np.zeros(expression_count, dtype=np.float32)
            expr[index] = value
            vertices, _ = evaluate(model, identity, pose, expr)
            metrics = opening_metrics(vertices, neutral_vertices, sets)
            item = {
                "index": index,
                "name": f"expression_{index+1:02d}",
                "value": value,
                **metrics,
            }
            if best is None or item["bilateral_opening_delta_cm"] > best["bilateral_opening_delta_cm"]:
                best = item
                component_vertices[(index, value)] = vertices
            if value == 1.0:
                plus_response = metrics
        component_results.append(best)
        response_rows.append(
            [
                plus_response["eyes"]["left"]["upper_mean_dy_cm"],
                plus_response["eyes"]["left"]["lower_mean_dy_cm"],
                plus_response["eyes"]["right"]["upper_mean_dy_cm"],
                plus_response["eyes"]["right"]["lower_mean_dy_cm"],
            ]
        )

    component_results.sort(
        key=lambda item: (
            item["bilateral_opening_delta_cm"] - 0.5 * item["bilateral_asymmetry_cm"],
            -item["body_sample_mean_displacement_cm"],
        ),
        reverse=True,
    )

    # A has shape [4 eyelid responses, 72 expression components].
    A = np.asarray(response_rows, dtype=np.float32).T
    target_profiles = {
        "ridge_open_4mm": np.asarray([0.28, -0.12, 0.28, -0.12], dtype=np.float32),
        "ridge_open_6mm": np.asarray([0.42, -0.18, 0.42, -0.18], dtype=np.float32),
        "ridge_open_8mm": np.asarray([0.55, -0.25, 0.55, -0.25], dtype=np.float32),
    }
    combinations = []
    candidate_meshes = [("neutral", neutral_vertices, {"type": "neutral"})]

    for name, target in target_profiles.items():
        coeff = ridge_solution(A, target, ridge=0.015)
        vertices, _ = evaluate(model, identity, pose, coeff)
        metrics = opening_metrics(vertices, neutral_vertices, sets)
        combinations.append({
            "name": name,
            "coefficients": coeff.tolist(),
            "nonzero_coefficients": [
                {"index": i, "name": f"expression_{i+1:02d}", "value": float(v)}
                for i, v in enumerate(coeff)
                if abs(float(v)) >= 0.03
            ],
            **metrics,
        })
        candidate_meshes.append((name, vertices, {"type": "ridge", "coefficients": coeff.tolist(), **metrics}))

    # Render the best four single components as a sanity check against the combined solutions.
    for rank, item in enumerate(component_results[:4], start=1):
        key = (item["index"], item["value"])
        vertices = component_vertices.get(key)
        if vertices is None:
            expr = np.zeros(expression_count, dtype=np.float32)
            expr[item["index"]] = item["value"]
            vertices, _ = evaluate(model, identity, pose, expr)
        candidate_meshes.append((f"single_{rank:02d}_{item['name']}_{'plus' if item['value'] > 0 else 'minus'}", vertices, {"type": "single", **item}))

    manifests = []
    for name, vertices, meta in candidate_meshes:
        path = OUT / f"{name}.obj"
        save_obj(path, vertices, faces)
        manifests.append({"name": name, "obj": path.name, "meta": meta})

    payload = {
        "model": "MHR official TorchScript",
        "model_asset": "assets/mhr_model.pt",
        "formal_final_character": False,
        "identity_count": identity_count,
        "pose_count": pose_count,
        "expression_count": expression_count,
        "vertex_count": int(neutral_vertices.shape[0]),
        "face_count": int(faces.shape[0]),
        "joint_count": len(joint_names),
        "neutral_bounds_cm": bounds(neutral_vertices),
        "left_eye_locator": {"joint": left_locator_name, "index": li, "position_cm": left_locator.tolist()},
        "right_eye_locator": {"joint": right_locator_name, "index": ri, "position_cm": right_locator.tolist()},
        "eye_vertex_sets": {
            side: {key: int(len(indices)) for key, indices in group.items()}
            for side, group in sets.items()
        },
        "top_single_components": component_results[:16],
        "ridge_combinations": combinations,
        "candidate_meshes": manifests,
        "interpretation": "Numeric probe only. Visual acceptance requires Blender renders; no source topology was modified.",
    }
    (OUT / "mhr_official_expression_probe.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({
        "model": payload["model"],
        "vertex_count": payload["vertex_count"],
        "face_count": payload["face_count"],
        "joint_count": payload["joint_count"],
        "eye_vertex_sets": payload["eye_vertex_sets"],
        "top_single_components": payload["top_single_components"][:8],
        "ridge_combinations": payload["ridge_combinations"],
        "candidate_meshes": [m["name"] for m in manifests],
    }, indent=2))


if __name__ == "__main__":
    main()
