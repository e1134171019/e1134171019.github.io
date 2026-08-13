# DRL → GNM Ray Geometry / Transfer Backend Design

## Goal

Diagnose why Blender Cycles Selected-to-Active produces zero coverage for the already-registered DRL donor → GNM `hockey_mask`, then compare an explicit-cage projection backend against deterministic CPU surface-correspondence before any identity texture is baked.

## Scope

- Existing MHR/GNM character foundation is unchanged.
- Existing DRL rigid + bounded non-rigid registration is reproduced exactly.
- Stage 1 is measurement only: no Cycles bake parameters are changed.
- Stage 2 may execute only after Stage 1 classifies donor position relative to GNM outward normals.
- No raw DRL OBJ or identity textures are uploaded as artifacts.
- No changes to `main`, no deployment, no formal asset adoption.

## Stage 1 — Ray Geometry Diagnostic

For GNM `hockey_mask` surface samples:

1. Compute area-weighted GNM vertex normals from canonical triangles.
2. Orient normals outward using the head centroid as a global consistency check.
3. Query nearest points on the registered DRL triangle surface using a BVH.
4. For each GNM sample compute:
   - Euclidean distance `|Q-P|`.
   - Signed normal offset `dot(Q-P, N)`.
   - Tangential residual magnitude.
5. Report fractions on `+N` and `-N`, distance buckets, percentiles, and normal-orientation consistency.
6. Produce a safe diagnostic heatmap/contact sheet without DRL identity texture.

Decision rule:

- Dominant `+N`: current inward cast direction is geometrically inconsistent with donor placement; explicit outward cage is required for Cycles A-test.
- Dominant `-N`: donor is geometrically reachable by inward rays; investigate Cycles selection/cage configuration before changing direction.
- Mixed: use explicit per-region cage and semantic filtering; do not use a single global extrusion assumption.

## Stage 2 — Coverage A/B

### A. Explicit Cage Coverage

- Duplicate the exact GNM hockey target topology.
- Offset cage origins in the direction established by Stage 1.
- Use `use_cage=True` and a real `cage_object`; do not infer success from `cage_extrusion` alone.
- Bake only a white emission coverage mask.
- Gate: expected hockey UV coverage ≥ 95%, with no non-hockey identity output.

### B. CPU Correspondence Coverage

- Rasterize target GNM UV triangles.
- At each target texel, reconstruct 3D position + interpolated target normal via barycentric coordinates.
- Query the registered DRL triangle surface using nearest/ray correspondence.
- Reject samples exceeding distance or normal-compatibility limits.
- Output only a binary coverage map and correspondence metrics.
- Cache mapping as `target_texel → donor_triangle + barycentric_coordinates` if valid.

## Backend Selection

Compare A and B on:

- hockey-mask coverage,
- wrong-surface / semantic bleed risk,
- deterministic repeatability,
- boundary/seam behavior,
- reuse across diffuse/specular/gloss/normal/displacement.

Only the winning backend may proceed to a real diffuse-only transfer Gate.

## Success Criteria

Stage 1 must produce an unambiguous signed-distance distribution with >95% valid BVH matches. Stage 2 must produce at least one backend with ≥95% hockey UV coverage while preserving semantic exclusions and without publishing DRL source assets.