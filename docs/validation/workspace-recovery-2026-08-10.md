# Layer 07 Sandbox Workspace Recovery — 2026-08-10

## Incident
The current Sandbox runtime retained the formal project path and documentation, but the prior local `.git` metadata and `src/` tree were absent. The previous local commit graph therefore could not be truthfully claimed as recovered.

## Recovery source
- Transport/executor only: `e1134171019/e1134171019.github.io`
- Branch: `runtime-bootstrap/cinematic-3d`
- Recovery workflow run: `31342083887`
- Recovery workflow head: `6d5323b4891c27ae7cb87ff568a0245e85f1cddc`
- Recovery artifact: `9046127390`
- GitHub Actions role remains CI/recovery transport only, not project Source SSOT.

## Integrity verification
Recovered source was checked against the hashes recorded by the retained formal validation documents for Tasks 2–6. All 15 recorded source hashes matched exactly, including Task 6 `CharacterController.ts` and `CharacterController.test.ts`.

## Recovery policy
A new local Git recovery baseline is created because the original Sandbox Git metadata is unavailable. This baseline preserves verified source bytes and retained governance/validation documentation, but it does **not** claim continuity of the lost local commit graph. Layer 07 continues in a new linked worktree from this recovery baseline.
