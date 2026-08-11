from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import numpy as np
import torch
import trimesh
from mhr.mhr import MHR

OUT_DIR = Path("artifacts/mhr-human-carrier-gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCE = {
    "model": "Meta Momentum Human Rig (MHR)",
    "version": "v1.0.1",
    "lod": 1,
    "device": "cpu",
    "identity_coefficients": 45,
    "pose_parameters": 204,
    "facial_expression_coefficients": 72,
    "purpose": "Human Carrier visual-quality gate only; not final cinematic asset approval",
}


def rotation_z(degrees: float) -> np.ndarray:
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


def canonicalize(vertices: np.ndarray) -> tuple[np.ndarray, dict]:
    """Map unknown model axes to X=lateral, Y=depth, Z=up, front toward -Y.

    Human meshes have a dominant height axis, a smallest depth axis, and the
    remaining axis is lateral width. Front sign is inferred from the stronger
    head protrusion (nose/face) relative to the head-depth median.
    """
    extents = vertices.max(axis=0) - vertices.min(axis=0)
    up_axis = int(np.argmax(extents))
    depth_axis = int(np.argmin(extents))
    lateral_axis = int(({0, 1, 2} - {up_axis, depth_axis}).pop())

    x = vertices[:, lateral_axis]
    z = vertices[:, up_axis]
    raw_y = vertices[:, depth_axis]

    zmin, zmax = z.min(), z.max()
    head = z >= zmax - 0.20 * (zmax - zmin)
    head_depth = raw_y[head]
    median = float(np.median(head_depth))
    positive_protrusion = float(head_depth.max() - median)
    negative_protrusion = float(median - head_depth.min())
    front_sign = 1 if positive_protrusion > negative_protrusion else -1

    # Canonical front must lie toward negative Y.
    y = raw_y * (-front_sign)
    canonical = np.column_stack([x, y, z])

    meta = {
        "source_extents": extents.tolist(),
        "detected_lateral_axis": lateral_axis,
        "detected_depth_axis": depth_axis,
        "detected_up_axis": up_axis,
        "detected_front_sign_on_source_depth_axis": front_sign,
        "canonical_axes": "X=lateral, Y=depth, Z=up; anatomical front toward -Y",
        "head_positive_protrusion": positive_protrusion,
        "head_negative_protrusion": negative_protrusion,
    }
    return canonical, meta


def render_mesh(
    vertices: np.ndarray,
    faces: np.ndarray,
    yaw_deg: float,
    filename: str,
    title: str,
    crop: tuple[float, float, float, float] | None = None,
) -> None:
    center = (vertices.min(axis=0) + vertices.max(axis=0)) * 0.5
    v = (vertices - center) @ rotation_z(yaw_deg).T
    tri = v[faces]

    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    normals = np.cross(e1, e2)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals = normals / lengths

    # Canonical front camera is on -Y looking toward +Y.
    visible = normals[:, 1] < 0.0
    tri = tri[visible]
    normals = normals[visible]
    camera_depth = -tri[:, :, 1].mean(axis=1)
    order = np.argsort(camera_depth)
    tri = tri[order]
    normals = normals[order]

    light = np.array([0.25, -1.0, 0.50], dtype=np.float64)
    light /= np.linalg.norm(light)
    diffuse = np.clip(normals @ light, 0.0, 1.0)
    shade = 0.46 + 0.47 * diffuse
    colors = np.stack([shade, shade, shade, np.ones_like(shade)], axis=1)

    screen_tri = tri[:, :, [0, 2]]
    fig, ax = plt.subplots(figsize=(8, 11), dpi=160)
    ax.add_collection(
        PolyCollection(
            screen_tri,
            facecolors=colors,
            edgecolors="none",
            linewidths=0,
            antialiased=False,
        )
    )

    screen = v[:, [0, 2]]
    if crop is None:
        xmin, ymin = screen.min(axis=0)
        xmax, ymax = screen.max(axis=0)
        dx = max(xmax - xmin, 1e-6)
        dy = max(ymax - ymin, 1e-6)
        ax.set_xlim(xmin - 0.05 * dx, xmax + 0.05 * dx)
        ax.set_ylim(ymin - 0.04 * dy, ymax + 0.04 * dy)
    else:
        xmin, xmax, ymin, ymax = crop
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)

    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    ax.set_title(title, fontsize=12, pad=12)
    fig.tight_layout(pad=0.5)
    fig.savefig(OUT_DIR / filename, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)


def projected_bounds(vertices: np.ndarray):
    center = (vertices.min(axis=0) + vertices.max(axis=0)) * 0.5
    v = vertices - center
    screen = v[:, [0, 2]]
    xmin, ymin = screen.min(axis=0)
    xmax, ymax = screen.max(axis=0)
    return v, screen, xmin, xmax, ymin, ymax


def main() -> None:
    torch.manual_seed(0)
    torch.set_grad_enabled(False)

    mhr_model = MHR.from_files(device=torch.device("cpu"), lod=1)
    identity_coeffs = torch.zeros(1, 45)
    model_parameters = torch.zeros(1, 204)
    face_expr_coeffs = torch.zeros(1, 72)

    with torch.no_grad():
        verts, _skel_state = mhr_model(
            identity_coeffs, model_parameters, face_expr_coeffs
        )

    vertices_raw = verts[0].detach().cpu().numpy().astype(np.float64)
    faces_obj = mhr_model.character.mesh.faces
    if isinstance(faces_obj, torch.Tensor):
        faces = faces_obj.detach().cpu().numpy().astype(np.int64)
    else:
        faces = np.asarray(faces_obj, dtype=np.int64)

    raw_mesh = trimesh.Trimesh(vertices=vertices_raw, faces=faces, process=False)
    raw_mesh.export(OUT_DIR / "mhr_v1.0.1_lod1_neutral_raw.ply")
    raw_mesh.export(OUT_DIR / "mhr_v1.0.1_lod1_neutral_raw.glb")

    vertices, axis_meta = canonicalize(vertices_raw)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.export(OUT_DIR / "mhr_v1.0.1_lod1_neutral_canonical.ply")
    mesh.export(OUT_DIR / "mhr_v1.0.1_lod1_neutral_canonical.glb")

    # Preserve the official rigged LOD1 FBX from the v1.0.1 asset package.
    official_fbx = Path("assets/lod1.fbx")
    if official_fbx.exists():
        shutil.copy2(official_fbx, OUT_DIR / "mhr_v1.0.1_lod1_official_rigged.fbx")

    render_mesh(vertices, faces, 0.0, "01_front.png", "MHR v1.0.1 LOD1 | Front")
    render_mesh(vertices, faces, 45.0, "02_three_quarter.png", "MHR v1.0.1 LOD1 | 3/4")
    render_mesh(vertices, faces, 90.0, "03_side.png", "MHR v1.0.1 LOD1 | Side")
    render_mesh(vertices, faces, 180.0, "04_back.png", "MHR v1.0.1 LOD1 | Back")

    _v, screen, xmin, xmax, ymin, ymax = projected_bounds(vertices)
    w = xmax - xmin
    h = ymax - ymin

    head_mask = screen[:, 1] >= ymax - 0.19 * h
    hx0, hy0 = screen[head_mask].min(axis=0)
    hx1, hy1 = screen[head_mask].max(axis=0)
    hm = 0.12 * max(hx1 - hx0, hy1 - hy0, 1e-6)
    render_mesh(
        vertices,
        faces,
        0.0,
        "05_face.png",
        "MHR v1.0.1 LOD1 | Face Gate",
        (hx0 - hm, hx1 + hm, hy0 - hm, hy1 + hm),
    )

    left_extreme = screen[:, 0] <= xmin + 0.09 * w
    right_extreme = screen[:, 0] >= xmax - 0.09 * w
    for mask, filename, label in [
        (left_extreme, "06_left_hand.png", "Left Hand Gate"),
        (right_extreme, "07_right_hand.png", "Right Hand Gate"),
    ]:
        pts = screen[mask]
        px0, py0 = pts.min(axis=0)
        px1, py1 = pts.max(axis=0)
        span = max(px1 - px0, py1 - py0, 1e-6)
        margin = 0.25 * span
        render_mesh(
            vertices,
            faces,
            0.0,
            filename,
            f"MHR v1.0.1 LOD1 | {label}",
            (px0 - margin, px1 + margin, py0 - margin, py1 + margin),
        )

    feet_mask = screen[:, 1] <= ymin + 0.14 * h
    fx0, fy0 = screen[feet_mask].min(axis=0)
    fx1, fy1 = screen[feet_mask].max(axis=0)
    fm = 0.12 * max(fx1 - fx0, fy1 - fy0, 1e-6)
    render_mesh(
        vertices,
        faces,
        0.0,
        "08_feet.png",
        "MHR v1.0.1 LOD1 | Feet Gate",
        (fx0 - fm, fx1 + fm, fy0 - fm, fy1 + fm),
    )

    metrics = {
        **SOURCE,
        **axis_meta,
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "raw_bounds_min": raw_mesh.bounds[0].tolist(),
        "raw_bounds_max": raw_mesh.bounds[1].tolist(),
        "canonical_extents": mesh.extents.tolist(),
        "is_watertight": bool(mesh.is_watertight),
        "is_winding_consistent": bool(mesh.is_winding_consistent),
        "official_rigged_fbx_included": official_fbx.exists(),
        "gate_status": "READY_FOR_GPT_VISUAL_REVIEW",
    }
    (OUT_DIR / "gate_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_DIR / "README.txt").write_text(
        "MHR v1.0.1 LOD1 Human Carrier Gate artifact\n"
        "Neutral identity / neutral pose / neutral expression; generated on CPU.\n"
        "Official rigged lod1.fbx is preserved when present.\n"
        "This artifact is for Human Carrier validation, not final cinematic asset approval.\n",
        encoding="utf-8",
    )

    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
