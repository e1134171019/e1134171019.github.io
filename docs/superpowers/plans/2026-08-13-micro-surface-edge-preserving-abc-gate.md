# Micro-Surface Edge-Preserving A/B/C Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether an edge-preserving low-pass can keep the coherent oval scar/meso structure in the base surface while retaining pores and micro-relief in the residual.

**Architecture:** Reuse the validated `drl_gnm_micro_surface_gate.py` unchanged. Compare the current best Gaussian-6 residual against two bilateral-filter residuals built from the same 4096² displacement proxy. Render all three with identical correspondence and shader settings, then select visually.

**Tech Stack:** GitHub Actions, Ubuntu 24.04, Blender 4.0.2, ImageMagick, Python 3, NumPy/Pillow, OpenCV CPU.

## Global Constraints

- Branch: `experiment/gnm-appearance-gate`; never modify `main`.
- A: Gaussian low-pass sigma 6 px.
- B: OpenCV bilateral low-pass d=13, sigmaSpace=6, sigmaColor=32 in 16-bit proxy intensity units.
- C: OpenCV bilateral low-pass d=13, sigmaSpace=6, sigmaColor=64 in 16-bit proxy intensity units.
- Correspondence remains <=15 mm and <=60 degrees through the existing script.
- Bump distance remains 0.35 mm; bump strength remains 0.32.
- Transfer size remains 1024; GNM/DRL geometry, camera, lights and neutral albedo remain unchanged.
- DRL identity diffuse remains excluded.
- Raw/derived displacement maps are never uploaded.
- Selection is visual; numeric checks only verify the experiment contract.

---

### Task 1: Add edge-preserving A/B/C workflow

**Files:**
- Create: `.github/workflows/drl-gnm-micro-surface-edge-preserving-abc-gate.yml`
- Reuse unchanged: `tools/experiments/drl_gnm_micro_surface_gate.py`

- [ ] Build the same 4096² grayscale displacement proxy.
- [ ] Build A with Gaussian sigma 6.
- [ ] Build B/C with OpenCV bilateral filter using fixed d/sigmaSpace and two sigmaColor values.
- [ ] Run the same Blender gate for A/B/C and preserve metrics + six legal renders per variant.
- [ ] Enforce identical correspondence, alpha core, bump distance, bump strength and target scope across all variants.
- [ ] Create comparison sheets for face close, 3/4 close, front and 3/4 full.
- [ ] Assert no raw/derived DRL maps are redistributed.
- [ ] Download artifact and judge scar suppression against pore/fine-wrinkle retention.

## Decision Contract

- `KEEP_GAUSSIAN6` only if both bilateral variants lose useful micro-detail or add artifacts.
- `KEEP_BILATERAL32` or `KEEP_BILATERAL64` only if the oval scar is materially suppressed while pores remain visible.
- `NEED_STRUCTURE_AWARE_REFINEMENT` if scar persists in all variants.
