# ViMag v1.1 — engineering/API/DB verification contract

> **2026-11-04 Library-first amendment:** For NAS Library inspection, enrichment and normalization, [Library-first normalization](library-first-normalization.md) supersedes historical torrent-dependency gating below. Torrent records and `missingFiles` are not Library normalization blockers. Physical ownership, fingerprints, paths, collisions, exact approvals, leases, journal/recovery and production write authorization remain mandatory. Delete/quarantine and download/import retain their separate dependency protections.

**Status:** approved engineering requirements for future implementation, not implemented; 2026-11-02. Read `docs/v1.1/product-scope.md` and `decisions.md` first. This document contains acceptance obligations rather than a promise of completed implementation.

## Existing RC1 baseline (observed)

- Vue3/Vite/Nginx UI, FastAPI API, Python Worker, PostgreSQL, Docker Compose; qBittorrent and Jellyfin external adapters. No generic file-mutation approval from documentation.
- RC1 `GET /api/v1/library/assets` accepts `category`, `limit`, `offset` but returns `{items}` only; no total/title/quality/stream filters. RC1 Library UI loaded at most one page and used oversized cards.
- One completed inventory scan yielded **4119** video asset rows with `probe.format` and `probe.streams` each present for all 4119; all contain `probe.format.size`, `duration`, `bit_rate` and nonempty streams. Category inventory at one time: Series 3315; Movies 590; Animations 122; Documentaries 92; Concerts 0. Counts may change.
- Of these, 472 had `BG_TAGGED`, zero `BG_VERIFIED`; 157 had recorded torrent dependencies and 3962 did not. Missing recorded dependency is NOT proof of no dependencies.
- RC1 has `POST /api/v1/library/scan`, single-asset normalization plan/approval, single-asset quarantine plan/approval/restore and manual BG evidence APIs. Do not assume these meet v1.1 behavioural requirements.
- Two production Compose gates remain **`VIMAG_WRITE_ENABLED=false`** and **`VIMAG_AUTOMATIC_INTAKE=false`**. Production changes to these are not authorized.
- Published RC1 images and immutable tag `v1.0.0-rc.1` must not be overwritten. A later release needs a distinct tag/digests and tested rollout plan.

## API contracts to design (adapt to existing code structure)

Design versioned, authenticated FastAPI endpoints with normalized error shapes, optimistic concurrency, CSRF, role checks, audit trails; avoid duplicate alternate endpoints. Minimal target capabilities:

1. `GET /library/assets`: `search` (display title + optional path), `category`, `video_quality`, `audio_codec`, `audio_language`, `subtitle_language`, `sort`, `order`, `limit`, `offset`; result `{items,total,limit,offset}`. Filtering/count MUST happen in PostgreSQL, not just current page; stable tie-break sort; validated/enumerated parameters; indexes appropriately. Return normalized video/audio/subtitle stream display fields; identify unknown/untagged honestly.
2. `GET /library/analytics`: aggregate category count and **real bytes** from `probe.format.size`, safe numeric parsing and caching for 4119+ rows, count unaffected by pagination. Include snapshot/last_scan context.
3. `POST /library/scans` + `GET /library/scans/{id}`: incremental scan intents with scope, progress/changed/new/missing/unchanged/failed counts. Keep old endpoint compatible or migrate deliberately. No false missing on incomplete NAS traversal.
4. Policy endpoints: `GET/POST /library/policies` with immutable revisions, versioned hierarchy/tree, naming tokens and live-preview evaluator. Separate publish/activate revision from media moves; invalid/ambiguous unsafe policies rejected, no path traversal or collisions.
5. Normalization: scoped `POST /library/normalizations/plans`, `GET /library/normalizations/{job_id}`, `POST .../approve`, `POST .../(pause|resume|cancel|retry)`, per-file records and phase progress. Reuse RC1 durable queue/journal/locking/fencing infrastructure. Plan hash/revision and dry-run, stale-plan rejection, one-approval auto phased execution, restart-resume.
6. Quarantine: existing single operations + bulk scoped plan/confirm/restore with target manifests; collision block and per-file success/failure, no automatic eviction/retention.
7. Delete: **new separate explicit endpoint** for single/bulk physical deletion only, with exact owned-video/sidecar deletion plan, permission, user confirmation and qBt dependency guards; record outcome and clear active catalogue only after filesystem success; recover partial state via journal. No implicit delete from maintenance/quality decisions.
8. Subtitle: provider search/match, exact candidate evidence and selected-primary with version manifest, restore prior `ver-NN`; no accidental duplicate filenames or default track ambiguity. Check Jellyfin behavior before finalization.
9. Media identity: TMDb IDs, linked IMDb IDs, collection ID/title provenance and manual override; collection conditional placeholder `{CollectionName}`, validation and directory preview.

Prefix all appropriate paths with existing `/api/v1`, evolve OpenAPI contract and TypeScript types; use migration compatibility. Suggested endpoint names are descriptive, not absolute when current consistent routes should be extended.

## Data model / migrations

- Existing assets need normalized searchable `title`, `category`, video dimensions/quality tier, audio codec and language arrays, subtitle language arrays, durable media IDs and inventory availability; avoid recomputing full ffprobe in paginated GET.
- Store `file_size_bytes` as a precise integer sourced from `data.probe.format.size` where valid; use it for volume analytics; do not invent demo TB values. Nullable unknown size.
- Incremental scan snapshots/last_seen, file fingerprint, mtime/size identity, scope successful-enumeration proof; versioned changes and missing states distinct from quarantine.
- Versioned policy rules with snapshot of active revision on each job, optional collection folder and per-category overrides.
- Parent Normalization job + per-file operation and stage state, intent journaling, locks, attempt counts, replay tokens, recovery and per-operation audit.
- Subtitle version manifests distinguish current primary, historical `ver-02` etc, source provider/release, calculated FPS/duration/encoding/sync evidence; rollback/restore without loss of variants.
- Quarantine manifests restore original media and exclusive sidecars; delete tombstone/audit, correct FK sequencing; no broad cascades erasing unrelated history.
- DB migrations are forwards/backwards assessed, tested on disposable backed-up RC1-shaped fixtures, documented recovery. No live DB schema writes merely to sync docs.

## Safety and stage semantics

- Worker is sole filesystem mutator; API has no NAS write mounts. No general `rm -rf` or arbitrary path deletion from client input.
- Existing 92 legacy qBittorrent torrents must not be modified automatically. Delete/quarantine and import retain torrent dependency checks. Library normalization ignores historical torrent references and checks physical ownership, unknown hardlinks, fingerprints, containment and collisions independently.
- Require path containment under configured Library (or dedicated Quarantine for restore), no symlink traversal, exact file identity/fingerprint before and after mutating. Sidecars selected by ownership manifest; avoid deleting shared NFO/artwork, collection cover or sibling episode subtitles.
- Read-only scan can run with writes off because it writes *database inventory only*; physical actions remain fail-closed behind existing deployment gates.
- Phase 1 identity/metadata builds match evidence; phase 2 hierarchy/naming uses NAS ownership and exact approved manifests, independent of legacy torrent mappings; phase 3 subtitle candidate evaluation includes **FPS, duration, encoding**, edition, completeness, language, sync and provider, uses separate atomically published/renamed assets with history; phase 4 Jellyfin refresh verifies targeted item.
- Pause stops new items and allows currently active operation to reach safe checkpoint; Cancel affects unfinished items, not completed physical operations. Reconcile on crash before retrying.
- BG audio is accepted when detected by stream evidence as owner's v1.1 policy; retain provenance/uncertainty. BG-first retention of important editions remains. Do not blindly relabel streams lacking Bulgarian signal.
- No automatic physical deletes or quarantine from normalizations, dedup comparison or policy saves. Explicit DELETE-01 user intent, plan and confirmation only.

## User interface completion criteria

- Use committed `wireframes/v1.1` assets as reference, NOT production code; replace demo data/buttons with authenticated real server APIs and proper states. Collapsible persistent nav is responsive and keyboard operable.
- Compact modals for single/bulk quarantine and delete with accurate exact file count and impact; protected rows provide reason rather than enabling unsafe execution; no giant JSON dumps in standard browsing.
- Table and Card views have identical server filters and pagination; search covers all 4119+ rows. Reset offset on criteria change. Show empty/error/loading states. Analytics aggregates across all rows, not just current page.
- Bulk normalize plan and status show phase, totals, individual error, NeedsReview, pause/resume/retry and recovery. Never mark all Completed when warnings/failures exist.

## Automated acceptance tests required (extend RC1 suite, do not delete)

- API count=4119 with pagination boundaries, mixed category/title search, multi-stream audio/subtitle filters and actual byte totals, SQL injection/path input rejects; stable pagination under updates.
- No false missing assets on inaccessible NAS, partial errors or concurrent scans; changed file detected without repeated full probes; physically deleted or missing records treated consistently.
- Token drag/drop persistence, nested Collection level and invalid policy rejection; change Settings creates policy revision but performs **zero filesystem operations**.
- Composite exact-name collision and edition/collection classification; ambiguous TMDb → NeedsReview. Legacy torrent references do not block normalization; ambiguous physical ownership still blocks unsafe rename/move.
- New BG signal recognized without confirmation; unknown/contradictory signal not fabricated.
- Subtitle timing/encoding/FPS/duration candidate selection; bad encoding, subtitle misalignment, movie cut mismatch; correct ver-02/ver-03 shift, restore and simulated crash mid-shift; Jellyfin preferred-track discovery.
- Bulk phases and one approval; file-level error continues other files; pause/retry/cancel idempotency/restart, no duplicate moves or subtitle versions.
- Single/bulk quarantine reversible, original-path collision fails safe, associated file ownership, partial failure and shared sidecars preserved.
- Single/bulk delete removes only selected file(s) and exclusive sidecars, no torrent action, blocks active/legacy dependencies, updates DB after physical proof, no false success on FS errors, skips sibling episode/collection files, audit persists.
- Restore and backup/migration dry-run, integration fixtures in ephemeral PostgreSQL and simulated NAS/qBt/Jellyfin, CI frontend/build/tests/security checks with no secrets in logs.

## Implementation handoff gating

This document is an **approved specification**, not permission to commence coding or deploy. Once documentation is reviewed and repository sync verified, user will separately instruct Codex. Do not create a release tag, publish images or activate production writes in documentation-only work.
