# Nonfinal GLB Runtime Pipeline v1 — Layer 07 Task 5 Decision

Date: 2026-08-10
Proposal: `cinematic-3d-character-website-solution-r1@1.0`
Selected Skill: `three_d_asset_runtime_pipeline`
Skill execution scope: provenance/runtime-loading subset only

## Scope

This node proves that a legally reusable, provenance-tracked GLB fixture can cross the approved runtime asset boundary and be loaded through Three.js without weakening the final-character approval gate. It does not create, adapt, approve, purchase, commission, or visually validate the cinematic master character.

## Project-specific Skill translation

1. `source_and_provenance`: required and enforced by an explicit runtime manifest plus a human-readable provenance record.
2. `master_runtime_separation`: this generic fixture is classified as `nonfinal_test_fixture`, not as either the project cinematic master asset or its final runtime derivative. Therefore it cannot satisfy the final master→runtime evidence requirement.
3. `runtime_export_handoff`: the approved Layer 05 route is GLB; this task consumes an already-authored upstream GLB without transformation.
4. `runtime_validation_evidence`: loader contract and browser loading smoke are allowed; offline presence alone is insufficient.
5. `rig_animation_compatibility_boundary`: no rigging or animation-authoring claim is made from this fixture.
6. `tool_vendor_decoupling`: no new engine, vendor, DCC, compression format, or cloud dependency is introduced.

## Fixture selection

The KhronosGroup sample `Box.glb` was chosen intentionally because it is a small standards-oriented loader fixture with an explicit license trail. It is not character-shaped and is therefore difficult to confuse with the project's final cinematic-quality character. The runtime path retains the plan-prescribed filename `/assets/test-character.glb`, but the manifest and provenance record explicitly classify it as nonfinal and non-equivalent.

## Loader contract

- Input: a typed `RuntimeAssetManifest` and a loader boundary.
- Success: returns root `Object3D`, animation clips, and the exact source manifest.
- Failure: throws typed `AssetLoadError` with code `asset_load_failed`; no `undefined`/silent fallback.
- Production adapter: Three.js `GLTFLoader`.
- Meshopt/KTX2: not wired because this fixture does not require either; deferred per the approved plan.

## Reapproval boundary

Return upstream before treating any asset as the final character, purchasing/commissioning an asset, changing the approved runtime format/engine route, or claiming final master/runtime quality evidence from this fixture.
