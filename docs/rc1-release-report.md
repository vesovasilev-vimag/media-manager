# ViMag Media Manager 1.0.0-rc.1 release evidence

**Decision: RC1 ARTIFACTS PUBLISHED — OPERATIONAL VALIDATION PENDING (NOT RC1 PASSED).** Source and automated suites have passed, two multi-architecture Docker Hub images are published with real immutable digests and a validated deployment artifact exists. ViMag deployment, live host safety gates and one-torrent pilot have **not** been executed. General production writes remain disabled by the Compose defaults.

## Source and validation identity

- Validated application commit: [`f4a12f0646f0bdf92b70ce57bf502ed89eb8fabf`](https://github.com/vesovasilev-vimag/media-manager/commit/f4a12f0646f0bdf92b70ce57bf502ed89eb8fabf), branch `codex/rc1`.
- Exact source tree: `4d86adbefa97bb62f237db364238372c8d763b31`. Later documentation/release-trigger changes preserve the tested application and production bootstrap inputs.
- [Final CI](https://github.com/vesovasilev-vimag/media-manager/actions/runs/41324806382): PASS; backend, frontend and desktop/mobile browser jobs completed successfully.
- [Final Security](https://github.com/vesovasilev-vimag/media-manager/actions/runs/41324806438): PASS; runtime Python/npm dependency audits, Bandit, Gitleaks and both container scans. Both actual Trivy reports have **0 HIGH/CRITICAL findings**. No vulnerability suppression is used; the narrow Gitleaks exception matches only generated source SHA-256 lines.
- [Release attempt](https://github.com/vesovasilev-vimag/media-manager/actions/runs/41324806470): **BLOCKED on registry credentials** after all verification/security/browser jobs passed. `prepare` job `124903168817` observed empty `HUB_USER` and `HUB_TOKEN` on 2026-11-01 and failed its registry prerequisite. Publication/manifest jobs were skipped. No RC tag was created.
- [Successful RC1 publication](https://github.com/vesovasilev-vimag/media-manager/actions/runs/41327366195): all verify/security, prepare, both publish jobs and manifest PASS, run source `3305709695a16d8ea49beb1da8a2a553a9340469`.
- RC tag: [`v1.0.0-rc.1`](https://github.com/vesovasilev-vimag/media-manager/tree/v1.0.0-rc.1) points to `3305709695a16d8ea49beb1da8a2a553a9340469`.
- Web: `vesovasilev/media-manager-web@sha256:6da8af69364252c6b988325ec7592837b6940eb29321b05155c579e94b235d20` (pushed, GitHub publish job `124910754472`).
- Backend: `vesovasilev/media-manager-backend@sha256:410f93ed480ca4e9785a4837d0ad74a769c79fea722e32b3cf16088b00c52a37` (pushed, GitHub publish job `124910754490`).
- [Validated `rc1-deployment` artifact](https://github.com/vesovasilev-vimag/media-manager/actions/runs/41327366195/artifacts/13092350630): upload/manifest job `124911405736` PASS; includes immutable release manifest, production Compose and runbooks. PostgreSQL pinned reference is preserved in the published manifest. The repo's `deploy/release-manifest.pending.json` is intentionally not deployable.

## Delivered implementation

All M1–M6 workstreams have source, configuration and deterministic verification: four-container Vue/Nginx/FastAPI/Worker/PostgreSQL architecture; seven persisted API screens; one-admin Argon2id sessions/CSRF/audit; immutable torrent baseline and generation guards; durable SKIP LOCKED queue, resource epochs, heartbeat fencing, intent journal and reconciliation; ffprobe/TMDb/manual identity, editions and BG evidence; explainable actual media factors and explicit material-quality review; qBt-aware simple moves and torrent-store/hardlink parent/child imports; owned atomic NFO/artwork, subtitle provider/download/timing/review/attachment; exact Jellyfin recognition gates; inventory, approved normalization and reversible dependency-blocked quarantine/restore; staging-only cleanup proof; structured private diagnostics, readiness, backups/restore/migrations and operator/release tooling. PostgreSQL bootstrap has a distinct admin secret; API/Worker use a role without cluster-admin attributes. Deployment rejects a privileged runtime role, and CI rehearses the actual production initialization SQL in a disposable database.

Unknown source provenance, ambiguous identity, uncalibrated quality and unverified subtitle timing remain visible review states. G-05 is not bypassed with an invented score. Production adapters are implemented; external services in automated tests are emulated. No production integration is claimed from those results.

## Executed automated evidence

| Check | Result | Evidence |
|---|---|---|
| T-01…T-43 | 43/43 automated PASS | [Exact test references](rc1-traceability.md), [sanitized JUnit-derived evidence and source hashes](rc1-automated-evidence.json) |
| IT-01…IT-17 | 17/17 automated PASS | Same traceability; live operational gates below are separate |
| Full Linux backend/API/storage suite | 70 PASS, 0 failed, 0 skipped | Real disposable PostgreSQL and filesystem; generated ffprobe media; emulated providers; CI `backend-evidence` |
| Backend formatting/lint/types | PASS | Ruff format/check and mypy, CI backend job |
| Frontend lint/types/unit/build | PASS, 4 unit tests | CI frontend job and `frontend-evidence` |
| Desktop/mobile browser | PASS on final application source | Enrollment/login/logout, seven API-backed screens, no JS errors or viewport overflow; CI browser evidence |
| Migration and restore | PASS in disposable Linux environment | Down/up, serialized migration, custom pg_dump, empty isolated restore, journal/audit recovery and schema compatibility in `tests/integration/test_operations.py` |
| Production database privilege bootstrap | PASS in real disposable PostgreSQL | CI backend job `124902404359`, step `Production database least privilege bootstrap`: all five forbidden role flags false, schema/data operations succeed; admin secret absent from API/Worker |
| Fault, concurrency and security | PASS | Duplicate/replay, asynchronous move/recheck, stale epochs/heartbeat, NAS failure, collisions/symlinks, legacy guards, auth/CSRF, no-delete and dependency tests |
| Runtime/image security | PASS | Final Security artifacts: dependency audit/SAST and both Trivy JSON reports |

The Starlette test client emits one upstream HTTPX deprecation warning. It does not skip tests or affect production HTTP clients.

## Deployment and operational gates

| Gate/step | Result and exact boundary |
|---|---|
| Docker Hub publication and digest/SBOM/provenance artifact | **PASS (2026-11-01):** tag, two pushed multi-architecture images, actual digests and validated release artifact. GitHub Actions run `41327366195` |
| G-01 qBt | Historical authenticated read-only 5.2.0/API 2.15.1 discovery documented in approved design. Mocked 204-cookie/API-key/async commands tested. No live write fixture executed in this implementation session |
| G-02 NAS | Synthetic same-share hardlink/content/failure tests PASS. Historical CIFS scratch proof is documented. Actual deployed Worker UID/ACL/bind and qBt store mount remain unverified |
| G-03 Jellyfin | Adapter and exact async recognition contracts PASS. Actual Movies/Shows roots, editions, NFO saver and non-overlapping indexing remain unverified |
| G-04 Recovery | Synthetic crashes, lease fencing, journal replay, dependency-safe restore PASS. Host-specific rehearsal pending |
| G-05 Media validation | Synthetic BG/quality/identity/subtitle policies PASS. Representative anonymized sample calibration and live provider results pending; automated quality activation remains gated |
| G-06 Inventory | Synthetic read-only inventory and fresh content/dependency guards PASS. Full live five-category catalog/dependency mapping pending |
| G-DB-01 | Disposable PostgreSQL migration/concurrency/backup/restore PASS. ViMag ext4/XFS PGDATA, permissions and host restore proof pending |
| Deployment / read-only integration | **NOT RUN:** image publication is complete, but ViMag host access, private TLS/middleware, secrets, token rotation, production PostgreSQL restore, host/NAS permissions and preflight evidence remain unverified. No production host was accessed or changed |
| Exactly one new harmless torrent | NOT RUN: no torrent added. Original color/sine multi-file generator is supplied in `tests/fixtures/generate_fixture.py`; no real media or fabricated provider ID used |
| Write state / legacy | Production Compose defaults `WRITE_ENABLED=false`, automatic intake false. No deployed ViMag instance created by this work. No legacy torrent was modified by this work; current live count was not re-observed |

## Unavoidable external action and resume

**Registry blocker resolved:** repository Actions secrets became accessible and publication run `41327366195` passed. Do not rerun this immutable RC tag/image publication pipeline merely to repeat completed work: the workflow deliberately refuses to overwrite existing RC images. Do not copy registry secret values into documentation or logs.

Next: download and verify the published deployment package, establish actual runtime access/preflight, rotate the Jellyfin token, perform private backups/restore and mount/network proofs. Runtime credentials and host access were deliberately not tested before publication; they are **unverified**, not asserted absent. Deploy read-only, establish the fresh actual legacy baseline, then execute exactly one new isolated harmless torrent only under the scoped operational authorization. General production write activation remains a separate gated cutover.

Local Git credentials for `VesoVasilev` returned push 403. This was resolved through the connected repository-owner GitHub API, verifying identical Git tree SHAs and retaining recovery branches; it is not a remaining blocker. Source is committed and published to `codex/rc1`. No intermediate owner test, demo or approval was requested.
