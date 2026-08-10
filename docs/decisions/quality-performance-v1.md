# Cinematic 3D Character Website — Quality & Performance Decision v1

## Decision identity

- decision_id: `cinematic-3d-character-quality-performance-v1`
- layer: `07`
- task: `Task 9 — Quality Policy and Performance Instrumentation`
- selected_skill: `realtime_3d_performance_optimization`
- skill_source_commit: `858c3e58e1f35ea3a5746c4df6003ffbd1c4dad0`
- status: `implementation_ready`

## Bound project inputs

This decision consumes the approved Layer 06 performance contract without inventing new acceptance budgets:

- Primary quality target: median 60 FPS.
- Sustained inability to maintain 45 FPS triggers quality review/degradation.
- Minimum interactive floor after approved degradation: median 30 FPS.
- Cold-cache minimum-interactive startup: <= 10 s at 50 Mbps.
- Warm-cache minimum-interactive startup: <= 3 s when required assets are cacheable/cached.
- Visible input/action state response target: <= 100 ms under local runtime test conditions.
- Stability scenario: 10 minutes with no crash, WebGL context loss, or uncontrolled motion after focus loss.
- Memory policy: after 2 minutes of stabilization, no sustained monotonic runtime-memory growth >20% over the following 8 minutes.
- Degradation order: reduce secondary environment/effects before character identity, primary character materials, or basic interaction.
- WebGL context loss is failure evidence, not an accepted quality fallback.

## Measurement policy

The implementation is measure-first. It records bounded frame-time samples and derives FPS from actual frame durations. It can record startup-to-interactive timing and optional memory samples. Unsupported or absent memory evidence is represented as `null`; it is never silently converted to zero.

A numeric duration/sample count for the word "sustained" has not been approved by the outcome contract. Therefore Task 9 does **not** freeze an arbitrary project-wide duration. The rolling-window capacity and the number of samples required to establish a sustained condition are explicit caller-provided measurement configuration. Later real-browser/GPU validation must record the exact configuration used.

## Quality decision policy

`QualityLevel` is limited to:

- `high`
- `balanced`
- `minimumInteractive`

A complete caller-defined sustained window below 45 FPS requests degradation. The first quality reduction targets optional effects; a subsequent reduction targets secondary environment load. The policy does not emit a character-fidelity reduction target.

30 FPS is only the minimum interactive floor. Reaching 30 FPS does not mean the primary quality target is satisfied and does not suppress a degradation/review recommendation caused by sustained performance below 45 FPS.

Below 30 FPS is explicit failure evidence for the minimum interactive floor and must not be reported as success.

## Representative scenarios for later measurement

The Performance Skill requires the same scenario family to be used before/after optimization:

- Hero close-up / presentation.
- Character movement and turning.
- Primary character action.
- Character-first camera transition/follow/orbit behavior.
- Loading and quality-level transition.

Task 9 only provides instrumentation and policy. The current non-final Box GLB is not representative of final cinematic character geometry, textures, rig, animation, hair, skin, or GPU cost, so it cannot establish final character performance acceptance.

## Required evidence boundary

Task 9 may prove:

- bounded metric collection behavior;
- deterministic quality-policy decisions against approved thresholds;
- startup timing and memory-evidence semantics;
- regression safety through unit/build verification.

Task 9 does not prove:

- final cinematic-character FPS or frame time;
- real discrete/integrated GPU performance;
- final VRAM/texture pressure;
- final 10-minute stability acceptance;
- final memory-growth acceptance;
- final browser/device matrix acceptance.

Those require a representative runtime build and real browser/GPU evidence.
