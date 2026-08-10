# Task 5 Validation — Provenance-Tracked Nonfinal GLB Loading

Date: 2026-08-10
Task: `layer07-task5-provenance-tracked-nonfinal-glb-loading`
Proposal: `cinematic-3d-character-website-solution-r1@1.0`
Selected Skill: `three_d_asset_runtime_pipeline`
Skill execution scope: provenance/runtime-loading subset only

## Result

Status: GREEN for the Task 5 nonfinal-fixture scope.

This result proves the approved Three.js runtime can load a legally reusable, provenance-tracked GLB fixture in a real headless browser runtime while preserving the explicit `finalAsset: false` and `equivalentToFinal: false` boundary. It does not prove final cinematic character quality, final master-to-runtime adaptation, rigging quality, animation quality, compression policy, or real-GPU visual acceptance.

## Authoritative formal source

Formal worktree: `.worktrees/layer07-v1`
Formal branch: `layer07/v1`
Pre-Task-5 base commit: `cd47564`

Task 5 source SHA-256 values verified identically in the CI executor:

- `src/assets/AssetManifest.ts`: `91420e4f4dcad132d9547c1a6fb6cb51fba1de9591ad3c259d69e588a05d35b2`
- `src/assets/AssetLoader.ts`: `b86c2719f0e24c438500976d66bff5581fd20c203d7d0093fad9528128c0a4cd`
- `src/assets/AssetLoader.test.ts`: `2d8eb3efb77b4a8af9b35d682617b24469077be6352770b559ea456648a51682`

## Asset provenance and integrity

Fixture: KhronosGroup glTF Sample Assets `Box.glb`
Asset owner/artist: Cesium
Distribution repository: `KhronosGroup/glTF-Sample-Assets`
Pinned source commit: `2bac6f8c57bf471df0d2a1e8a8ec023c7801dddf`
Pinned source path: `Models/Box/glTF-Binary/Box.glb`
License: `CC-BY-4.0`
Runtime path: `/assets/test-character.glb`
Byte length: `1664`
Upstream/source Git blob SHA-1: `95ec886b6b92b134291fd41d34ac9d5349306e0a`
Local and CI SHA-256: `ed52f7192b8311d700ac0ce80644e3852cd01537e4d62241b9acba023da3d54e`
glTF magic/version/declared length: `glTF` / `2` / `1664`
Exact upstream blob match: yes
Adaptations: none
Final asset: no
Equivalent to final asset: no

Human-readable provenance is recorded in `docs/assets/test-asset-provenance.md`.

## TDD evidence

RED run: GitHub Actions `31327906736`

Expected failure observed after dependencies installed:

`Failed to resolve import "./AssetLoader" from "src/assets/AssetLoader.test.ts"`

At that point `AssetLoader.ts` and `AssetManifest.ts` did not exist. This establishes the loader contract test preceded production implementation.

Initial targeted GREEN run: `31328000321`

- `src/assets/AssetLoader.test.ts`: 2/2 PASS

Final verification run: `31328487763`

- Task 5 targeted: 2/2 PASS
- Full unit regression: 27/27 PASS across 4 files
- Strict TypeScript + Vite build: PASS (`tsc --noEmit && vite build`)
- Task 5 formal-source SHA-256 match: PASS
- Fixed GLB SHA-256 / Git blob / glTF integrity: PASS
- Browser GLTFLoader smoke: PASS

Final CI executor versions:

- Node `v22.23.1`
- npm `10.9.8`
- Three.js `0.185.1`
- TypeScript `7.0.2`
- Vite `8.2.1`
- Vitest `4.1.10`

## Browser runtime evidence

Browser: Google Chrome `150.0.7871.128`, headless CI environment.

The executor-only smoke page imported the formal `AssetLoader.ts` and `AssetManifest.ts`, invoked the production default `GLTFLoader`, and loaded `/assets/test-character.glb` through Vite's actual HTTP serving path.

Observed final DOM result:

```json
{
  "status": "pass",
  "assetId": "khronos-box-nonfinal-loader-fixture",
  "finalAsset": false,
  "equivalentToFinal": false,
  "rootType": "Group",
  "clipCount": 0
}
```

This is loader/runtime evidence only. It is not a character rendering or real-GPU visual-quality acceptance result.

## Verification infrastructure correction

Two pre-final browser-smoke runs were intentionally rejected:

1. Run `31328138097` — browser output was written inside Vite's watched root, causing Vite page reloads and invalidating the snapshot.
2. Run `31328271927` — watcher interference was removed, but the `--dump-dom` snapshot still occurred before asynchronous module/GLTF loading completed.
3. Diagnostic run `31328380357` preserved the actual DOM and confirmed the page remained `data-task5="pending"` with no loader/module exception.
4. Final run `31328487763` added only a bounded `--virtual-time-budget=5000` to allow the asynchronous loader operation to complete before the DOM snapshot. The full final gate then passed.

No production source or fixture bytes changed during these browser-smoke debugging iterations.

## Execution-environment boundary

Formal Sandbox remains unable to install the existing dependency graph because its internal npm mirror returns a 404 for `xmlchars@2.2.0`. The already-approved GitHub Actions CI executor bridge was therefore used for executable Node/browser verification. Formal source authority remains the isolated Sandbox Git worktree; source SHA-256 equality was checked before accepting the CI result.

Architecture changed: no
Scope expanded: no
New engine/framework/vendor dependency introduced: no
KTX2 required by this fixture: no
Meshopt required by this fixture: no

## Explicit non-claims

This Task 5 result does NOT claim:

- final character selection or approval;
- cinematic master asset approval;
- final `web_runtime_asset` approval;
- master-to-runtime adaptation quality;
- human character topology/material/hair/skin quality;
- rigging or animation authoring quality;
- final animation-clip availability;
- real discrete/integrated GPU acceptance;
- final performance/FPS/memory targets;
- production deployment or public release.

## Next gate

`layer07-task6-character-locomotion`

Task 6 may consume a Three.js `Object3D` root and explicit input/desired-state contracts, but it must not reinterpret this Box fixture as the final character or as character-quality evidence.
