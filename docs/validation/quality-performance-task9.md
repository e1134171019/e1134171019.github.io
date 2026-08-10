# Layer 07 Task 9 — Quality Policy and Performance Instrumentation Verification

## Execution identity

- project: `Cinematic 3D Character Website`
- layer: `07`
- task: `Task 9 — Quality Policy and Performance Instrumentation`
- completed_at: `2026-08-10T08:21:00+08:00`
- system_route: `formal / single_domain / website / web_development`
- selected_skill: `realtime_3d_performance_optimization`
- skill_source_commit: `858c3e58e1f35ea3a5746c4df6003ffbd1c4dad0`
- skill_execution_lifecycle: `PARTIAL`
- handbook: `Web 專案開發規範 v1.0 / active / bound`
- formal_workspace: `/mnt/data/cinematic-3d-character-website/.worktrees/layer07-v1`
- formal_branch: `layer07/v1`
- source_commit: `08f7ccf9b28810cfb4a93966f3791de4cd4e0f7f`
- decision_reference: `docs/decisions/quality-performance-v1.md`
- decision_sha256: `02900d27eb5fcfa5a07805b918b83174b796845f88c4a2a78ba60b1da149046b`

## Implemented source

- `src/quality/PerformanceMonitor.ts`
  - sha256: `13725778ec4888bf72e90e6d70216da0bb9ec22a8e2e521638e4a3f585909a8c`
- `src/quality/QualityPolicy.ts`
  - sha256: `7884c7e84214048c6d907ced85a8cb0b722f6618483327d301aa1d2c919e1328`
- `src/quality/QualityPolicy.test.ts`
  - sha256: `2231cab51621f488adf36c50c162e0d16ca0518383f7489b76f50c71ee66cec1`

## Contract implemented

The policy consumes the already-approved project thresholds rather than creating new acceptance budgets:

- primary median target: `60 FPS`
- sustained degradation trigger: `<45 FPS`
- minimum interactive floor: `30 FPS`
- quality order: `high -> balanced -> minimumInteractive`
- first degradation target: `optionalEffects`
- second degradation target: `environment`
- character identity/material fidelity degradation target emitted by this policy: `none`
- unsupported memory evidence: `null`, never synthetic zero
- startup-to-interactive timing: explicitly measured from caller-provided timestamps
- rolling measurement window: bounded and caller-configured; Task 9 does not invent a project-wide numeric definition of “sustained”

## TDD RED evidence

Authoritative refined RED:

- GitHub Actions run: `31343766691`
- job: `93321771767`
- artifact: `9046616107`
- artifact SHA256: `d823bfb35a11050056779d04b38f9d71df410f246ea094b895db0f9c1e0eb244`
- dependency install before failure: `PASS`
- test source identity before failure: `PASS`
- intended failure: unresolved `./PerformanceMonitor`
- false RED: `false`

This RED was observed before the production quality/performance modules existed.

## Debugging corrections

### Floating-point boundary defect

The first GREEN attempt exposed one real behavior defect at the exact 30 FPS boundary. Deriving FPS through `1000 / (1000 / 30)` yields `29.999999999999996` in JavaScript, so comparing the derived value directly with `>= 30` incorrectly rejected the floor boundary.

Root-cause correction: threshold decisions compare measured frame-time values with `1000 / targetFPS`; FPS remains a derived reporting metric. This preserves the accepted boundary without epsilon guessing.

Rejected attempt evidence:

- run: `31343922691`
- job: `93322203954`
- targeted result: `7/8 PASS`
- artifact: `9046664293`
- artifact SHA256: `e538e53f8a110889624699a5e52e083254d703e53282c019e73966afa1ef386b`

### CI executor-mirror build defect

After the policy logic passed, a subsequent run reached `51/51` unit tests but Vite failed because the temporary CI mirror intentionally did not contain the future Task 11 composition root `src/main.ts` while `index.html` references it.

This was not treated as a production Task 9 defect. The already-established executor pattern was restored: GitHub Actions generates a runner-only minimal `src/main.ts` solely for build verification. No formal Task 11 source was added early.

Rejected build attempt evidence:

- run: `31344045198`
- job: `93322537388`
- targeted tests: `8/8 PASS`
- full unit regression: `51/51 PASS across 8 files`
- Vite build: `FAIL — missing executor-mirror src/main.ts`
- artifact: `9046704713`
- artifact SHA256: `28c4bd63413225a781b30f636f44b65819a19059b3227379da62425149af0f75`

## Fresh GREEN verification

Authoritative final Task 9 GREEN:

- GitHub Actions run: `31344124732`
- job: `93322756434`
- head SHA: `42f28da8846747a78581c9872fdcbe264c103738`
- exact Task 9 source hash checks: `PASS / PASS / PASS`
- targeted Task 9 tests: `8/8 PASS`
- full unit regression: `51/51 PASS across 8 files`
- strict TypeScript: `PASS`
- Vite production build: `PASS`
- artifact: `9046728524`
- artifact SHA256: `fc64d33ffbfe745bb123ddcebd578f95fa550fdce1767552331d9bead11f3fc6`
- executor-only main mirror: `generated in CI only; not formal project source`

## Skill lifecycle / evidence boundary

`realtime_3d_performance_optimization` remains `PARTIAL` for this project. Task 9 has executed the target-policy and instrumentation subset with synthetic deterministic verification, but the Skill's full measure-first lifecycle still requires a representative runtime workload, actual bottleneck identification, a measured optimization change, before/after evidence, and real target-environment regression evidence.

The current non-final Box GLB is explicitly non-representative of final cinematic character geometry, skin, eyes, hair, textures, rig, animation, deformation, material cost, or GPU pressure.

## Non-claims

- final cinematic character performance acceptance: `false`
- representative cinematic character runtime baseline: `false`
- real discrete-GPU acceptance: `false`
- real integrated-GPU acceptance: `false`
- real target browser/device matrix acceptance: `false`
- final 10-minute stability acceptance: `false`
- final >20% memory-growth rule acceptance: `false`
- final character asset adopted: `false`
- production deployment: `false`
- production credentials used: `false`
- paid action performed: `false`

## Result

- Task 9 policy/instrumentation scope: `GREEN`
- architecture changed: `false`
- outcome contract changed: `false`
- reapproval required: `false`
- project complete: `false`
- next formal gate: `Task 10 — Minimal UI States and Accessible Runtime Status`
