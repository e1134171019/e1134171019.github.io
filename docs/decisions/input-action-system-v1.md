# Input Action System — Project-Specific Decision v1

- project: Cinematic 3D Character Website
- capability: input_system_design
- selected_skill: input_action_system_design
- skill_state: active / SPEC_VERIFIED
- exact_skill_source_commit: 858c3e58e1f35ea3a5746c4df6003ffbd1c4dad0
- decision_id: cinematic-3d-character-input-action-v1
- decision_status: approved_upstream_scope / ready_for_execution
- owner_domain: web_development
- target_device_scope: desktop keyboard only

## Project-specific inputs

This decision is constrained by the approved V1 project contract and architecture:

- Keyboard is the required V1 physical input device; touch, gamepad and persistent rebinding are out of scope.
- Character movement/turning must respond in real time and remain controllable.
- At least one non-locomotion action must be triggerable from keyboard input.
- Focus loss must never leave the character moving or acting without active user control.
- Physical keys must not leak into character/gameplay contracts; downstream code consumes named actions only.
- This node does not implement locomotion physics, animation blending, camera motion or character-state policy.

## Input action map

| Named action | Class | Default physical binding | Alternate binding | Conflict behavior | Downstream intent |
|---|---|---|---|---|---|
| `moveForward` | continuous / held | `KeyW` | `ArrowUp` | neutral with `moveBackward` | forward movement intent |
| `moveBackward` | continuous / held | `KeyS` | `ArrowDown` | neutral with `moveForward` | backward movement intent |
| `turnLeft` | continuous / held | `KeyA` | `ArrowLeft` | neutral with `turnRight` | left turn intent |
| `turnRight` | continuous / held | `KeyD` | `ArrowRight` | neutral with `turnLeft` | right turn intent |
| `primaryAction` | discrete / press-edge | `KeyE` | none | may coexist with held movement/turn | one non-locomotion action intent |

Binding policy:

- Named actions are authoritative. Physical bindings are an adapter configuration, not gameplay state.
- Bindings use `KeyboardEvent.code` so the physical mapping is stable across keyboard layouts.
- Arrow keys are keyboard-only alternate bindings; they do not expand the device scope.
- `KeyE` is used for the primary action rather than Space to avoid taking over the page's standard Space-scroll behavior.
- Mapped-key default browser behavior is prevented only while input capture is started and the event is not coming from an editable target.
- Key events originating from `input`, `textarea`, `select`, or `contenteditable` targets are ignored so keyboard interaction does not trap normal text-entry behavior.

## Edge vs held semantics

- Continuous actions (`moveForward`, `moveBackward`, `turnLeft`, `turnRight`) remain active between `keydown` and the matching `keyup`.
- `primaryAction` is a rising-edge event. One physical press creates at most one pending action edge.
- `KeyboardEvent.repeat` must not generate another `primaryAction` edge.
- `snapshot()` returns the current held state plus any discrete edges accumulated since the previous snapshot, then consumes those discrete edges.
- A new `primaryAction` edge can occur only after release and a subsequent new press.
- Simultaneous movement + turn is allowed (for example forward + right).
- Opposing continuous pairs resolve to neutral in the emitted snapshot:
  - forward + backward => neither emitted as active;
  - left + right => neither emitted as active.

## Focus and lifecycle safety

All active and pending input state is cleared when any of the following occurs:

- browser window `blur`;
- document visibility becomes `hidden`;
- `KeyboardInput.stop()` is called (runtime pause/failure/teardown boundary).

`start()` and `stop()` are idempotent. A missed `keyup` before focus loss must therefore not leave a held action active.

## Accessibility constraints

- Every core action has a single-key path; no operation requires a forced multi-key chord.
- Editable controls keep their ordinary keyboard behavior.
- No touch/gamepad/rebinding UI is introduced in V1.
- Arrow alternatives remain within the same required keyboard device class.

## Testable state cases

1. `KeyW` down => `moveForward` held; `KeyW` up => false.
2. `ArrowUp` behaves as the same named action without exposing ArrowUp downstream.
3. `KeyE` down => one `primaryAction` press edge; second snapshot without another press => false.
4. repeated `KeyE` keydown (`repeat=true`) => no second press edge.
5. blur after a held movement => all held/edge state cleared.
6. hidden visibility state => all held/edge state cleared.
7. `stop()` clears state and removes listeners.
8. forward + backward simultaneously => neutral movement snapshot.
9. left + right simultaneously => neutral turn snapshot.
10. movement + turn simultaneously => both non-conflicting held intents remain active.
11. mapped keys from editable targets are ignored.

## Traceability map

- `moveForward` / `moveBackward` / `turnLeft` / `turnRight` -> approved keyboard locomotion/turn primary action and input-transition evidence.
- `primaryAction` -> approved non-locomotion keyboard action and input-transition evidence.
- focus/visibility/stop cleanup -> approved focus-loss safety and no-stuck-input requirement.
- named-action abstraction -> architecture control boundary: keyboard input -> virtual character runtime state without raw-key coupling.

## Applicable Web Handbook rules

For this capability, the bound Web Handbook v1.0 applies specifically through:

- Type & Predictability: named typed actions; no magic-string gameplay key contracts.
- Modularity / Responsibility Separation: DOM event side effects are isolated in `KeyboardInput`; action contracts live separately.
- State Ownership: `KeyboardInput` owns transient browser input state only.
- Contract & Boundary: downstream modules receive named action snapshots, not DOM events.
- Side-effect Isolation: event registration/removal is isolated from state interpretation.
- Testability: action semantics and lifecycle cleanup are deterministic unit-test targets.
- Traceability: tests map to the approved movement/action/focus-safety outcomes.
- Accessibility: keyboard capture does not override editable controls and does not require chords.

## Executor translation

Executor: approved GPT formal implementation role in the isolated `layer07/v1` worktree.

Implement only:

- `src/input/InputActions.ts`
- `src/input/KeyboardInput.ts`
- `src/input/KeyboardInput.test.ts`
- Task-2 validation evidence

Required implementation contract:

- expose typed named actions and typed snapshots;
- isolate DOM keyboard/focus/visibility side effects in `KeyboardInput`;
- implement held vs press-edge semantics exactly as defined above;
- implement opposing-pair neutralization;
- implement focus/visibility/stop cleanup;
- do not implement character movement, animation, camera, physics, gamepad, touch, persistence or rebinding;
- use RED -> minimum GREEN -> fresh test/build verification before completion.

## Decision review against Skill comparison contract

- actions separated from physical keys: PASS
- discrete vs continuous semantics explicit: PASS
- focus loss cleanup present: PASS
- required devices match V1 contract: PASS
- accessibility constraints preserved: PASS
- test cases present: PASS
- engine/framework input API lock-in: NONE

No reapproval trigger is introduced by this decision: it stays within the approved desktop-keyboard V1 interaction scope and does not change architecture, cost, credentials, assets or delivery.
