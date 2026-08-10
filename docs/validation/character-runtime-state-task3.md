# Task 3 Validation — Character / Runtime State Machines

Date: 2026-08-10
Decision: `cinematic-3d-character-runtime-state-v1`
Formal workspace: `/mnt/data/cinematic-3d-character-website/.worktrees/layer07-v1`
CI executor mirror: `e1134171019/e1134171019.github.io@runtime-bootstrap/cinematic-3d`

## Scope validated

- `KeyboardInput/InputSnapshot` named-action handoff into character desired-state reducer.
- Explicit `presentationIdle -> interactiveIdle -> move/turn/action/stop/returnToIdle` desired-state behavior.
- `primaryAction` precedence and sticky action semantics until explicit `actionCompleted`.
- Defensive neutralization of contradictory movement/turn pairs.
- Explicit browser runtime lifecycle state and typed fallback errors.
- Pure reducer boundary: no DOM, renderer, animation, camera, asset, persistence, or network side effects.

## TDD RED evidence

Final valid RED:
- GitHub Actions run: `31325374307`
- job: `93274762006`
- artifact: `9041365713`
- artifact digest: `sha256:f91fd39dc209039dc80eea9696635c8773911645bf3e6b0ab2b3fe5187ed33ea`
- result: expected RED verifier PASS
- intended product test failure: Vite/Vitest could not resolve `./CharacterState` because the production reducer did not exist yet.
- dependency install completed successfully before the test, so this is not a package/bootstrap false RED.

After the RED evidence was captured, the RED workflow was changed to manual `workflow_dispatch` only so expected-failure verification does not remain a permanent push failure.

## GREEN evidence

Final fresh GREEN after exact source-byte synchronization:
- GitHub Actions run: `31325568452`
- job: `93275248683`
- artifact: `9041420972`
- artifact digest: `sha256:08702978b779c14e49bfc23bf6234e6b62602235a8b9841c03ff4cb8067973fe`
- Task 3 state tests: `13/13 PASS`
- full unit regression: `20/20 PASS`
- strict TypeScript: PASS
- Vite production build: PASS

GREEN source hashes recorded by CI and matched against the formal workspace:

```text
445c9a13264c71d89cb9a02bd11369de565d0ca7ba10cac18a6b546a9aaa9643  src/state/state.test.ts
040c80a1296a633079765552dcff48c5178f16e8f8f924e82d7dc53ee018c1fa  src/state/CharacterState.ts
77307e42d4458b52954689e48ef3ed3a14d6fc2380fde550adb4c82b0472eeac  src/state/RuntimeState.ts
6306358f5251d1d1d02915f55604cdcaa6f4d3eb851ff5cab79f50c11817149b  src/input/InputActions.ts
```

A formatting-only mismatch in `state.test.ts` was detected during trace review. The formal test file was synchronized to the CI-tested bytes, then a second fresh GREEN run was executed. All four final hashes match that fresh run exactly. Reducer production files were unchanged by the synchronization.

## Capability review

Result: PASS for the isolated `input_action_snapshot -> character_desired_state` and typed runtime-state scope.

- raw physical keys remain isolated in the Input boundary;
- character state consumes only typed named actions/events;
- desired state and future actual animation state are not conflated;
- action completion is not guessed from input absence;
- fallback is explicit and typed;
- core reducer behavior is independently testable and deterministic.

## Project / outcome cross review

Outcome progress: ADVANCED, not project-complete.

This task closes the previously pending named-action-to-character-desired-state handoff. Remaining downstream gaps include:
- actual character transform / locomotion execution;
- animation state and `actionCompleted` producer;
- desired-state-to-animation handoff;
- camera synchronization;
- real browser/GPU integrated interaction evidence;
- final character/runtime asset integration.

No upstream assumption was invalidated. No reapproval trigger was hit. No deployment, production credential, paid asset, final-character purchase/commission, or public release action occurred.
