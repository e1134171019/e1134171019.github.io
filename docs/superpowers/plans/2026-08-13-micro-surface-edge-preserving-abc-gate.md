# Micro-Surface Edge-Preserving A/B/C Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test whether an edge-preserving low-pass can keep the coherent oval scar/meso structure in the base surface while retaining pores and micro-relief in the residual.

**Architecture:** Reuse the validated `drl_gnm_micro_surface_gate.py` unchanged. Compare Gaussian-6 against two bilateral-filter residuals built from the exact pixel/channel domain consumed by that renderer. A pre-render parity Gate must prove the low-pass builder and the renderer see the same source/low-pass intensities before any visual comparison is accepted.

**Tech Stack:** GitHub Actions, Ubuntu 24.04, Blender 4.0.2, ImageMagick, Python 3, NumPy/Pillow, OpenCV CPU.

## Global Constraints

- Branch: `experiment/gnm-appearance-gate`; never modify `main`.
- A: Gaussian low-pass sigma 6 px.
- B: OpenCV bilateral low-pass d=13, sigmaSpace=6, sigmaColor=32 in the renderer's actual PIL consumer intensity domain.
- C: OpenCV bilateral low-pass d=13, sigmaSpace=6, sigmaColor=64 in the renderer's actual PIL consumer intensity domain.
- Correspondence remains <=15 mm and <=60 degrees through the existing script.
- Bump distance remains 0.35 mm; bump strength remains 0.32.
- Transfer size remains 1024; GNM/DRL geometry, camera, lights and neutral albedo remain unchanged.
- DRL identity diffuse remains excluded.
- Raw/derived displacement maps are never uploaded.
- Selection is visual; numeric checks verify the experiment contract and representation parity.

## Representation-Parity Gate

The prior run is invalid for filter comparison because OpenCV built B/C in a 16-bit grayscale domain while the renderer consumed the ImageMagick source through PIL's channel representation. Evidence: builder p99.5 residual was ~24.7/~51.9, while the renderer measured ~7204/~7199 from the same B/C files.

The corrected workflow must:
- Load the source with Pillow exactly as `drl_gnm_micro_surface_gate.py` does and select channel 0 if multi-channel.
- Build bilateral filters from that consumer-domain array.
- Save B/C through Pillow in a representation that round-trips to the same shape/value domain.
- Re-read A/B/C through Pillow and run the same `micro_height_from_lowpass(..., percentile=99.5)` function before Blender.
- Record consumer dtype/range and per-variant residual scale.
- Abort before rendering if source/low-pass shape or intensity domain is inconsistent.

---

### Task 1: Execute corrected edge-preserving A/B/C workflow

- [ ] Build the same 4096² displacement proxy and Gaussian-6 baseline.
- [ ] Build B/C from the exact PIL consumer-domain source array.
- [ ] Pass representation-parity preflight before Blender.
- [ ] Run the same Blender gate for A/B/C and preserve metrics + six legal renders per variant.
- [ ] Enforce identical correspondence, alpha core, bump distance, bump strength and target scope across all variants.
- [ ] Verify renderer residual scale agrees with the preflight consumer-domain scale.
- [ ] Create comparison sheets for face close, 3/4 close, front and 3/4 full.
- [ ] Assert no raw/derived DRL maps are redistributed.
- [ ] Download artifact and judge scar suppression against pore/fine-wrinkle retention.

## Decision Contract

- `KEEP_GAUSSIAN6` only if both valid bilateral variants lose useful micro-detail or add artifacts.
- `KEEP_BILATERAL32` or `KEEP_BILATERAL64` only if representation parity passes and the oval scar is materially suppressed while pores remain visible.
- `NEED_STRUCTURE_AWARE_REFINEMENT` if parity passes but scar persists in all variants.
- `INVALID_COMPARISON` if builder/consumer representation parity fails.
