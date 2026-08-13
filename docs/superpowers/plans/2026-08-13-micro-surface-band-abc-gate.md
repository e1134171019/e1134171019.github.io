# Micro-Surface Band A/B/C Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Compare DRL displacement high-frequency residuals using low-pass subtraction radii 6 px, 12 px, and 24 px while keeping correspondence, bump distance, bump strength, model, lighting, camera, and transfer resolution fixed.

**Architecture:** Reuse `tools/experiments/drl_gnm_micro_surface_gate.py` unchanged. Add one isolated GitHub Actions workflow that creates three low-pass proxies from the same 4096² source proxy, runs the same Blender gate three times, preserves only legal diagnostic renders/metrics, checks fixed-parameter invariants, and builds side-by-side contact sheets for GPT visual review.

**Tech Stack:** GitHub Actions, Ubuntu 24.04, Blender 4.0.2, ImageMagick, Python 3, NumPy/Pillow via the existing experiment.

## Global Constraints

- Branch: `experiment/gnm-appearance-gate`; never modify `main`.
- Bands: 6 px, 12 px, 24 px only.
- Correspondence contract remains `<=15 mm` and normal agreement `<=60°` via the existing validated script.
- Bump distance remains `0.35 mm`.
- Bump strength remains `0.32`.
- Transfer size remains `1024`.
- GNM model, DRL donor geometry, camera, lighting, neutral base color, and render samples remain unchanged.
- DRL identity diffuse remains excluded.
- Raw or derived DRL displacement/appearance maps must not be uploaded.
- Numeric GREEN is not sufficient for final selection; GPT must inspect the A/B/C images.

---

### Task 1: Add isolated A/B/C workflow

**Files:**
- Create: `.github/workflows/drl-gnm-micro-surface-band-abc-gate.yml`
- Reuse unchanged: `tools/experiments/drl_gnm_micro_surface_gate.py`

**Interfaces:**
- Consumes: official pinned GNM v3, DRL Marcus OBJ + `Marcus_38_Displace.exr`, existing micro-surface script.
- Produces: `artifacts/drl-gnm-micro-surface-band-abc/{px06,px12,px24}/` metrics and six rendered views per band plus A/B/C comparison sheets and `band_summary.json`.

- [ ] **Step 1: Create the workflow**
  - Download/verify the same GNM and DRL inputs as the validated 24 px run.
  - Create `displace_4k.png` once.
  - Create low-pass files with `-blur 0x6`, `-blur 0x12`, `-blur 0x24`.
  - For each band, clear the transient output directory, run the existing Blender script, and copy only metrics/render files into the band artifact directory.

- [ ] **Step 2: Enforce per-band numeric contract**
  - Require `identity_diffuse_used == false`.
  - Require `lowpass_removed == true`.
  - Require correspondence `>=0.70`.
  - Require zero invalid-correspondence alpha leakage.
  - Require numeric gate PASS and micro-surface-only scope contract.
  - Require bump distance exactly `0.35 mm` and strength exactly `0.32`.

- [ ] **Step 3: Enforce A/B/C invariants**
  - Require equal correspondence valid fraction, ray accepted count, nearest fallback count, and full-alpha core fraction across 6/12/24.
  - Record each band’s normalized micro-height std, p95, and p99 in `band_summary.json`.
  - Do not auto-select a winner numerically.

- [ ] **Step 4: Build visual comparison sheets**
  - Create side-by-side sheets for `face_close`, `face_3q_close`, `front`, and `three_quarter_right` in A=6 / B=12 / C=24 order.
  - Preserve original per-band renders for detailed review.

- [ ] **Step 5: Assert source protection**
  - Ensure no `.obj`, `.fbx`, `.ztl`, `.psd`, `.exr`, raw 4K proxy, low-pass proxy, or derived micro-height texture is present in the uploaded artifact.

- [ ] **Step 6: Run GitHub Actions and inspect evidence**
  - Workflow must complete with all steps success.
  - Download the artifact and inspect `band_summary.json` plus all comparison sheets.
  - Final decision must be `KEEP 6`, `KEEP 12`, `KEEP 24`, or `NEED FURTHER BAND REFINEMENT`, based on visual pore retention versus meso-scale scar/relief contamination.

## Self-Review

- Spec coverage: all approved variables and invariants are represented.
- Placeholder scan: none.
- Scope: one workflow, one isolated experiment, no production integration.
- Ambiguity: band labels are fixed as A=6, B=12, C=24; no numeric auto-winner.
