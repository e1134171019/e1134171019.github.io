# Cinematic 3D Character Website — Task 12.5 Action Completion E2E Closure Design

Date: 2026-08-10
Proposal: cinematic-3d-character-website-solution-r1
Revision: 1.0
Layer: 07 corrective integration gate
Baseline commit: `485bc422c2434dabdaa160f157129d31e9de530b`
Status: written design pending user review

## 1. Goal

Close the remaining Task 11 primary-action correctness gap without expanding architecture or hiding the later performance/GPU findings.

The required end-to-end contract is:

`KeyE -> primaryAction -> CharacterDesiredState.action -> semantic action animation/fallback -> semantic actionCompleted -> CharacterState reducer -> move | turn | returnToIdle -> interactive progression`

The closure must work both when a real semantic action clip exists and when the current legal nonfinal runtime fixture exposes no usable action clip. Missing animation capability must not leave `CharacterDesiredState` permanently stuck in `action`.

## 2. Governance and Skill Binding

This corrective task remains inside the already approved Layer 07 implementation scope. It does not change the visible outcome, framework/engine route, delivery architecture, asset strategy, cost, credential use, or deployment authorization.

Bound governance:

- `00｜GLOBAL｜AI 工作系統總綱`
- `00｜MAIN｜網頁開發決策總綱`
- `07｜執行、責任配置與整合`
- `Web 專案開發規範 v1.0`, active and required
- approved solution `cinematic-3d-character-website-solution-r1@1.0`

Relevant selected Skill contracts:

- `input_action_system_design`: preserves the already approved discrete `primaryAction` press-edge and the requirement that focus/lifecycle behavior cannot leave the character stuck in an unfinished action.
- `interactive_3d_scene_advisory`: preserves explicit animation/state-event responsibility and the distinction between desired character state and actual animation runtime state.

Execution responsibility remains `GPT_PROJECT_INTEGRATOR` in `SANDBOX_PRIMARY_WORKSPACE`, using the existing isolated `layer07/v1` worktree. This task does not claim either selected Skill is globally complete.

## 3. Observed Baseline and Exact Gap

The baseline code already establishes the upstream and downstream halves:

- `src/input/KeyboardInput.ts` produces the named `primaryAction` press edge.
- `src/state/CharacterState.ts` enters `action` on `primaryAction` and deliberately keeps `action` sticky during ordinary input ticks.
- `CharacterState` can leave `action` only through `{ type: 'actionCompleted', input: InputSnapshot }`.
- On `actionCompleted`, current held movement can immediately select `move`; current held turn can select `turn`; otherwise the reducer selects `returnToIdle`.
- `src/character/AnimationCoordinator.ts` maps desired `action` to a semantic action clip, configures it as `LoopOnce`, and falls back to idle or `none` when no action clip exists.
- `AnimationCoordinator.update(deltaTime)` currently updates `AnimationMixer` but produces no semantic completion event.
- `src/app/RuntimeApp.ts` currently performs `transitionTo()` and `update()` but never dispatches `actionCompleted` back into `CharacterState`.

Therefore the missing responsibility is exactly:

`AnimationMixer completion / missing-action fallback -> typed semantic runtime event -> RuntimeApp -> CharacterState.actionCompleted`

This is a local integration defect. It does not justify a new state model, timer-based action duration, physics engine, new animation framework, or input redesign.

## 4. Approaches Considered

### A. Typed pull-event from `AnimationCoordinator.update()` — selected

`AnimationCoordinator` translates engine-specific mixer completion into a project semantic event and returns pending runtime events from its update boundary. `RuntimeApp` consumes those events using the already sampled current `InputSnapshot`.

Advantages:

- Three.js `AnimationMixer` details stay inside the animation subsystem.
- `RuntimeApp` receives only project semantic events.
- deterministic unit and composition testing is straightforward.
- the frame loop remains explicit and ordered.
- missing-clip completion can use the same event contract as actual clip completion.

### B. Callback from `AnimationCoordinator` into `RuntimeApp` — rejected

A callback would close the loop but introduces asynchronous/re-entrant side effects from the animation subsystem into the composition root. It makes frame ordering and current-input ownership harder to reason about and test.

### C. `RuntimeApp` directly listens to `AnimationMixer.finished` or inspects `AnimationAction` — rejected

This leaks Three.js implementation state across the `RuntimeAnimationPort`, violates subsystem ownership, and couples the composition root to clip/action internals.

### D. Timer derived from nominal clip duration — rejected

A timer can drift from actual mixer playback, crossfade, time scale, paused frames, and browser scheduling. It would manufacture completion instead of observing runtime completion.

## 5. Selected Runtime Event Contract

Introduce a minimal typed semantic event owned by the animation subsystem:

```ts
export type AnimationRuntimeEvent =
  | { readonly type: 'actionCompleted' };
```

The runtime animation port becomes conceptually:

```ts
interface RuntimeAnimationPort {
  transitionTo(desiredState: CharacterDesiredState): AnimationTransitionResult;
  update(deltaTime: number): readonly AnimationRuntimeEvent[];
  dispose(): void;
}
```

The exact production implementation may use an internal pending-event queue because Three.js emits mixer events during `mixer.update()`. Engine-specific event objects must not cross this boundary.

No new global event bus is introduced.

## 6. Actual Action Clip Completion Semantics

When `transitionTo('action')` selects a real semantic action clip:

1. Configure the selected `AnimationAction` as `LoopOnce` with existing clamp behavior.
2. Arm one semantic action-completion generation for that accepted action playback.
3. Observe the mixer `finished` event internally.
4. Accept completion only when it corresponds to the currently armed semantic action playback.
5. Queue exactly one `{ type: 'actionCompleted' }` event.
6. Mark that generation completed so repeated mixer notifications or subsequent ordinary frame updates cannot emit duplicates.
7. A later new action intent must be able to replay and re-arm the same semantic clip after the desired state has left `action` and re-entered it.

Unrelated clip completion must not produce `actionCompleted`.

## 7. Missing Action Clip Semantics

The current legal nonfinal fixture may have zero clips, and a future runtime asset may have idle/walk clips but no semantic action clip. Both are valid capability-absence cases for this corrective task.

When desired state is `action` but semantic selection resolves to fallback idle or `none`:

1. Preserve the existing visual fallback result (`usedFallback: true`).
2. Do not fabricate a fake animation duration.
3. Queue exactly one semantic `actionCompleted` for that action request, available through the next `update()` boundary in the same controlled frame cycle.
4. Allow `RuntimeApp` to reduce the state using current held input.
5. Do not classify absence of an optional test-fixture action clip as a runtime crash.

This keeps the state machine live while clearly preserving the distinction between “action intent completed through capability fallback” and “a real action animation was played.” It is not evidence of final character animation quality.

## 8. RuntimeApp Handoff and Frame Ordering

The existing frame order remains authoritative. The corrective insertion is local to the animation segment:

```text
sample InputSnapshot
-> reduce ordinary input into CharacterDesiredState
-> step/apply locomotion
-> animation.transitionTo(desiredState)
-> animation.update(deltaTime) => AnimationRuntimeEvent[]
-> consume animation events
   -> actionCompleted uses the same current InputSnapshot
   -> reduce CharacterState
-> camera
-> performance/quality sample
-> render
-> overlay/diagnostics
```

Consequences:

- If the action completes while `moveForward` remains held, the reducer can select `move` immediately; physical key rebinding is not involved.
- If no movement/turn intent is held, completion selects `returnToIdle`, and the already established reducer progression reaches `interactiveIdle` on later ordinary ticks.
- Motion for a just-completed action may resume on the next frame because locomotion is intentionally stepped before animation completion consumption. At 60 Hz this is one frame of deterministic latency and avoids rerunning locomotion side effects twice in a frame.
- The corrective task must not reorder camera, quality, renderer, or overlay responsibilities merely to close action completion.

## 9. Lifecycle and Cleanup

Because the selected implementation observes mixer completion, lifecycle cleanup becomes part of the animation port contract.

`AnimationCoordinator.dispose()` must:

- remove any mixer completion listener installed by the coordinator;
- invalidate/clear pending action-completion state;
- be safe against repeated disposal;
- prevent post-disposal semantic completion delivery.

`RuntimeApp.releaseRuntimeSideEffects()` must dispose the animation port if one was created. This applies to normal app disposal and fallback cleanup.

The task must not create a second RAF loop, window-global animation event listener, or persistent cross-app event bus.

## 10. TDD Acceptance Matrix

Implementation begins with failing tests that demonstrate the missing producer/handoff. At minimum:

1. **Real semantic action clip**: an armed `LoopOnce` action produces exactly one semantic `actionCompleted` when the mixer finishes it.
2. **Unrelated finish isolation**: completion from an unarmed/non-action animation does not produce `actionCompleted`.
3. **No duplicate completion**: extra updates after completion do not emit another event for the same action generation.
4. **Replay/re-arm**: a later new action request can replay and complete again after the prior action has left the desired `action` state.
5. **Missing action clip with idle fallback**: one semantic completion is emitted; state cannot remain stuck in `action`.
6. **Zero-clip fixture**: one semantic completion is emitted without crash; this remains nonfinal/non-equivalent asset evidence.
7. **RuntimeApp E2E idle path**: `primaryAction` enters `action`, semantic completion is consumed, then reducer progresses through `returnToIdle` to `interactiveIdle` under neutral input.
8. **RuntimeApp held movement path**: if forward movement remains held when completion is consumed, desired state becomes `move` rather than being forced to idle.
9. **Dispose cleanup**: after runtime disposal, animation completion cannot mutate app state or create additional frame/runtime side effects.
10. **Existing input priority**: the corrective work does not alter KeyE press-edge semantics or raw-key isolation.

The RED phase must fail because the semantic animation completion API/producer or app handoff is absent, not because of syntax, fixture corruption, or unrelated infrastructure failure.

## 11. Verification Gate

After minimal implementation:

- targeted `AnimationCoordinator` tests pass;
- targeted `RuntimeApp` composition tests pass;
- existing CharacterState/InputAction regression tests pass;
- full Vitest regression passes;
- strict TypeScript + Vite production build passes;
- production chunk-size warning remains reported rather than being suppressed by this task;
- if browser composition wiring changes observable behavior, rerun the existing browser action flow and confirm action can leave `action` through the semantic completion path where the test asset permits deterministic verification;
- verify exact source bytes/commit used for independent executor evidence;
- verify no deployment, credential, paid, final-asset, or architecture change occurred.

Sandbox dependency installation is an environment concern, not permission to weaken the gate. If local npm execution remains unavailable, use the already established isolated executor bridge for TDD/runtime evidence and record that separation explicitly.

## 12. Explicit Non-Goals

Task 12.5 does not:

- change the 635+ kB bundle or `chunkSizeWarningLimit`;
- introduce code splitting or dependency pruning;
- run or claim the 1920x1080 real-hardware GPU acceptance gate;
- resolve the Firefox hosted-executor WebGL2 environment blocker by changing the approved WebGL2 baseline;
- implement final character animation authoring, retargeting, rigging, facial animation, or final asset acquisition;
- reinterpret the Box fixture as a character-quality or animation-quality asset;
- change the keyboard binding contract;
- add a physics engine, React/R3F, WebGPU primary route, backend, analytics, or Sentry;
- deploy or publish the site.

Those boundaries intentionally preserve the subsequent sequence:

`Task 12.5 Action Completion Closure -> Task 13A Performance Baseline -> Task 13B Bundle Decision -> Task 13C Real GPU Acceptance -> Task 14 Integration Review`.

## 13. Rollback and Traceability

- All modifications remain in the existing isolated `layer07/v1` worktree.
- The design spec is committed separately before implementation planning.
- Production implementation must be a later isolated commit following TDD RED -> minimal GREEN -> regression verification.
- No unrelated file may be folded into the corrective commit.
- If the actual mixer semantics prove this design invalid, stop and revise the written design rather than stacking speculative fixes.

## 14. Completion Definition

Task 12.5 may be closed only when fresh evidence proves all of the following:

- a real one-shot semantic action can produce exactly one `actionCompleted`;
- an absent action clip cannot permanently trap the character in `action`;
- `RuntimeApp` consumes completion through a typed animation boundary rather than Three.js internals;
- current held movement/turn intent is preserved at completion;
- animation event listeners/pending completion state are cleaned up on disposal;
- full regression and production build remain valid;
- the bundle warning and real-GPU validation remain separately disclosed, not silently reclassified as solved.
