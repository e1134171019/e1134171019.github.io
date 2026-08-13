# GNM Authored Skin Material Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Advance the accepted Bilateral32 GNM micro-surface result into one bounded authored-skin material candidate with low-frequency skin color, gloss-derived roughness, specular response, and the already-selected high-frequency displacement layer, then produce render-only evidence for GPT visual review.

**Architecture:** Keep `experiment/gnm-appearance-gate@23857ac903231c20b168a8e3c5a3cb2b463eb335` immutable and work only on `experiment/gnm-authored-skin-gate`. Reuse the verified DRL→GNM geometric/UV correspondence from `drl_gnm_diffuse_transfer_gate.py`; author skin channels from privately extracted DRL PBR maps, remove identity-scale diffuse detail before transfer, and never upload raw or derived texture maps. The gate emits only renders, source/proxy metadata, hashes, and JSON metrics. This is an experimental material gate, not final character adoption.

**Tech Stack:** Python 3, NumPy, Pillow, OpenCV (workflow preprocessing), Blender/Eevee, GitHub Actions, Google GNM v3 pinned at `98450b3c943101d5859ac1ceb7331ec918ebc321`, Digital Reality Lab Marcus PBR sample archive fixed at 928494471 bytes.

## Global Constraints

- Formal project: true; experimental branch only.
- Do not modify `main`, `project/cinematic-3d-character-website`, or `experiment/gnm-appearance-gate`.
- Bilateral32 is frozen as the selected micro-surface low-pass; do not reopen Gaussian/Bilateral A/B/C optimization.
- Reuse the existing DRL→GNM correspondence and GNM `skin ∩ hockey_mask` semantic scope.
- DRL raw/derived diffuse, glossiness, specular, displacement, geometry, and temporary GNM textures must never be uploaded as artifacts.
- Render evidence may be uploaded; source usage evidence and hashes may be uploaded.
- No final character adoption, purchase, commission, merge, deploy, or public release.
- One material candidate only; no new unbounded A/B/C search loop.

---

### Task 1: Pure authored-skin math contract (TDD)

**Files:**
- Create: `tests/experiments/test_authored_skin_math.py`
- Create: `tools/experiments/authored_skin_math.py`
- Create: `.github/workflows/drl-gnm-authored-skin-unit.yml`

**Interfaces:**
- Produces: `author_low_frequency_skin(rgb) -> (authored_rgb, stats)`
- Produces: `gloss_to_roughness(gloss) -> (roughness, stats)`
- Produces: `specular_to_level(specular) -> (level, stats)`
- Values are normalized floats in `[0, 1]`; output images are finite and bounded.

- [ ] **Step 1: Write the failing tests**
  - High-frequency checker detail must be strongly attenuated by authored base skin while broad red/yellow field variation remains measurable.
  - Gloss mapping must be monotonic inverse and bounded to the skin roughness interval `[0.38, 0.62]`.
  - Specular mapping must be monotonic and bounded to `[0.35, 0.55]`.
  - Constant input must remain finite and bounded without divide-by-zero.

- [ ] **Step 2: Run RED in GitHub Actions**
  - Expected failure: `ModuleNotFoundError: tools.experiments.authored_skin_math`.

- [ ] **Step 3: Implement minimal math**
  - Downsample/blur/re-expand diffuse to remove identity-scale detail, separate broad chroma/luma variation from median, and re-center around a fixed authored skin base.
  - Robust percentile normalization for gloss/specular channels.

- [ ] **Step 4: Run GREEN**
  - `python -m pytest tests/experiments/test_authored_skin_math.py -q` passes.

---

### Task 2: Authored PBR skin render gate

**Files:**
- Create: `tools/experiments/drl_gnm_authored_skin_gate.py`
- Create: `.github/workflows/drl-gnm-authored-skin-gate.yml`

**Interfaces:**
- Consumes: `DRL_OBJ`, `DRL_DIFFUSE`, `DRL_GLOSSINESS`, `DRL_SPECULAR`, `DRL_DISPLACE_PROXY`, `DRL_DISPLACE_LOWPASS`, `GNM_MODEL`.
- Reuses: `tools/experiments/drl_gnm_diffuse_transfer_gate.py` correspondence and `micro_height_from_lowpass`.
- Produces render-only artifact: `front.png`, `three_quarter_right.png`, `three_quarter_left.png`, `side_right.png`, `face_close.png`, `face_3q_close.png`, contact sheet, and `authored_skin_metrics.json`.

- [ ] **Step 1: Build private proxies**
  - Extract exact DRL OBJ, diffuse, glossiness, specular, and displacement entries from the verified archive.
  - Resize color/material maps to bounded working proxies.
  - Build 16-bit displacement proxy and fixed Bilateral32 low-pass.

- [ ] **Step 2: Compose one material candidate**
  - Base Color: authored low-frequency skin only; no identity-scale DRL diffuse detail.
  - Roughness: regional response derived from DRL glossiness and constrained to `[0.38, 0.62]`.
  - Specular IOR Level / Specular: regional response derived from DRL specular and constrained to `[0.35, 0.55]`.
  - Normal: accepted Bilateral32 high-frequency displacement residual only, `0.35 mm`, strength `0.32`.
  - Subsurface: bounded diagnostic weight; do not claim calibrated tissue transport.

- [ ] **Step 3: Numeric and scope gate**
  - Correspondence remains within the accepted high-confidence contract used by the micro-surface gate.
  - No invalid correspondence leaks into authored channel maps.
  - Authored color high-frequency suppression is recorded.
  - Roughness/specular ranges are finite and within contract.
  - Metrics explicitly state `final_character_adopted: false` and `visual_decision: PENDING_GPT_VISUAL_REVIEW`.

- [ ] **Step 4: Artifact hygiene**
  - Delete all temporary GNM transfer textures before artifact upload.
  - Assert artifact directory contains no OBJ/FBX/ZTL/EXR or raw/derived material maps.

---

### Task 3: Final material-stage review

**Files:**
- No source modification unless a hard gate fails.

- [ ] **Step 1: Download the successful workflow artifact**
- [ ] **Step 2: Inspect `face_close`, `face_3q_close`, front and 3/4 views**
- [ ] **Step 3: Decide exactly one result**
  - `PASS_FREEZE_SKIN_MATERIAL_STAGE` if skin no longer reads as flat/plastic and no new fatal transfer artifact is visible.
  - `FAIL_MATERIAL_STAGE` only for a concrete fatal visual defect; record the defect without opening another broad optimization search.
- [ ] **Step 4: Do not merge or deploy**
