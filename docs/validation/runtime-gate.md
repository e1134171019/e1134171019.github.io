# Layer 07 Runtime Gate Evidence

Date: 2026-08-09
Branch: `layer07/v1`
Status: `BLOCKED_ENVIRONMENT_PACKAGE_NETWORK`

## Approved Runtime

- TypeScript + Vite + Three.js `WebGLRenderer` / WebGL2
- Vitest unit tests
- Playwright browser validation
- GPT Sandbox remains the approved primary workspace

## Local Prerequisites

- Node.js: `v22.16.0`
- npm: `10.9.2`
- Git: `2.47.3`
- Local TypeScript available globally: `5.8.3`
- Three.js: not installed
- Vite: not installed
- Vitest: not installed
- Node `@playwright/test`: not installed
- jsdom: not installed

## Root Cause Investigation

### 1. Sandbox network policy

The environment declares `NETWORK=caas_packages_only`. External DNS is unavailable from the shell. `registry.npmjs.org`, `npmjs.com`, `github.com`, `raw.githubusercontent.com`, `pypi.org`, and `google.com` do not resolve through the configured resolver.

Direct DNS-server connectivity to the configured resolver on TCP/53 also fails in this container.

### 2. npm is forced through the internal package gateway

`NPM_CONFIG_REGISTRY` and `/etc/npmrc` point npm to the internal package gateway rather than public npm.

The gateway hostname resolves through `/etc/hosts`, so the request reaches the internal endpoint.

### 3. Internal npm endpoint is not serving packages

Requests to the configured npm endpoint return HTTP 404. This is not specific to the selected project dependencies: a baseline query for `lodash` also returns npm `E404`.

The gateway root, Artifactory root, npm API root, configured registry root, and registry ping path all return nginx 404 responses.

### 4. No usable local package cache

`npm cache verify` reports zero cached content and zero index entries. There is no cached Three.js, Vite, Vitest, Playwright, or jsdom package available for offline installation.

### 5. No hidden/global approved runtime packages

Filesystem/global-module checks found no installed `three`, `vite`, `vitest`, `@playwright/test`, or `jsdom` package. A Python Playwright executable exists but it is not the approved Node `@playwright/test` dependency and cannot satisfy the planned JS test/runtime route by itself.

## Conclusion

The blocker is environmental package acquisition, not application architecture and not npm authorization:

1. public npm cannot be resolved/reached from the Sandbox shell;
2. the configured internal npm gateway is reachable but returns 404 for all tested npm paths/packages;
3. there is no offline cache or preinstalled approved dependency set.

Per the approved implementation plan, production code and the TDD cycle remain unstarted until the Runtime Gate can install the approved dependencies or an explicitly approved equivalent acquisition mechanism is provided.

## Non-actions

The following were intentionally not used as silent substitutes:

- raw WebGL instead of Three.js
- CDN runtime imports
- a different 3D engine
- Replit or another execution environment
- vendored third-party packages from unverified sources
- production credentials

## Plan Correction Identified

The implementation plan configures Vitest with `environment: 'jsdom'` but omitted `jsdom` from `devDependencies`. Once package acquisition is restored, `jsdom` must be added as a dev-only dependency before executing the first unit-test cycle.
