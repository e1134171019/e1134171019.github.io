# Cinematic 3D Character Website — Runtime UI Status Decision v1

## Decision identity

- decision_id: `cinematic-3d-character-runtime-ui-status-v1`
- layer: `07`
- task: `Task 10 — Minimal UI States and Accessible Runtime Status`
- selected_skills:
  - `web_ux_structure_design` — revision `1.0`, status `active`
  - `web_ui_system_design` — revision `1.0`, status `active`
- implementation_route: `approved GENERAL_EXECUTION_FALLBACK / GPT_PROJECT_INTEGRATOR + SANDBOX_PRIMARY_WORKSPACE`
- status: `implementation_ready`

## Bound project inputs

This decision is constrained by the already-approved project contract and does not add a new product surface:

- V1 target: desktop browser only; mobile/touch remains outside V1.
- Primary surface: character-first realtime 3D showcase.
- Authoritative runtime lifecycle already exists as `RuntimeState` with `loading`, `presentation`, `interactive`, and `fallback`.
- Task 10 consumes runtime state; it must not own or duplicate 3D business state.
- Input contract already exposes desktop keyboard controls: `W/S/A/D` plus arrow-key alternatives for movement/turning and `E` for `primaryAction`.
- Quality levels already exist as `high`, `balanced`, and `minimumInteractive`.
- Task 11 owns the formal composition root and runtime wiring. Task 10 must not create formal `src/main.ts` or a competing state store.

## UX delivery artifact

### Page structure map

Task 10 adds one DOM-only runtime overlay that sits adjacent to the future 3D scene host. It contains only status/help surfaces required to understand system state and controls:

1. runtime state heading/status text;
2. loading progress when provided;
3. keyboard help before and during interactive control;
4. focus/capture status in interactive mode;
5. quality-level status;
6. fallback/error details when realtime 3D is unavailable.

No navigation, marketing content, character-selection UI, settings UI, mobile controls, or runtime command surface is added here.

### State map

| Authoritative `RuntimeState.mode` | UI responsibility |
| --- | --- |
| `loading` | Announce that the character experience is loading; expose numeric progress when known; keep keyboard help discoverable before control starts. |
| `presentation` | State that the character presentation is ready; expose keyboard help without implying control capture has started. |
| `interactive` | State that realtime control is active; expose keyboard help and explicit focus/capture status. |
| `fallback` | Surface the typed runtime error and state that the fallback is non-equivalent to realtime 3D. Do not blame the user or claim realtime interaction remains available. |

Quality state is orthogonal to runtime lifecycle. If quality is `balanced` or `minimumInteractive`, visible text must state that quality has been reduced and that the reduction concerns secondary visual load rather than silently signaling by color.

### Interaction map

Task 10 does not initiate runtime transitions. It only reflects inputs supplied by the future Task 11 composition root.

- runtime event/change → caller passes new `RuntimeState` → overlay re-renders visible/assistive status;
- loading progress update → caller passes progress → visible percentage/status changes;
- interaction focus/capture update → caller passes focus state → interactive help states whether keyboard control is currently focused;
- quality-level update → caller passes quality level → visible quality explanation changes;
- runtime fallback → caller passes typed `RuntimeState.error` → overlay exposes code/message plus non-equivalent fallback explanation.

Recovery controls are deliberately absent because Task 10 has no approved recovery command contract. Adding a retry button without an authoritative runtime recovery action would invent behavior.

### Responsive behavior

V1 remains desktop-only. The overlay must be structurally usable at normal desktop viewport widths, avoid fixed pixel assumptions in its DOM contract, and permit wrapping/stacking through CSS. It must not infer mobile/touch behavior or add touch controls.

### Implementation annotations

- Consume `RuntimeState` directly rather than copying mode/error into a second store.
- Consume `QualityLevel` as a read-only presentation input.
- Loading progress is optional; unknown progress must remain textual rather than fabricated as `0%`.
- Interactive focus status is explicit boolean data from the caller; the overlay does not capture focus itself.
- Use semantic headings/paragraphs and an announced status region using `role="status"` / `aria-live="polite"` where appropriate.
- Fallback error content uses visible text and an assertive announcement boundary appropriate for failure status.
- State meaning must never depend on color alone.
- CSS is minimal structural/readability styling only; no new brand system or unapproved aesthetic direction is invented.
- No formal `src/main.ts`, renderer ownership, keyboard listener, quality-policy evaluation, or runtime transition logic in this task.

### UX rationale

Critical system status and keyboard instructions remain near the primary 3D task surface. Loading, focus, degradation, and fallback are explicit because they materially change whether the user can interact with the character. Error recovery is not invented because no recovery command is yet part of the authoritative runtime contract.

### UX unresolved / downstream handoff

- Task 11 must connect authoritative runtime/progress/focus/quality data to the overlay.
- Task 11/12 browser review must confirm overlay placement does not obscure the character-first presentation.
- Real keyboard-focus behavior requires browser-level validation after composition.

**UX verdict:** `UX_PARTIAL` — Task 10 has sufficient structure/state/interaction rules for implementation, but runtime handoff and browser-level placement/focus validation are downstream work.

## UI delivery artifact

### Token system boundary

Task 10 does not invent a complete visual design system. It uses semantic CSS custom properties only for local readability/structure and leaves full aesthetic tokenization to the composed UI/visual-review phase.

Permitted semantic roles:

- overlay surface/background;
- primary text / muted text;
- border/separator;
- focus/status emphasis;
- error emphasis;
- spacing/radius values needed for the minimal overlay.

Status semantics must always be present in text; color is supplemental only.

### Component rule

`RuntimeOverlay` is one status surface with a render/update contract. It may rebuild its own DOM subtree from caller-provided state, but it owns no business-state transition and registers no global keyboard/runtime listeners.

Required visible sub-surfaces are conditionally rendered from authoritative inputs:

- state label/message;
- progress text;
- keyboard help;
- focus status;
- quality status;
- fallback error details/non-equivalence statement.

### State styling rule

- loading: readable status + progress, no color-only spinner dependency;
- presentation: ready/presentation message + control help;
- interactive: explicit active-control and focus text;
- reduced quality: explicit `品質已降級` text and explanation;
- fallback/error: visible failure heading/message/code plus non-equivalence text; semantic failure announcement;
- focus differences: text and DOM state, not color alone.

### Responsive rendering rule

Use a wrapping, bounded overlay layout suitable for desktop widths; avoid absolute assumptions that require a fixed screen size. No touch-density or mobile breakpoint behavior is introduced because mobile/touch is outside V1.

### Implementation notes

- Prefer native semantic HTML (`section`, headings, paragraphs, lists) before ARIA roles.
- Use ARIA only to announce changing runtime state/error status.
- Tests must inspect visible text/semantics, not colors or screenshots.
- `styles.css` is structural/minimal and cannot become a substitute for later visual review.

### UI rationale

The character remains visually primary while status information remains legible, explicit, and assistive-technology discoverable. Minimal styling prevents Task 10 from silently freezing a broader aesthetic system before the composed runtime can be reviewed.

### UI unresolved / downstream handoff

- final cinematic typography/color/material treatment;
- overlay placement against the actual character framing;
- focus-ring behavior inside the composed runtime;
- responsive visual review beyond the approved desktop V1 surface.

**UI verdict:** `UI_PARTIAL` — semantic runtime-state UI rules are implementation-ready, while full visual-system/browser validation remains downstream.

## Executor translation

Implement only the formal Task 10 files:

- `src/ui/RuntimeOverlay.ts`
- `src/ui/RuntimeOverlay.test.ts`
- `src/styles.css`

TDD order is mandatory: create `RuntimeOverlay.test.ts`, observe an intended failure because `RuntimeOverlay` is absent, then implement the minimum DOM-only overlay and CSS, run targeted tests, full regression, strict TypeScript, and Vite build through the existing approved GitHub Actions executor bridge if Sandbox dependency execution remains blocked.
