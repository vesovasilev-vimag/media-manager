# Codex execution contract — ViMag Media Manager

> **Version routing note (2026-11-02):** This AGENTS.md remains the historical RC1 coding contract for v1.0. A **separately authorized** v1.1 coding task must use the versioned [docs/v1.1/README.md](docs/v1.1/README.md), [product-scope.md](docs/v1.1/product-scope.md), [engineering-contract.md](docs/v1.1/engineering-contract.md), [decisions.md](docs/v1.1/decisions.md) and committed [wireframes/v1.1](wireframes/v1.1/) as the owner-approved superseding product requirements while retaining unaffected RC1 safety invariants. This note does **not** authorize development, production writes, deployment, or republishing RC1.


This file is the repository-level instruction for any coding agent working toward **Release Candidate 1 (RC1)**. Read it **before making changes** and read the referenced documents completely.

## Mission: one uninterrupted execution to RC1

Deliver the **entire approved v1.0 product**, not an MVP or UI-only prototype, on the RC1 branch. The owner has explicitly requested **no intermediate questions, manual testing sessions, demo approvals, or phase-by-phase handoffs**. Make safe implementation decisions independently, record them in `docs/rc1-decisions.md`, implement the full stack, run and fix automated checks yourself, and report only when the RC1 deliverable is ready or a genuine external blocker remains.

Do not claim to run in the background or promise a future result without actually executing the work. If the execution environment imposes limits, leave recoverable commits, an accurate progress ledger, and a concrete remaining-work list. Resume from the ledger without asking the owner to repeat instructions. Never falsely report an incomplete feature, unrun test, unpublished image, or undeployed service as complete.

## Source-of-truth order

1. Current explicit owner directives in `docs/rc1-kickoff.md` (execution cadence and release sequence).
2. `docs/technical-scope-v1.0.md` (**approved product policy**, 22 decisions, T-01..T-43).
3. `docs/implementation-design-v1.0.md` (**approved architecture**, IT-01..IT-17, G-01..G-06, G-DB-01).
4. `wireframes/vimag-media-manager-v1.0.html` (**approved seven-screen UX**; mock data must be replaced with real state).
5. README as a summary only; if stale, correct README rather than overriding approved decisions.

Implementation Design supersedes earlier exploratory SQLite suggestions: **PostgreSQL is required**. Treat the seven workflow steps, 43 T tests and 17 IT tests as mandatory traceable requirements, not optional inspiration. Do not silently drop complex capabilities because an external provider is unavailable.

## Approved target architecture

- Monorepo; Vue 3 + TypeScript + Vite/Nginx web UI; FastAPI API; separate Python/ffprobe Worker; PostgreSQL persistence/queue. **Four runtime containers, two custom images** (web and shared API/worker backend).
- Python migration/transaction design with PostgreSQL `FOR UPDATE SKIP LOCKED`, leases, idempotency, operation journal, reconciliation and audit. No Redis/RabbitMQ for v1.
- Dev: synthetic fixtures and emulated adapters only. Production: Docker Compose **pulls** immutable images from Docker Hub `vesovasilev`; no production source checkout/build and no unattended auto-update.
- Registry target: `vesovasilev/media-manager-web:1.0.0-rc.1` and `vesovasilev/media-manager-backend:1.0.0-rc.1`, plus pinned digests in a release manifest. Build on GitHub Actions once all automated RC checks pass.
- Respect Traefik/Tailscale and the existing `vimag_default` Docker network; do not publish PostgreSQL, Worker, or qBittorrent Web API on public ports.
- One admin, Argon2id, secure server-side sessions, CSRF, protected API, audit, secret files and least privilege.

## Hard safety invariants (non-negotiable)

- The **92 qBittorrent torrents observed on 2026-11-01 are legacy, NOT owned by ViMag**. Snapshot current torrents when deployed; never auto-modify a torrent already present at first startup, even if count differs. No bulk `hashes=all` writes, no automatic global category-path rewrites, no migration of legacy payloads.
- qBittorrent v5.2.0/Web API 2.15.1 was verified read-only. Login may return HTTP 204 with a session cookie. Implement the 5.2 API-key option securely and support a verified session approach if required. A 200 response to `setLocation` is NOT proof of completed movement.
- Five category names are exact: `movies`, `series`, `animations`, `documentaries`, `concerts`. New ViMag-managed torrents use Manual TMM, category preserved, `savepath=/downloads/complete`; `use_category_paths_in_manual_mode=false`. Current `temp_path_enabled=false` means partial payload may already be in `complete`: never interpret file presence as download completion.
- Host mounts: `/mnt/storage/qbt` and `/mnt/nas/Movies`. Only Worker receives the NAS root as ONE bind (e.g. `/nas-movies`) to support within-mount hardlinks. Do not alter existing qBittorrent/Jellyfin mounts during development. Actual qBt production mount changes require a validated cutover procedure.
- A simple torrent uses qBt-aware rename/move; multi-file/season packs use a validated NAS torrent-store tree + same-share hardlinks into Jellyfin. Parent/child jobs for mixed torrents. Respect paused/queued state; zero upload speed alone does not mean failure.
- Preserve verified Bulgarian-audio editions, and keep a materially better non-BG version when justified; `BG` filename suffix only with strong stream-bound verification. Never trust a language tag alone.
- No permanent deletion of library or quarantine assets in v1, **even after approval**. Automated cleanup is allowed ONLY for proven disposable staging copies, with dependency and integrity proof. Quarantine is explicitly approved, journaled, reversible, and blocked when torrent dependencies exist.
- No overwrite of unknown or externally edited sidecars. ViMag-owned unchanged NFO/artwork may be updated atomically with hash and journal validation.
- No terminal Completed/CompletedWithWarnings until **NAS integrity + qBt seeding capability + Jellyfin catalogue recognition + all critical child checks**. Missing noncritical subtitle may warn; Jellyfin pending cannot.
- Default to `WRITE_ENABLED=false` on the first ViMag deployment. No real-media mutations or global qBt setting changes without preflight, backups, safety-gate proof, explicit operational authorization, and a **single isolated new test torrent after deployment**.
- Never commit credentials, API keys, cookies, tracker URLs/passkeys, personal media, private inventory, secrets, or production databases. The Jellyfin token previously shown in a conversation MUST be rotated before pilot. Do not invent or echo credentials.

## Autonomous work loop

1. Inspect repo and documents; fill `docs/rc1-decisions.md` only for technical choices not decided in the approved specs.
2. Implement all M1..M6 milestones from Implementation Design §23 (not as separate user-facing deliverables), all seven screens and real backend APIs.
3. Maintain `docs/rc1-traceability.md`: each of T-01..T-43, IT-01..IT-17 and all gates must show an exact test/evidence reference. Untested means NOT VERIFIED.
4. Run autonomous checks throughout coding (lint, typecheck, formatting, backend/frontend unit tests, mocked adapters, ephemeral PostgreSQL migrations, synthetic hardlink/failure-injection fixtures, security regressions). **Never ask owner to run intermediate tests.** No live qBt/NAS pilot during coding.
5. Fix failures and rerun. Keep CI green; do not suppress, skip or fake tests to produce a passing result. Record upstream outages and alternatives precisely.
6. Deliver docs, source, Dockerfiles, development/production Compose, CI/security/release workflows, backups and restore scripts, OpenAPI, dependency locks, operator runbook, reproducible synthetic fixtures, RC1 release evidence.
7. Build/publish two Docker Hub images via GitHub Actions when required credentials are available, using pinned image digests and no embedded secrets. Missing external permissions/secrets are **external blockers**; finish all independent work before reporting them.
8. **After image publication**, perform controlled deployment to ViMag *only when runtime access, secrets, backup and permission preconditions are actually satisfied*. Run read-only integration/preflight and **exactly one new isolated, authorized, harmless test torrent** for functional validation after deploy. Do not treat the owner's wish for uninterrupted execution as permission to modify legacy torrents or bypass safety gates.
9. Produce `docs/rc1-release-report.md` with commit, tests and results, digest references, deployment outcome, remaining gates, restore evidence, known limitations and RC1 pass/fail. Do not mark RC1 PASSED if any required gate or invariant is unresolved.

## Blockers, product decisions, and exit

- Do **not** pause for questions about UI variants, APIs, library paths or optional defaults that the documents already answer. Choose conservative behavior, document rationale, implement it.
- If an essential third-party credential, deployment permission, sample or service is genuinely unavailable, implement its adapter, configuration and deterministic tests; clearly mark the live test as BLOCKED. Do not invent working integrations.
- Do not start unrelated work, transcode/remux media, broaden feature scope, destroy or reorganize existing libraries, or expose new internet ports.
- Avoid committing incomplete core features disguised as successful work. If interrupted, write a precise work ledger for the next Codex execution.
- Final response should be a compact RC1 handoff with links, evidence and **only unavoidable external actions**. No interim user approval requests.
