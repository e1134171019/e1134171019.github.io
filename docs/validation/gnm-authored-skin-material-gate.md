# GNM Authored Skin Material Gate — Final Review

Date: 2026-08-13
Branch: `experiment/gnm-authored-skin-gate`
Base character experiment: `experiment/gnm-appearance-gate@23857ac903231c20b168a8e3c5a3cb2b463eb335`
Material implementation commit: `dda2e693535be33e8a664d2502c29c6434d334ee`
Render workflow commit: `c01044c32b3612a2aa09182d8024ae5fa80c5fd2`

## Decision

`PASS_FREEZE_SKIN_MATERIAL_STAGE`

This freezes the skin-material stage only. It does **not** adopt the final character, approve final eyes/hair/brows/lashes, merge to the formal website branch, deploy, or publish.

## TDD evidence

- RED run: `31683314316`, job `94393532430`.
- Expected failure: `ModuleNotFoundError: No module named 'tools.experiments.authored_skin_math'` after checkout, Python setup, and dependency install succeeded.
- GREEN run: `31683511240`, job `94394145180`.
- Result: authored-skin math contract passed.

## Render / numeric evidence

Workflow run: `31683914857`
Job: `94395437580`
Artifact: `9174762392`
Artifact digest: `sha256:2763f21bcefca18294c5e79ff37bfbdd6ac27ba809e6e685bd75476663bd6ee9`

All workflow stages passed: pinned GNM acquisition, DRL PBR channel acquisition, unit regression, proxy construction, frozen Bilateral32 low-pass, Blender render, numeric/scope contract, redistribution hygiene, and artifact upload.

Key metrics:

- correspondence valid fraction: `0.8277950662`
- full-alpha core fraction: `0.4188754158`
- invalid correspondence with nonzero alpha: `0`
- invalid face index count: `0`
- authored-base high-frequency energy ratio: `0.1032332123`
- roughness target range: `[0.38, 0.62]`
- specular target range on valid skin: approximately `[0.45, 0.45]`
- micro-surface selection: `bilateral32`
- bump distance: `0.35 mm`
- bump strength: `0.32`
- final character adopted: `false`

## Visual review

Reviewed render evidence:

- `face_close.png`
- `face_3q_close.png`
- `front.png`
- `three_quarter_right.png`
- contact sheet / remaining fixed views

Material-stage observations:

1. The skin no longer reads as the prior uniform diagnostic surface. Broad skin color variation, localized roughness/highlight response, and the accepted Bilateral32 micro-surface are visible.
2. No fatal UV seam, donor-texture displacement, invalid-correspondence leak, or renewed orange-peel micro-surface artifact was observed.
3. The nose/cheek highlight is somewhat oily under the diagnostic light but remains coherent with the roughness map and is not a stage-blocking transfer defect.
4. A localized warm/red jaw variation remains visible but does not create a seam or anatomical mismatch severe enough to reject the material stage.
5. The DRL specular input is effectively constant over the accepted skin UV support (`robust_span: 0.0`), so spatial highlight variation in this candidate is primarily driven by gloss-to-roughness rather than a varying specular-level map. This is explicitly disclosed and must not be described as regional specular variation.
6. Remaining mannequin appearance is now dominated by unfinished eyes, eyebrows/lashes, hair, and final character presentation rather than a fatal skin-material defect.

## Frozen material contract

- Base Color: authored low-frequency skin only; identity-scale donor diffuse detail is suppressed.
- Roughness: bounded inverse gloss, `[0.38, 0.62]`.
- Specular level: bounded dielectric response; effectively `0.45` over accepted skin UV in current source evidence.
- Micro normal: frozen Bilateral32 displacement residual only.
- DRL normal map: not used in this stage, to avoid double-normal stacking against the frozen micro layer.
- SSS: diagnostic weight only; not calibrated tissue transport.
- Raw/derived DRL PBR maps: not uploaded in workflow artifact.

## Stop condition

Do not reopen Gaussian/Bilateral micro-surface optimization or create another broad skin A/B/C search loop unless a later fixed-site-lighting validation exposes a concrete fatal material defect.

## Next character node

Proceed to the missing human-recognition stack:

`eyes → brows/lashes → hair silhouette/material → fixed cinematic character review`

Final Character Freeze Gate remains pending.
