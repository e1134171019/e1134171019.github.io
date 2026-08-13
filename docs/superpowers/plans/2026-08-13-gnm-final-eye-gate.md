# GNM Final Eye Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze one final GNM eye material/anatomy candidate on top of the already frozen authored skin without reopening skin or micro-surface optimization.

**Architecture:** Reuse the validated GNM nested semantic partition (`pupil > iris > sclera`, cornea as a separate exterior shell) from `experiment/gnm-head-eye-gate`, but execute from the current `experiment/gnm-authored-skin-gate` baseline. Add pure NumPy eye-partition/alignment contracts first, then patch only the eye layer in the authored-skin Blender gate. The skin shader, Bilateral32 micro-surface, source correspondence and authored-skin numeric contract are immutable inputs.

**Tech Stack:** Python 3.12, NumPy, pytest, Blender/Eevee, GitHub Actions, Google GNM v3.

## Global Constraints

- Branch only: `experiment/gnm-final-eye-gate`.
- Never modify `main`, merge, deploy, publish, purchase, commission, or set `final_character_adopted: true`.
- Preserve `PASS_FREEZE_SKIN_MATERIAL_STAGE`; eye code must not alter authored skin maps, correspondence, roughness/specular mapping, SSS, or Bilateral32 bump parameters.
- GNM source remains pinned to commit `98450b3c943101d5859ac1ceb7331ec918ebc321` and NPZ SHA-256 `868075bbb172fc6574ece89338e21fdc0efe0be91ca4e6e5c3166a1a97840055`.
- Final eye anatomy partition: pupil overrides iris; iris overrides sclera; cornea remains an independent exterior shell.
- One eye material candidate only. No A/B/C appearance search.
- Artifact output contains renders + metrics/evidence only; no raw external material maps.

---

### Task 1: Eye partition and alignment math

**Files:**
- Create: `tests/experiments/test_eye_gate_math.py`
- Create: `tools/experiments/eye_gate_math.py`
- Create: `.github/workflows/gnm-final-eye-math-unit.yml`

**Interfaces:**
- Consumes: Boolean per-face membership arrays and Nx3 semantic point arrays.
- Produces: `priority_eye_partition(...)` and `measure_eye_alignment(...)`.

- [ ] **Step 1: Write the failing test** for nested partition priority, centered pupils, bilateral symmetry, and deliberate gaze mismatch.
- [ ] **Step 2: Run the unit workflow and verify RED** because `tools.experiments.eye_gate_math` does not exist.
- [ ] **Step 3: Implement minimal NumPy functions** only.
- [ ] **Step 4: Re-run and verify GREEN** with all tests passing.

### Task 2: Single final-eye Blender candidate

**Files:**
- Create: `tools/experiments/gnm_final_eye_gate.py`
- Create: `.github/workflows/gnm-final-eye-gate.yml`

**Interfaces:**
- Consumes: frozen authored-skin gate, pinned GNM v3 geometry and semantic groups.
- Produces: `artifacts/gnm-final-eye-gate/eye_metrics.json`, front/3Q/close renders, contact sheet.

- [ ] **Step 1: Re-run eye math unit regression.**
- [ ] **Step 2: Validate non-empty sclera/iris/pupil/cornea partitions and eye alignment metrics.**
- [ ] **Step 3: Keep frozen skin unchanged and replace diagnostic eye materials only.** Sclera is warm off-white/non-emissive; iris is neutral dark brown with deterministic procedural radial variation; pupil is near-black; cornea uses low roughness and dielectric IOR with safe transmission when supported.
- [ ] **Step 4: Render `front.png`, `face_close.png`, `face_3q_close.png`, `three_quarter_right.png` and a contact sheet.**
- [ ] **Step 5: Enforce numeric/scope contract.** Required eye groups non-empty, pupil-to-iris normalized offsets bounded, bilateral gaze mismatch bounded, render outputs non-flat, `skin_frozen: true`, `final_character_adopted: false`.

### Task 3: Visual freeze review and state persistence

**Files:**
- Create only after actual render review passes: `docs/validation/gnm-final-eye-gate.md`
- Update: Drive `PROJECT｜Cinematic 3D Character Website｜流程狀態`

- [ ] **Step 1: Download workflow artifact and visually inspect front, face-close and 3Q-close renders.**
- [ ] **Step 2: Reject on any fatal defect:** glowing sclera, dead-flat iris/pupil, absent corneal catchlight, cross-eye/gaze mismatch, eye/socket penetration, or close-up breakdown.
- [ ] **Step 3: If no fatal defect, record `PASS_FREEZE_EYE_STAGE`; otherwise record concrete failure only.**
- [ ] **Step 4: Keep `final_character_adopted: false`; next node is Brows/Lashes only after eye freeze.
