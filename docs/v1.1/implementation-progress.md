# v1.1 implementation ledger

Authorized by the owner's 2026-11-02 implementation kickoff. Base `645bebf85fabf05f8b33ce91fd0fbeef721679e3`, branch `codex/v1.1-library-maintenance`, PR target `codex/rc1`. This is implementation work, not a release or deployment authorization.

## Current checkpoint

- Read the approved v1.1 specifications and both wireframes, reviewed RC1 design, implementation, tests and release evidence. The untracked nested `media-manager/` directory is unrelated local content and remains untouched.
- Implemented additive schema 0002; froze RC1's schema for reproducible 0001 upgrades. PostgreSQL catalogue filtering/counts, normalized probe fields, real-byte analytics and invalidation, scan intents and incremental inventory are implemented.
- Implemented immutable organisation policies, live preview, collection hierarchy and manual metadata/collection correction; per-file bulk normalization, exact quarantine/delete manifests, separate approval, controls, audit, leases, recovery, tombstones, sidecar ownership and subtitle version history.
- Implemented compact API-backed Library table/cards, server pagination/filtering, analytics, selection and operation dialogs; visual hierarchy/token editor; persistent sidebar collapse.
- Last complete Linux suite: **85 passed, zero skipped**, including all retained RC1 tests and v1.1 fixtures. Ruff/mypy passed. Frontend: **8 tests passed**, lint/types/build passed at their latest checkpoints. Further checks follow ongoing edits; this is not final evidence.
- Real isolated Jellyfin 10.10.7 test passed: two films under a collection folder, four edition sources, one active Bulgarian subtitle per source, zero discovered history tracks. Image digest is pinned in `tests/compose.jellyfin.yaml`; no host ports or production paths were used.

## Work remaining before final handoff

1. Finish concurrency/recovery edge verification, v1.1 migration/backup evidence and browser interaction fixtures; rerun all checks on final source.
2. Generate OpenAPI; complete v1.1 decisions, traceability, operator/recovery instructions and implementation report.
3. Build local synthetic images, run desktop/mobile Playwright and security checks; fix failures. Push recoverable commits, open PR against `codex/rc1`, inspect and fix hosted CI/security results.
4. Report exact final source/check identities and any unresolved external prerequisites. No tag, image publication or deployment is part of this task.

## Safety boundary

Only local synthetic containers/volumes are used. Production NAS, torrents and settings have not been accessed or changed. Production Compose write/intake defaults remain false. Published RC1 tags/images are not modified. Missing provider credentials produce explicit unavailable/review states, not simulated production success.
