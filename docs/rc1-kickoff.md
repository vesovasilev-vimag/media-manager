# ViMag Media Manager — Codex autonomous RC1 kickoff

**Execution authorization:** 2026-11-01. **Target:** `v1.0.0-rc.1`. **Mode:** one continuous implementation and release-candidate delivery, not a sequence of owner-reviewed prototypes. The owner requested Docker Hub publication, then deployment, then post-deployment integration and a functional test with **one** torrent. This instruction supersedes older milestone handoff expectations but **does not waive safety gates**.

## 1. Read first and obey

- [AGENTS.md](../AGENTS.md) — mandatory agent contract.
- [Technical Scope v1.0](technical-scope-v1.0.md) — complete approved product scope, 22 decisions, T-01..T-43.
- [Implementation Design v1.0](implementation-design-v1.0.md) — all 25 sections, M1..M6, PostgreSQL and operation journal, IT-01..IT-17.
- [Interactive wireframe v1.0](../wireframes/vimag-media-manager-v1.0.html) — seven UI screens and their workflows; adapt to real, persisted backend state.
- [RC1 traceability](rc1-traceability.md) — every scope acceptance scenario MUST be implemented and evidenced before declaring RC1 passed.

No more product Q&A: apply the approved decisions. Record unavoidable implementation assumptions in `docs/rc1-decisions.md`, but never silently change accepted product policy.

## 2. Exact deliverable (not a skeleton)

One cohesive, working application that implements **all** approved scope, with a real backend and persisted state:

| Workstream | Mandatory deliverables |
| --- | --- |
| Foundation | `frontend/`, `backend/`, `deploy/`, `tests/`, `.github/workflows/`, pinned dependency manifests, migrations, complete docs |
| Four-container runtime | Vue/Nginx; FastAPI; Python Worker (same backend image); PostgreSQL; isolated networks and Compose secrets |
| Authentication | Setup for one admin, Argon2id, secure sessions, CSRF, full API authorization, audit, no default password |
| Job orchestration | Seven visible steps, parent/child jobs, durable queue/leases, idempotency, journaled operations, progress/audit, crash reconciliation |
| qBittorrent | v5.2 API auth, safe polling, baseline/ownership guard, eligibility of new torrents, Manual TMM, location/rename/recheck/seeding state verification |
| Library and storage | Category routing, read-only inventory, NAS mounts, simple/multi-file/mixed import plans, one-bind hardlinks, collision and path traversal guards, retry/restore |
| Media intelligence | ffprobe, integrity, TMDb/manual matching, editions, Bulgarian audio evidence, explainable quality and duplicate comparison, review/approval |
| Enrichment | NFO/artwork lifecycle and ownership, subtitles and timing/evidence review, dependency-safe quarantine and restore, verified staging cleanup only |
| Jellyfin | Scan requests, async recognition verification, versions/editions, Movies/Shows grouping, no double indexing, `PublishPending` on mismatch |
| UI | All seven approved screens, genuine APIs (not wireframe demos), Bulgarian-first UI labels, accessibility and responsive layouts |
| Operations | Health/readiness, structured logs, backup/restore, migration rehearsal, diagnostics, release/runbook, recovery/rollback workflow |
| Delivery | GitHub Actions tests/security/build, two Docker Hub images, immutable release manifest, operator deployment instructions, postdeploy evidence |

Do not substitute mock responses for a complete production feature. Mock adapters are permitted **only** in dev/CI fixtures. If an external provider cannot be reached, preserve working error/review states and flag the external dependency truthfully.

## 3. Developer work without owner interruptions

Proceed internally through all six milestones of Implementation Design §23.2, committing coherent increments to `codex/rc1` or an equivalent feature branch, but do not ask the owner to evaluate individual milestones.

- Develop locally or in a Codex workspace, not on ViMag production. Dev Compose must use PostgreSQL with disposable **synthetic media only**, stub qBt/Jellyfin providers, and **no production NAS bind mounts**.
- Run coding checks continuously and fix them autonomously: backend lint/typecheck/tests, frontend lint/typecheck/tests/build, API schemas, database migration tests, mocked integration tests, security checks, Docker build.
- Automate all 43 acceptance scenarios T-01..T-43 and 17 technical IT-01..IT-17 with deterministic fixtures, mocks or contract tests where live infrastructure is not available. Real-infrastructure evidence is **separate** and must not be forged.
- `docs/rc1-traceability.md` is a mandatory exit report: replace each `NOT_RUN` with `PASS` plus exact test file/workflow evidence or `BLOCKED` plus cause; never enter `PASS` solely because code exists.
- Resolve noncritical unknowns conservatively. Where secrets, network access or irreducible validation are unavailable, finish everything else, document the blocker and keep operational write actions disabled.

**No intermediate manual tests, previews or owner sign-offs.** Automated development/CI validation is mandatory; the user's requested **real integration + functional testing occurs after deployment**.

## 4. Security and legacy boundary

Snapshot actual qBt torrent identities on first authenticated, read-only connection. The 92 observed torrents are a **historical baseline**, not a fixed count to hardcode. Any existing or ambiguous torrent is `LEGACY_READ_ONLY` / `EXTERNAL_UNMANAGED`; no silent owner reassignment and no write API calls to old hashes.

New eligible torrents must use Manual TMM, explicit local `/downloads/complete`, one of five approved categories; category savePath currently points to NAS, but category-path use in Manual TMM is false. Never alter five global category roots in order to force this. Until safe cutover, default new-torrent ingestion is opt-in and real actions remain gated.

Current `temp_path_enabled=false`: directory `/downloads/complete` is not a proof of completion. Use authenticated qBt state and hash-based ownership. Expect qBt 5.2 login HTTP 204 and a cookie or configure machine API key as a scoped secret. Do not disable CSRF/Host validation.

Use `/mnt/nas/Movies` as the Worker single host NAS bind, while preserving qBittorrent legacy mounts. Hardlink functionality passed on host and isolated Docker probe with UID 1000:1000; final Worker UID/ACL and production bind are **not yet proven**. CIFS inode and hardlink counts were inconsistent; never trust them alone for delete decisions.

Protect BG editions, manually edited sidecars and torrent data; no permanent library delete endpoint. For active torrents, qBt owns rename/move. A successful HTTP response is not movement completion. Terminal success requires verified library content, recognized Jellyfin entry, and seeding-capable torrent mapping.

## 5. RC1 quality and external dependency gates

| Stage | Required behavior |
| --- | --- |
| **Build/CI (before Docker Hub)** | All available deterministic T/IT tests pass, migrations up/down/restore, ffprobe fixtures, security and SAST/dependency/secret scans, both images built |
| **Release artifact** | Images `vesovasilev/media-manager-web:1.0.0-rc.1` and `vesovasilev/media-manager-backend:1.0.0-rc.1`, SBOM and build provenance, digest-pinned release manifest, rollback steps |
| **Deployment (after Docker Hub)** | Pull images on ViMag with no source/build; validate Traefik/network/secrets, PostgreSQL persistence/backup, current qBt legacy baseline; start in `WRITE_ENABLED=false` |
| **Postdeploy integration** | Real qBt/Jellyfin API connectivity, Worker UID and CIFS hardlinks in scratch, migrations and recovery checks; verify qBt/WebUI config unchanged and legacy hashes unaffected |
| **One functional torrent** | Exactly **one new authorized test torrent** with harmless, legally usable, ffprobe-valid sample media (prefer a multi-file fixture where practical); inspect → compare → approve if required → qBt-managed NAS move → hardlink where applicable → Jellyfin recognize → seeding/recheck; evidence and cleanup/restore guards |
| **Activation** | Production-wide automatic writes and default TMM cutover stay DISABLED until G-01…G-06/G-DB-01 required for that feature are demonstrably passed and explicit operational cutover is authorized. RC1 deployment is **not** automatic production activation. |

The first deployment and single-torrent test must not be used as a substitute for the other automated T/IT scenarios. Do not use an existing NAS movie or any of the 92 legacy torrents as the functional fixture. Record before/after qBt settings and torrent counts; preserve the test torrent's seeding state in case of failure. Do not force global default Manual TMM in order to run the one test — add that **specific fixture** explicitly as Manual.

If deployment credentials or host access are absent, DO NOT claim the app is deployed or the test passed. Finish the code, workflows, manifests and runbooks; report precise external steps and blocked gates.

## 6. Required files for the finished candidate

Follow the monorepo structure in Implementation Design §23.1. In addition, produce:

- `docs/api-contract-v1.yaml`, `docs/qbt-integration-runbook.md`, `docs/storage-mount-matrix.md`, `docs/operations-and-recovery.md`, `docs/deployment-and-backup.md`;
- `docs/rc1-decisions.md` (implementation choices only), `docs/rc1-release-report.md` (truthful evidence), completed `docs/rc1-traceability.md`;
- `deploy/compose.dev.yaml` (synthetic-data only), `deploy/compose.prod.yaml` (images only), secret-file examples, lockfiles, migration scripts, image digest release manifest;
- `.github/workflows/ci.yml`, `security.yml`, `build-release.yml` with CI gates on PR and image publication only after tests;
- backup/restore scripts **tested against disposable PostgreSQL** and a rollback procedure that respects migration compatibility and NAS job journals.

Never silently change a signed-off product policy, invent a credential or fake a release status. No source or real media content is copied to ViMag as a build prerequisite.

## 7. Single final report to owner

Only once implementation is complete or genuinely blocked, provide:

1. Commit/PR/RC tag and complete feature coverage.
2. Exact pass/fail results for 43 T and 17 IT scenarios and gate evidence; reason for each blocked integration test.
3. Docker Hub image URLs **with actual digests**, not expected tags.
4. Deployment outcome on ViMag; current state of `WRITE_ENABLED` and the 92 legacy torrents.
5. One-torrent test outcome and Jellyfin/seeding evidence (if actually executed).
6. Only unavoidable external credentials/permissions that must be supplied.

**Exit condition:** RC1 is finished only when code, docs, CI and all automatable cases are complete. Image publication/deployment/live checks may remain separately BLOCKED solely on missing external access; never mislabel a build-only handoff as a fully verified RC1.
