from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
import numpy as np
import torch
import trimesh
import anny

OUT_DIR = Path("artifacts/anny-human-carrier-gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCE = {
    "model": "NAVER Anny",
    "version": "v0.6.0",
    "source_commit": "72104cac8242d1735ec06433b65bec5e26953ce7",
    "rig": "anny",
    "topology": "anny",
    "skinning_method": "lbs",
    "coordinate_system_verified_from_output": "Z-up; front camera on -Y looking +Y",
    "purpose": "Human Carrier visual-quality gate only; not final cinematic asset approval",
}


def rotation_z(degrees: float) -> np.ndarray:
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)


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

    # Verified from the generated Anny v0.6 mesh: Z is up and the anatomical
    # front is viewed from -Y toward +Y. Screen coordinates are X/Z.
    visible = normals[:, 1] < 0.0
    tri = tri[visible]
    normals = normals[visible]

    # Camera is on -Y. Larger (-Y) camera depth is closer; draw far to near.
    camera_depth = -tri[:, :, 1].mean(axis=1)
    order = np.argsort(camera_depth)
    tri = tri[order]
    normals = normals[order]

    light = np.array([0.25, -1.0, 0.50], dtype=np.float64)
    light /= np.linalg.norm(light)
    diffuse = np.clip(normals @ light, 0.0, 1.0)
    shade = 0.48 + 0.45 * diffuse
    colors = np.stack([shade, shade, shade, np.ones_like(shade)], axis=1)

    screen_tri = tri[:, :, [0, 2]]
    fig, ax = plt.subplots(figsize=(8, 11), dpi=160)
    polys = PolyCollection(
        screen_tri,
        facecolors=colors,
        edgecolors="none",
        linewidths=0,
        antialiased=False,
    )
    ax.add_collection(polys)

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


def projected_bounds(vertices: np.ndarray, yaw_deg: float = 0.0):
    center = (vertices.min(axis=0) + vertices.max(axis=0)) * 0.5
    v = (vertices - center) @ rotation_z(yaw_deg).T
    screen = v[:, [0, 2]]
    xmin, ymin = screen.min(axis=0)
    xmax, ymax = screen.max(axis=0)
    return v, screen, xmin, xmax, ymin, ymax


def main() -> None:
    torch.set_grad_enabled(False)

    model = anny.Anny(rig="anny", topology="anny", skinning_method="lbs")
    output = model()

    vertices = output["vertices"].detach().cpu().numpy()[0].astype(np.float64)
    faces_t = model.faces.detach().cpu() if isinstance(model.faces, torch.Tensor) else model.faces
    faces = np.asarray(faces_t, dtype=np.int64)

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.export(OUT_DIR / "anny_v0.6_default.ply")
    mesh.export(OUT_DIR / "anny_v0.6_default.glb")

    # Full-body Human Carrier gate views. Rotation is around anatomical up (+Z).
    render_mesh(vertices, faces, 0.0, "01_front.png", "Anny v0.6 | Front")
    render_mesh(vertices, faces, 45.0, "02_three_quarter.png", "Anny v0.6 | 3/4")
    render_mesh(vertices, faces, 90.0, "03_side.png", "Anny v0.6 | Side")
    render_mesh(vertices, faces, 180.0, "04_back.png", "Anny v0.6 | Back")

    # Front-view close-up gates derived from actual X/Z projected bounds.
    v, screen, xmin, xmax, ymin, ymax = projected_bounds(vertices, 0.0)
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
        "Anny v0.6 | Face Gate",
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
            f"Anny v0.6 | {label}",
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
        "Anny v0.6 | Feet Gate",
        (fx0 - fm, fx1 + fm, fy0 - fm, fy1 + fm),
    )

    metrics = {
        **SOURCE,
        "vertex_count": int(len(vertices)),
        "face_count": int(len(faces)),
        "bone_count": int(model.bone_count),
        "phenotype_labels": list(model.phenotype_labels),
        "bounds_min": mesh.bounds[0].tolist(),
        "bounds_max": mesh.bounds[1].tolist(),
        "extents": mesh.extents.tolist(),
        "is_watertight": bool(mesh.is_watertight),
        "is_winding_consistent": bool(mesh.is_winding_consistent),
        "gate_status": "READY_FOR_GPT_VISUAL_REVIEW",
    }
    (OUT_DIR / "gate_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_DIR / "README.txt").write_text(
        "Anny v0.6 Human Carrier Gate artifact\n"
        "Source: NAVER anny v0.6.0 @ 72104cac8242d1735ec06433b65bec5e26953ce7\n"
        "Coordinate system verified from generated output: Z-up; front camera = -Y.\n"
        "This artifact is for anatomy/proportion/carrier validation only.\n"
        "It is not approval of the final cinematic character asset.\n",
        encoding="utf-8",
    )

    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
