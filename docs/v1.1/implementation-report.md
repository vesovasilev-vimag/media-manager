# ViMag v1.1 implementation report

Review deliverable: [PR #4](https://github.com/vesovasilev-vimag/media-manager/pull/4), `codex/v1.1-library-maintenance` → `codex/rc1`. Owner-authorized baseline: `645bebf85fabf05f8b33ce91fd0fbeef721679e3`. This work does not publish a release or authorize production deployment.

## Implemented behavior

The Library uses PostgreSQL filtering, stable pagination and normalized stream metadata across the full catalogue, with real-byte analytics and cross-process cache invalidation. Incremental scans preserve identity, reuse unchanged probes, expose progress/errors and require completed enumeration before marking files missing. The compact table/cards share filters, selection and pagination; navigation collapse persists on desktop and remains accessible on mobile.

Organisation policies are immutable versions with visual hierarchy/token editing, conditional collections and API-backed previews. Saving a policy performs zero filesystem operations. Metadata matching retains TMDb/IMDb/collection provenance, manual corrections and explicit review for ambiguity. Detected Bulgarian stream evidence is accepted according to BG-01 while preserving uncertainty and provenance.

Bulk maintenance snapshots exact manifests and policies, then executes identity, naming/hierarchy, subtitle and Jellyfin phases under one explicit approval. Per-file durable state, journal/fencing, pause/resume/cancel/retry and crash reconciliation preserve independent outcomes. Unknown or legacy torrent dependencies block affected physical operations. Exact ownership protects shared/externally changed sidecars. Quarantine has collision-safe single/group restores; physical delete has its own exact confirmed plan and durable tombstone, and never issues torrent deletion commands.

Subtitle candidates carry timing, FPS/duration, encoding, edition, completeness and provider evidence. Accepted candidates publish one primary atomically; immutable history outside Library exposes `ver-02`/`ver-03` manifests and reversible version restore. Forced/SDH variants remain separate. Additive migration 0002 upgrades RC1-shaped data and retains pending journal evidence; production rollback/recovery requires compatible code, backups and filesystem reconciliation.

## Executed verification

| Check | Result and evidence |
|---|---|
| Backend/acceptance/integration, Linux + disposable PostgreSQL | **94 passed, zero skipped**; includes 4119-row catalogue, migrations/backups, safe delete/quarantine, sidecar ownership, subtitle version/crash recovery and all historical T/IT regression identifiers |
| Backend formatting/lint/types | Ruff checks passed; mypy passed for 21 application modules |
| Frontend | **8 passed**; ESLint, vue-tsc and production build passed |
| Browser, rebuilt four-container synthetic stack | **2 passed**; seven screens, responsive sidebar, pagination/filter/card selection, compact deletion preview, hierarchy/token persistence and zero filesystem changes on policy save; desktop/mobile screenshots visually reviewed |
| Real Jellyfin 10.10.7, pinned isolated container | **PASS**: two films, four edition sources, one current BG subtitle per source, zero discovered history tracks; exact-path application adapter recognition verified |
| OpenAPI and repository hygiene | OpenAPI regenerated; `git diff --check` passed; historical RC1 release evidence and immutable artifacts preserved |
| Hosted CI/security | Follow-up publication and final hosted verification in progress; this row must be replaced before final handoff |

[Traceability](traceability.md) and [machine-readable executed evidence](automated-evidence.json) identify exact test references and SHA-256 source fingerprints. Hosted workflow artifacts retain JUnit, isolated Jellyfin JSON and browser screenshots. T-25/BG and T-42/deletion are explicitly superseded by approved v1.1 decisions; original RC1 reports are unchanged.

## Commits and review

- Baseline: `645bebf85fabf05f8b33ce91fd0fbeef721679e3`.
- Published implementation checkpoint: `2b6aaa9d0f79dd07dd71fb5bffe036536c79727a`.
- Follow-up hardens crash recovery, per-file restore, sidecar/dependency proof, identity/subtitle concurrency, browser coverage and versioned evidence. Final source/check identities will be recorded after hosted verification.

The connected repository-owner GitHub account publishes the feature branch. A separate local CLI account lacks push permission; connector-created commits are verified against the exact local Git tree, and local recovery commits are retained. No RC1 tag or published image is altered.

## Limits and separate deployment prerequisites

No production NAS, qBittorrent, Jellyfin or provider account was accessed or changed. External-provider behavior is deterministically tested; missing credentials remain explicit unavailable/review states. The real Jellyfin compatibility claim applies to pinned 10.10.7. Live CIFS semantics, production server versions and credentials remain operational validation prerequisites, rather than fabricated implementation-test results. Ambiguous identity, unknown hardlink ownership and uncertain torrent dependencies deliberately require review.

Before a separate deployment decision: review/merge the PR, create distinct immutable v1.1 images/digests, verify backup/restore and schema compatibility, confirm NAS containment/hardlink semantics and current torrent baseline, rotate the previously exposed Jellyfin token, provision secrets and verify read-only integrations. Keep `VIMAG_WRITE_ENABLED=false` and `VIMAG_AUTOMATIC_INTAKE=false` until separately authorized preflight and the existing isolated pilot gates pass. No image publication, release tagging, deployment or production write activation occurred in this task.

Physical delete is irreversible filesystem removal: a database backup alone cannot restore removed media. Operators must review the exact manifest and maintain independently verified media backups before authorizing it. [Operations and recovery](operations-and-recovery.md) describes the supported commands and failure handling.
