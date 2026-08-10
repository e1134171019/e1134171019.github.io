# Task 12 Validation — Cross-Browser Runtime Smoke and Failure Evidence

Task ID: layer07-task12-playwright-cross-browser-interaction-focus-loss-regression
Date: 2026-08-10
Layer: 07
Status: PARTIAL_ENVIRONMENT_BLOCKED
Project outcome status: advanced_not_complete
Selected Skill execution claim: false
Global Skill Registry upgrade: not_claimed

## System route

- task_mode: formal
- route_type: single_domain
- deliverable: website
- primary_domain: web_development
- current_layer: 07
- current_task: task12_playwright_cross_browser_interaction_focus_loss_regression
- approved_solution: cinematic-3d-character-website-solution-r1 / revision 1.0
- execution_route: GENERAL_EXECUTION_FALLBACK
- formal_workspace: Sandbox isolated worktree `layer07/v1`
- isolated_runtime_executor: GitHub Actions mirror `e1134171019/e1134171019.github.io` / `runtime-bootstrap/cinematic-3d`
- mirror_source_status: executor_only_not_project_source_ssot

## Governance and handbook binding

Fresh formal reads were completed before Task 12 execution for:

- `00｜GLOBAL｜AI 工作系統總綱`
- `00｜MAIN｜網頁開發決策總綱`
- `00-A｜全域工具與執行資源登錄表`
- `00-B｜全域工具路由與執行回報規範`
- `07｜執行、責任配置與整合`
- `Web 專案開發規範` v1.0
- Project SSOT `PROJECT｜Cinematic 3D Character Website｜流程狀態`

Handbook lifecycle was applied as MUST_READ → MUST_BIND → MUST_APPLY → MUST_VERIFY. The Task 12 changes are limited to browser verification, development-only read-only diagnostics, a development-only forced WebGL2 failure seam, and unit/E2E test discovery separation. No renderer architecture, WebGL2 baseline, production fallback semantics, asset policy, or approved input bindings were changed.

## Mandatory resource review

The registered 29-resource mandatory review set was scanned before execution.

- INVOKED / required: Google Drive, GitHub, Superpowers
- RELEVANT_NOT_INVOKED: Vercel (deployment outside Task 12), Sentry (optional observability; not required for this smoke)
- REVIEWED_NOT_RELEVANT_FOR_TASK12: remaining registered resources

This is a 29/29 review claim, not a claim that 29 tools were invoked.

## Binding decision and plan deviation

Decision: `docs/decisions/browser-runtime-task12-v1.md`
Decision ID: `cinematic-3d-character-browser-runtime-task12-v1`
Decision SHA-256: `52a4852ea7138fa6d08c6926d5026e8303d15be9751bfe6393bee42f80ca89b2`

The older Task 12 implementation plan example says `Space` for the primary action. The already-approved Task 2 input contract is authoritative and binds `primaryAction` to `KeyE`, explicitly preserving Space for page semantics. Task 12 therefore verifies `KeyE`; it does not rebind Space to make the old example pass.

## Formal source commit

Formal source commit: `719e2c8fc9cb349685d46b8b43380ebf576b6eae`
Commit subject: `test: verify cross-browser character interaction flow`

Formal Task 12 source/config SHA-256 set:

- `src/app/RuntimeApp.ts`: `ff78ee14ebde4bacc14df3028431819a88c5d84d78e48e1fd8c85dd7e1220006`
- `src/main.ts`: `76be4f1c00f4106bac1e1f5fa89564b5b0e58e4d05c1d92e4074220d556aff84`
- `vite.config.ts`: `a1cf9e1c032df4b61428a2a5be68e322683f87e3455d679a7d4602fe81cee20c`
- `playwright.config.ts`: `ad5f52521add6c5bce07dfce16fce7981f4f3dddfaaebd398679c2149ab3eb88`
- `tests/e2e/runtime.spec.ts`: `192d97a95fd0acf940f48fe27a64e782564089e14a947de4e0f4e3465988fd01`
- `tests/e2e/focus-loss.spec.ts`: `57677cd671f97b86d94d1c4a2bd333dbb89b63d08c51ba814041a19921243134`
- `tests/e2e/fallback.spec.ts`: `f9ab9ed47cb44be444b9bf0c97b52c0fd8dd0b51e7953e6c1527ed3441d69b77`

The final executor verification first checked these exact hashes before tests.

## TDD RED evidence

Expected-failing browser run:

- workflow: `cinematic-3d-task12-e2e-red`
- run: `31347739469`
- job: `93332723884`
- artifact: `9047924747`
- artifact SHA-256: `ca13dee7857d902f9e289f6f6fc71ad59be6e6a5640b20a6af6ec3fbf8f8f111`
- result: 9 browser tests failed as expected before Task 12 diagnostics / force-failure hooks existed

The failures were useful RED evidence rather than an accepted final state. Chromium/WebKit lacked the new diagnostics and forced-failure hook. Firefox also failed to reach interactive mode, which was separately investigated instead of being hidden by a product downgrade.

## Systematic-debugging evidence

### Firefox WebGL2 capability probe

An executor-only blank-page capability probe was run independently of the product runtime:

- workflow: `cinematic-3d-task12-webgl2-capability-probe`
- run: `31348001488`
- job: `93333452461`
- artifact: `9047995577`
- artifact SHA-256: `8586899d9d7ea3acee355305729f076ce04e1df3dedb48ee17c0003beb472300`

Observed WebGL2 capability:

- Chromium: `webgl2=true`; WebGL 2.0; renderer reports ANGLE + SwiftShader software Vulkan device
- Firefox 153.0: `webgl2=false` on a blank page before loading product code
- WebKit 26.5: `webgl2=true`; WebGL 2.0

Conclusion: the Firefox interactive failure on this GitHub-hosted executor is an executor/browser capability blocker. Task 12 did not add a WebGL1 downgrade or alternate renderer to make the matrix artificially green.

### Unit/E2E discovery collision

First final-verifier attempt:

- run: `31348253077`
- job: `93334155079`
- result: stopped at `npm test` before browser steps

Root cause: the existing Vitest config had no explicit unit-test include boundary, so adding `tests/e2e/*.spec.ts` caused Vitest to discover Playwright specs and throw `Playwright Test did not expect test() to be called here`. The existing 10 unit files / 61 unit tests themselves passed in that run.

Minimal fix: `vite.config.ts` now scopes Vitest to `src/**/*.test.ts`. This separates unit and E2E discovery without changing runtime product behavior.

## Final verification evidence

Final workflow:

- workflow: `cinematic-3d-task12-e2e-verification`
- run: `31348435799`
- job: `93334644603`
- workflow conclusion: success
- artifact: `9048156825`
- artifact size: 960,912 bytes
- artifact SHA-256: `07e96257db0fc614129f5f7b40c70dc2240c62aa089ce21fa22b4fe5b29a9ff2`

The workflow `success` means the supported-browser verification passed and the Firefox executor limitation was correctly classified fail-closed. It does **not** mean all three browsers reached interactive mode.

Verification results:

- exact Task 12 source/config hash verification: PASS
- verified nonfinal Task 5 fixture hash: PASS (`ed52f7192b8311d700ac0ce80644e3852cd01537e4d62241b9acba023da3d54e`)
- dependency install: PASS; 0 reported npm vulnerabilities
- unit regression: 10 test files, 61/61 PASS
- strict TypeScript: PASS
- Vite production build: PASS
- Chromium automated Task 12 flow: 3/3 PASS
  - explicit fallback
  - focus-loss held-input cleanup
  - interactive movement + approved `KeyE` primary action
- WebKit automated Task 12 flow: 3/3 PASS
  - explicit fallback
  - focus-loss held-input cleanup
  - interactive movement + approved `KeyE` primary action
- Firefox explicit fallback: 1/1 PASS
- full Chromium/Firefox/WebKit matrix: 7/9 PASS, 2/9 FAIL
  - Firefox focus-loss test: cannot reach `interactive`
  - Firefox runtime test: cannot reach `interactive`
- final matrix contract: `environment_blocked_firefox_webgl2`

The two Firefox failures align with the independent blank-page `webgl2=false` probe and are retained as failure evidence rather than suppressed.

## Browser/runtime scope and non-claims

Automated environment:

- Chromium / Chrome for Testing: 151.0.7922.34
- Firefox: 153.0
- WebKit: 26.5
- Playwright viewport: 1280×720
- GitHub hosted Ubuntu 24.04 runner

Verified in this scope:

- formal app reaches `interactive` in Chromium and WebKit
- `KeyW` produces observable movement state
- approved `KeyE` produces observable action state
- `window.blur` clears held keyboard input in supported automated browsers
- forced `unsupported_webgl2` enters explicit, non-equivalent fallback UI
- Firefox fallback presentation is valid when WebGL2 is unavailable
- no page errors were observed by the Chromium/WebKit runtime-flow test

Not verified / not claimed:

- Firefox interactive path on a WebGL2-capable Firefox environment
- real discrete GPU acceptance at 1920×1080
- real integrated GPU 30 FPS floor
- physical driver variability
- real-hardware visual quality acceptance
- 10-minute stability / context-loss acceptance (Task 13 scope)
- final cinematic character quality
- Task 11 `actionCompleted` producer closure; Task 12 only observes entry into `action`
- project completion

## Build warning retained

The production build passes but reports a non-blocking main JS chunk warning:

- main JS: approximately 635.79 kB minified / 162.62 kB gzip
- Vite warning threshold: 500 kB

Task 12 does not hide the warning or perform unrelated code-splitting refactors. It remains a performance/runtime-gate handoff item.

## Capability cross review

Result: PARTIAL_PASS_ENVIRONMENT_BLOCKED.

- Chromium automated browser capability: PASS within software-rendered/headless executor scope
- WebKit automated browser capability: PASS within hosted/headless executor scope
- Firefox explicit fallback: PASS
- Firefox interactive capability: BLOCKED because the independent Firefox executor probe exposes no WebGL2
- real-hardware GPU acceptance: UNVERIFIED

No architecture downgrade is authorized or implied by this blocker.

## Project outcome cross review

Result: ADVANCED_NOT_COMPLETE.

Task 12 materially advances the project by converting the formal Task 11 composition root into repeatable browser interaction/focus/fallback evidence on two browser engines and explicit unsupported-WebGL2 evidence on Firefox. The project cannot claim full cross-browser acceptance or Layer 07 completion while Firefox interactive evidence and real-hardware GPU acceptance remain open.

Next blocked gate before a full Task 12 GREEN claim:

1. obtain a Firefox execution environment that independently exposes WebGL2 and rerun the interactive/focus-loss tests; and
2. obtain the approved real-hardware GPU environment and perform 1920×1080 acceptance evidence.

Task 13 may be prepared only with the Task 12 blocker preserved; it must not overwrite the unresolved cross-browser/real-GPU status.

## Deployment / source-control boundary

- no deployment was performed
- no production publication was performed
- no credentials were requested or changed
- no paid asset action occurred
- the GitHub executor mirror remains an isolated CI executor only and is not the formal project Source SSOT
- the dedicated formal project GitHub repository remains a separate infrastructure gap
