# GNM Final Eye Gate Validation

Date: 2026-08-13

## Scope

- branch: `experiment/gnm-final-eye-gate`
- parent state: `PASS_FREEZE_SKIN_MATERIAL_STAGE`
- skin frozen: `true`
- final_character_adopted: `false`
- main modified: `false`
- merged: `false`
- deployed: `false`

## TDD evidence

RED:
- workflow: `GNM Final Eye Math Unit`
- run: `31685980343`
- expected failure: `ModuleNotFoundError: No module named 'tools.experiments.eye_gate_math'`

GREEN:
- workflow run: `31686050134`
- final eye math contract: PASS

## Full render gate

- workflow: `GNM Final Eye Gate`
- run: `31686280609`
- head: `c13d20d6689fdeba752792c6afff3fd7a5e2ebac`
- artifact id: `9175644471`
- artifact digest: `sha256:10c65fa9e6881cf1ca38b1f7d3952595b234ea168c3e8499a9440cdcc3d19d66`
- CI conclusion: success
- frozen authored-skin source boundary: PASS
- pinned GNM v3 source/hash: PASS
- authored-skin + eye unit regressions: PASS
- Bilateral32 frozen proxy: PASS
- Blender final-eye render: PASS
- eye numeric/scope contract: PASS
- raw/derived material redistribution guard: PASS

## Eye numeric evidence

Semantic partition face counts:
- sclera: `864`
- iris: `384`
- pupil: `240`
- cornea: `1536`

Alignment:
- max pupil-to-iris offset ratio: `0.014255697118639705`
- bilateral gaze mismatch ratio: `0.00008892535489773222`
- sclera bilateral size mismatch ratio: `0.000001798696908329091`

These values establish that the eye anatomy is centered, bilaterally coherent, non-cross-eyed, and structurally valid. They do not establish cinematic appearance.

## Actual visual review

Reviewed actual artifact renders:
- `front.png`
- `three_quarter_right.png`
- `face_close.png`
- `face_3q_close.png`
- `00_gnm_final_eye_review_contact_sheet.jpg`

Positive observations:
- no visible cross-eye or bilateral gaze defect;
- no obvious iris/pupil semantic overlap corruption;
- no obvious socket penetration or displaced eyeball in front/3Q;
- sclera/iris/pupil are readable at close range;
- frozen authored skin remains visually intact.

Fatal visual defect:
- corneal wet catchlight/reflection is not visibly established in close-up or 3Q close-up;
- as a result the eye surface still reads too flat / doll-like rather than as a wet dielectric ocular surface;
- iris procedural variation is also too weak to materially break the flat appearance at the current review scale.

## Decision

`FAIL_EYE_STAGE_CONCRETE_DEFECT_CORNEA_CATCHLIGHT`

This is a visual failure only. Geometry/alignment/numeric contracts passed.

Do **not** reopen skin, roughness/specular skin mapping, SSS, or Bilateral32 micro-surface.

Next allowed correction is one bounded Eyes-only change:
1. replace the current weak alpha/transmission cornea response with a stronger, explicitly reflective wet cornea shell;
2. keep GNM eye geometry and gaze unchanged;
3. preserve neutral/non-identity iris intent;
4. re-render the same fixed front / face-close / 3Q-close review set;
5. freeze Eyes only if an actual visible corneal catchlight is present and no new occlusion/penetration defect appears.

Next project node remains: `Eyes`.
Brows/Lashes are blocked until `PASS_FREEZE_EYE_STAGE`.
