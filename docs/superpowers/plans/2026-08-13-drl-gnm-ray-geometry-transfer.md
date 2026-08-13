# DRL → GNM Ray Geometry / Transfer Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine why Cycles coverage is zero and select a reliable DRL→GNM facial texture-transfer backend without changing the accepted MHR/GNM character foundation.

**Architecture:** First isolate signed ray geometry as a pure diagnostic over the existing registered meshes. Then run two white-mask-only coverage backends: explicit Blender cage and CPU barycentric correspondence. Identity diffuse is forbidden until a backend reaches the coverage contract.

**Tech Stack:** Python 3, NumPy, Blender 4.x headless, `mathutils.bvhtree`, GitHub Actions, GNM v3 pinned NPZ, DRL Marcus PBR sample.

## Global Constraints

- Work only on `experiment/gnm-appearance-gate`.
- Do not change `main` or deploy.
- Do not upload DRL OBJ or raw identity textures.
- Reproduce existing rigid + bounded non-rigid registration parameters exactly.
- Stage 1 may not modify Cycles bake settings.
- Real diffuse bake remains blocked until coverage ≥95%.

---

### Task 1: Signed-distance math contract

**Files:**
- Create: `tests/experiments/test_ray_geometry_math.py`
- Create after RED: `tools/experiments/ray_geometry_math.py`

**Interfaces:**
- Produces `summarize_signed_offsets(points, normals, nearest_points) -> dict`.

- [ ] Write a failing unittest that requires +N/-N classification, distance buckets, and tangential residual statistics.
- [ ] Trigger CI and verify RED because `ray_geometry_math` does not exist.
- [ ] Implement the minimal NumPy helper.
- [ ] Re-run and verify GREEN.

### Task 2: Ray Geometry Diagnostic Gate

**Files:**
- Create: `tools/experiments/drl_gnm_ray_geometry_gate.py`
- Create: `.github/workflows/drl-gnm-ray-geometry-gate.yml`

**Interfaces:**
- Consumes pinned GNM NPZ and private DRL OBJ.
- Produces `ray_geometry_metrics.json`, safe heatmap/contact sheet, and a machine decision: `DOMINANT_PLUS_N`, `DOMINANT_MINUS_N`, or `MIXED_SIGN`.

- [ ] Reproduce the previously accepted rigid + bounded non-rigid registration.
- [ ] Build outward GNM hockey normals and registered DRL BVH.
- [ ] Measure nearest triangle points and signed offsets.
- [ ] Require >95% valid matches and non-empty signed distribution.
- [ ] Upload only safe diagnostics.

### Task 3: Coverage A/B Gate

**Files:**
- Create after Task 2 result: `tools/experiments/drl_gnm_transfer_ab_gate.py`
- Create: `.github/workflows/drl-gnm-transfer-ab-gate.yml`

**Interfaces:**
- A: explicit cage → binary GNM UV coverage.
- B: CPU correspondence → binary GNM UV coverage + cached donor triangle/barycentric mapping metadata only.

- [ ] Configure A according to the measured signed direction; set `use_cage=True` and explicit cage object.
- [ ] Rasterize the same hockey UV footprint for B and compute 3D barycentric samples.
- [ ] Apply semantic/distance/normal compatibility filters.
- [ ] Compare coverage and deterministic repeatability.
- [ ] Select backend only if ≥95% expected hockey UV pixels receive valid source correspondence.

### Task 4: Verification and decision

- [ ] Confirm no raw DRL mesh/texture appears in artifacts.
- [ ] Confirm no repository change outside experiment/docs/tests/workflow paths.
- [ ] Record KEEP / PARTIAL / REJECT for each backend.
- [ ] Keep real diffuse transfer blocked unless one backend passes the 95% contract.