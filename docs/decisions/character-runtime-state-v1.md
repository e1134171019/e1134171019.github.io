# Character / Runtime State Decision v1

Date: 2026-08-10
Project: Cinematic 3D Character Website
Proposal: cinematic-3d-character-website-solution-r1@1.0
Layer: 07
Decision ID: cinematic-3d-character-runtime-state-v1

## Skill and governance binding

This decision applies the selected `input_action_system_design` contract to the downstream named-action handoff and applies the `interaction_state_design` scope of `interactive_3d_scene_advisory`. It is bound to Web Project Development Handbook v1.0 (active) for typed state, state ownership, module boundaries, side-effect isolation, testability, and traceability.

## Responsibility boundary

- `KeyboardInput` owns physical-key-to-named-action translation and lifecycle clearing.
- `CharacterState` owns only `CharacterDesiredState`: the runtime command/intention state requested for the character.
- `CharacterState` never sees raw key codes.
- Actual animation clip/playback state, blend progress, root motion, and animation completion are not owned by this reducer and remain downstream Animation Runtime responsibilities.
- `RuntimeState` owns browser runtime lifecycle mode and explicit typed fallback error state.
- Reducers are pure and have no DOM, renderer, animation, camera, asset, or persistence side effects.

## Character desired states

`presentationIdle | interactiveIdle | move | turn | stop | action | returnToIdle`

## Character event contract

The reducer consumes explicit events:

- `interactionEnabled`
- `presentationEnabled`
- `input` carrying the existing `InputSnapshot`
- `actionCompleted` carrying the current `InputSnapshot`

Rules:

1. `presentationIdle` ignores input until `interactionEnabled` establishes `interactiveIdle`.
2. `primaryAction` press-edge has highest input priority and enters `action`.
3. `action` is sticky with respect to normal input ticks. It remains `action` until explicit `actionCompleted`; input absence does not imply animation completion.
4. After `actionCompleted`, current held input may immediately request `move` or `turn`; otherwise state becomes `returnToIdle`.
5. Movement has precedence over turn for the coarse desired-state classification when compatible movement + turn are simultaneously held. The original `InputSnapshot` still carries both intents for downstream heading/motion systems.
6. Opposing pairs are treated as neutral defensively (`forward && backward`, `left && right`) even though `KeyboardInput` already neutralizes them.
7. An active locomotion state with no actionable input progresses `move/turn -> stop -> returnToIdle -> interactiveIdle` over reducer ticks. This preserves explicit Stop and Return Idle states required by the approved architecture.
8. `presentationEnabled` returns the character to `presentationIdle` from any desired state.

## Runtime state contract

Runtime states are explicit tagged values:

- `{ mode: 'loading' }`
- `{ mode: 'presentation' }`
- `{ mode: 'interactive' }`
- `{ mode: 'fallback', error: { code, message } }`

Runtime events:

- `assetsReady`: loading -> presentation
- `interactionStarted`: presentation -> interactive
- `presentationRequested`: interactive -> presentation
- `runtimeError`: any state -> fallback with typed `RuntimeErrorCode` and message

Fallback is fail-closed for normal lifecycle events. Recovery/retry is not introduced in this task because no approved recovery UX/runtime contract has been implemented yet.

## Handoff contract

Producer: `KeyboardInput.snapshot()`
Output: typed `InputSnapshot { held, pressed }`
Consumer: `reduceCharacterState()` via `{ type: 'input', input }`
Validation:
- raw key codes do not enter state domain;
- edge action remains one-shot at input boundary;
- named input deterministically maps to desired state;
- action completion requires a separate downstream state event;
- focus-loss clearing upstream therefore produces neutral input and deterministic stop/idle progression downstream.

## Explicit non-goals

This task does not implement character translation/rotation, animation clips/blending, camera, Three.js scene behavior, physics, asset loading, final character assets, UI overlays, deployment, or public release.
