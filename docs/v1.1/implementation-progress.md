# v1.1 implementation ledger

Authorized by the owner's 2026-11-02 implementation kickoff. Base `645bebf85fabf05f8b33ce91fd0fbeef721679e3`, branch `codex/v1.1-library-maintenance`, PR target `codex/rc1`. This is implementation work, not a release or deployment authorization.

## Completed implementation

- Read the approved v1.1 specifications and both wireframes, reviewed RC1 design, implementation, tests and release evidence. The untracked nested `media-manager/` directory is unrelated local content and remains untouched.
- Implemented additive schema 0002; froze RC1's schema for reproducible 0001 upgrades. PostgreSQL catalogue filtering/counts, normalized probe fields, real-byte analytics and invalidation, scan intents and incremental inventory are implemented.
- Implemented immutable organisation policies, live preview, collection hierarchy and manual metadata/collection correction; per-file bulk normalization, exact quarantine/delete manifests, separate approval, controls, audit, leases, recovery, tombstones, sidecar ownership and subtitle version history.
- Implemented compact API-backed Library table/cards, server pagination/filtering, analytics, selection and operation dialogs; visual hierarchy/token editor; persistent sidebar collapse.
- Final local Linux suite: **94 passed, zero skipped**, including all retained RC1 tests and v1.1 fixtures. Ruff formatting/lint and mypy passed (21 application modules). Frontend: **8 tests passed**, lint/types/build passed. Rebuilt synthetic stack: **2 Playwright tests passed** at desktop/mobile, including API-backed pagination, compact deletion preview, policy/token persistence and sidebar behavior. Screenshots were visually reviewed.
- Real isolated Jellyfin 10.10.7 test passed: two films under a collection folder, four edition sources, one active Bulgarian subtitle per source, zero discovered history tracks. Image digest is pinned in `tests/compose.jellyfin.yaml`; no host ports or production paths were used.

## Verification and handoff

Published source `80dce4f7d6d0efe1e90518da011ff35f29e11f22` passed [CI](https://github.com/vesovasilev-vimag/media-manager/actions/runs/41521447792) and [security](https://github.com/vesovasilev-vimag/media-manager/actions/runs/41521447244), including 94 backend, 8 frontend and 2 browser tests, real Jellyfin and database least-privilege checks. [PR #4](https://github.com/vesovasilev-vimag/media-manager/pull/4) targets `codex/rc1`. The [implementation report](implementation-report.md) records commits, artifacts, supported limits and deployment prerequisites. No implementation work remains outstanding.

OpenAPI, migration/backup/recovery fixtures, versioned traceability and operations instructions are complete. [Executed evidence](automated-evidence.json) fingerprints the reviewed source and records all 60 historical T/IT identifiers, with the approved BG/delete supersessions explicitly identified. No tag, image publication or deployment is part of this task.

Final compatibility review added migration-only backfill from existing RC1 quarantine manifests, preserving restored/active distinctions and restore evidence. The expanded migration fixture and full 94-test backend suite passed again. During verification the repository owner merged PR #4 as `2c6cfc6`; [PR #5](https://github.com/vesovasilev-vimag/media-manager/pull/5) therefore contains the final compatibility correction (`45953a0`) against the updated `codex/rc1`. Final head CI/security are visible under PR #5 checks. No runtime/production migration was performed.

## Safety boundary

Only local synthetic containers/volumes are used. Production NAS, torrents and settings have not been accessed or changed. Production Compose write/intake defaults remain false. Published RC1 tags/images are not modified. Missing provider credentials produce explicit unavailable/review states, not simulated production success.
