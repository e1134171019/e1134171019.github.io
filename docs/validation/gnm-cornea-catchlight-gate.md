# GNM Cornea Catchlight Gate

Date: 2026-08-13
Branch: `experiment/gnm-cornea-catchlight-fix`
Parent eye baseline: `experiment/gnm-final-eye-gate@c3aec3a6bf9dc8274ac642002c995f615213db07`

## Scope

One bounded material-only correction for the concrete Eye Gate defect `cornea wet catchlight not visible`.

Frozen invariants:
- authored skin remains `PASS_FREEZE_SKIN_MATERIAL_STAGE`
- micro-surface remains `bilateral32`
- eye geometry unchanged
- gaze/alignment unchanged
- sclera/iris/pupil materials unchanged
- lighting unchanged
- cameras unchanged
- no merge to `main` or project branch
- no deploy/publish
- `final_character_adopted: false`

## TDD

Initial runner-environment failure (not counted as RED):
- run `31695132171`
- failure: `pytest` absent from runner

Valid RED:
- run `31695197345`
- job `94431290125`
- expected failure: `ModuleNotFoundError: No module named 'tools.experiments.cornea_material_contract'`

GREEN:
- helper commit `434a83256ace2846b0007ce1b1e72700b882acbf`
- run `31695246365`
- conclusion: success

Material contract:
- IOR: `1.376`
- roughness: `0.012`
- Fresnel boost: `1.35`
- transparent base: `true`
- alpha blending: `false`
- reflection lobe: `principled_metallic_white`

## 3D Render Gate

Wrapper commit: `8bfbcf8d1d2f9e1d99f4d244066c9dc43e40694c`
Workflow commit: `f30a3fb76ab5daa456d84add32ddea731b0a9d42`
Workflow run: `31695445506`
Job: `94432066783`
Conclusion: success

The workflow passed:
- immutable failed-eye baseline guard
- frozen authored-skin source guard
- pinned GNM v3 acquisition/hash
- frozen DRL input acquisition
- authored skin + eye + cornea unit regressions
- Blender execution over the actual 3D character
- cornea numeric/scope contract
- redistribution hygiene
- artifact upload

Artifact:
- id: `9179215631`
- name: `gnm-cornea-catchlight-gate`
- digest: `sha256:23d5eb4f785b94fa81027ee764cb280ee2df23d2adf81b2e22f7cf1aa6c8e157`

## Visual Review

Reviewed actual fixed-camera renders:
- `face_close.png`
- `face_3q_close.png`
- `front.png`
- `00_gnm_cornea_catchlight_review_contact_sheet.jpg`

Observed:
1. The requested wet catchlight is now clearly visible on both corneal shells.
2. However, the corneal surface renders as a dark/black opaque-looking shell in the current Eevee software-render path.
3. The dark shell obscures the sclera, iris, and pupil over most of each visible eye.
4. The defect repeats in both frontal close-up and 3/4 close-up, so it is not a single-view artifact.
5. Skin, facial geometry, and eye alignment remain unchanged.

Interpretation:
- The material hypothesis succeeded at producing a specular catchlight but failed at transparent compositing.
- The `Transparent BSDF + Fresnel reflective lobe` construction does not composite over the nested eye surfaces as intended in this current Eevee material/render configuration.
- This is a renderer/material architecture issue for this approach, not a remaining roughness/IOR parameter-tuning issue.

## Decision

`FAIL_EYE_STAGE_CORNEA_CORRECTION_EXHAUSTED`

The bounded single cornea correction has been consumed. Do not continue parameter-search A/B/C variants under this gate.

Eye stage is **not frozen**.
Brows/Lashes remains **blocked**.

A future continuation requires a new explicit material/render architecture decision for transparent cornea/refraction parity rather than another numeric tweak to the current shader.

PNG files remain validation renders only. The actual change under test is the reproducible 3D Blender material/shader pipeline on the GNM eye geometry.
