# RC1 execution ledger

Work branch: `codex/rc1`. Owner authorization: Issue #1 and rc1-kickoff.md. No intermediate owner actions or manual tests requested.

## Current checkpoint (2026-11-01)

- Read AGENTS.md, kickoff, full technical scope, implementation design, traceability, developer setup and approved wireframe; fetched GitHub Issue #1 through the connected GitHub account.
- Started local Docker Desktop and downloaded workspace-local uv/Python (ignored `.tools`, `.venv`). No production access or media mutation.
- Implemented PostgreSQL schema/migration, session/CSRF/security, intake baseline and generations, leases/journal, qBt/Jellyfin/TMDb/subtitle adapters, core transfer/enrichment, quarantine/restore, seven Vue screens bound to APIs.
- Executed **70 backend tests in Linux: PASS, zero failures/skips**, including real disposable PostgreSQL migrations, backup/restore, ffprobe, symlink/hardlink, fault/replay, auth and mock provider contracts. All 43 T and 17 IT identifiers traced in `rc1-automated-evidence.json`. Frontend lint/TypeScript/4 unit tests/build and desktop/mobile Playwright PASS on application commit `f4a12f0646f0bdf92b70ce57bf502ed89eb8fabf`.
- GitHub CI `41324806382` and Security `41324806438` PASS. Actual final Trivy backend/web artifacts each contain zero HIGH/CRITICAL findings. Real provider health, stale heartbeat and private JSON logs tested; actual quality factors and explicit material-improvement review reach the comparison UI.
- No images published; no RC tag; no ViMag deployment; no real torrent added or modified. Production write defaults remain false.

## Required remaining work (continue autonomously)

1. External blocker confirmed by the actual release job: repository Actions receives empty `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. Supply the authorized registry secrets outside chat/Git, then rerun failed release jobs. The connected repository-owner API works for source writes; local Git push credentials do not, so continue with connector tree/commit/ref operations if needed.
2. Source/docs/workflows and all deterministic checks are complete. Production DB bootstrap was also tested in actual disposable PostgreSQL: runtime has none of the five cluster-admin attributes; API/Worker do not receive the separate admin secret. No RC tag, registry images or immutable digest artifact exists while the registry gate is closed. Do not invent them or bypass CI with local push.
3. Only after actual image publication, check runtime access, rotated Jellyfin token, backups/restore, NAS UID/ACL/mount and Traefik/network prerequisites. Deploy read-only and establish the actual legacy baseline.
4. Execute exactly one new harmless fixture only after scoped authorization and all applicable proofs. Preserve legacy torrents and test seeding on failure. Keep broad automatic intake and writes disabled.
5. Record actual digests, deployment/pilot observations and remaining G-01..G-06/G-DB-01 evidence in the release report. RC1 remains BLOCKED until these gates pass; no owner intermediate testing is requested.
