# RC1 execution ledger

Work branch: `codex/rc1`. Owner authorization: Issue #1 and rc1-kickoff.md. No intermediate owner actions or manual tests requested.

## Current checkpoint (2026-11-01)

- Read AGENTS.md, kickoff, full technical scope, implementation design, traceability, developer setup and approved wireframe; fetched GitHub Issue #1 through the connected GitHub account.
- Started local Docker Desktop and downloaded workspace-local uv/Python (ignored `.tools`, `.venv`). No production access or media mutation.
- Implemented PostgreSQL schema/migration, session/CSRF/security, intake baseline and generations, leases/journal, qBt/Jellyfin/TMDb/subtitle adapters, core transfer/enrichment, quarantine/restore, seven Vue screens bound to APIs.
- Executed **67 backend tests in Linux: PASS, zero failures/skips**, including real disposable PostgreSQL migrations, backup/restore, ffprobe, symlink/hardlink, fault/replay, auth and mock provider contracts. All 43 T and 17 IT scenario identifiers traced in `rc1-automated-evidence.json`. Executed **4 frontend tests: PASS**, lint, TypeScript and production Vite build: PASS. Synthetic results are separate from production proof.
- Desktop/mobile Playwright PASS; final rebuilt-stack rerun in progress. Runtime dependencies audit and both patched Alpine image high/critical scans PASS; final CI repeat remains required.
- No images published; no RC tag; no ViMag deployment; no real torrent added or modified. Production write defaults remain false.

## Required remaining work (continue autonomously)

1. Finish final browser/source security/secret checks. Subtitle selection/download/timing/attachment, BG verify/revoke, sidecar conflict review, settings, inventory and maintenance are implemented. Resource epochs and heartbeat fencing regression tests pass.
2. Compose, digest validation, backup/restore/deploy/preflight scripts, CI/security/release workflows, generated OpenAPI and runbooks are implemented. Commit and push `codex/rc1`, run/repair GitHub CI, publish only after all checks pass.
3. The existing token received HTTP 403 reading repository secret names: registry credentials are UNVERIFIED, not known absent. Attempt the gated publication workflow and record the actual outcome; never invent digests.
4. Deploy only after publication and verified host access/secrets/backup/preflight. Exactly one new isolated authorized harmless torrent; preserve baseline/legacy. Live permissions/credentials have not yet been checked.
5. Update final report with commit/run/digests and precise blockers. RC1 is not passed at this checkpoint.
