# Library-first normalization and metadata enrichment

Owner request: 2026-11-04. Baseline: v1.1.1 / merged PR #12, `3d34ecf`. Implementation branch: `feat/library-first-normalization`. This authorizes a PR only; no merge, release images, publication, deployment or production NAS/database/torrent changes.

## Separation and safety

Library inventory, metadata inspection, bulk normalization and the compatible single-asset normalization route do not query `qbt.all()`, consult `library_assets.data.dependencies` or `media_file_refs`, or use legacy torrent states as normalization blockers. They issue no torrent commands. Historical references are preserved for their owning subsystem. Intake polling failures are recorded as degraded health and cannot starve independent Library tasks.

The separate delete, quarantine, restore and download/import pipelines retain their dependency protection. This amendment supersedes only historical requirements to block Library normalization on torrent references; it does not globally remove shared storage guards. Unknown physical hardlinks, ambiguous work directories, source changes, unknown/edited sidecars, unsafe paths and collisions still require review. Exact plans, current asset revisions, approval hashes, write authorization, leases/fencing and journal recovery remain required. No automatic deletion, quarantine, edition replacement or quality-driven removal is introduced. BG-first preservation remains unchanged.

## Inspect, identify and review

The Library **Обследване** toolbar action requests all five categories regardless of browsing filters. Category-scoped inventory remains available through the API. Every discovered asset receives metadata inspection, including unchanged videos whose ffprobe data is cached. Inventory maintains paths, file size, fingerprint provenance, video/audio/subtitle streams and codecs, dimensions, audio/BG evidence, external subtitles, NFO IDs, season/episodes, associated sidecar/artwork paths and duplicate/version relationships. Missing/inaccessible category handling remains conservative; an unresolved identity does not stop peers.

Confirmed TMDb IDs are reused with the existing language-scoped `en-US` detail cache. Automatic title-based confirmation requires a single exact normalized title/type/year candidate and verified English details; a single vaguely similar result is insufficient. Unknown dates, ambiguous matches and missing English authority stay in review. Original-language titles and linked IMDb IDs remain separate. Provider availability and quotas are handled by existing adapter errors and one-day language-scoped caches. Live provider coverage is not claimed by synthetic tests.

Catalogue enrichment fills missing identity metadata and retains manual decisions. A conflicting confirmed manual title/year requires review rather than silent replacement. Manual category assignment survives subsequent full inspections even while the video remains physically under its old category root. Inspection never translates guessed titles or changes media paths, sidecars or artwork.

Library **За преглед** uses server filtering/pagination across unresolved and uninspected assets. Entries show current filename/path, parsed title/year/type, identification failure reason, current/proposed identity and suggested candidates. The identification dialog supports queued TMDb searches, a known-ID detail lookup, candidate selection, manual title/year/category/season/episode, collection override, supplementary classification and separate editions. Corrections are revision-checked, audited and persist in the asset identity. Supplementary material stays explicitly in review rather than being forced into a movie naming template.

Saving a correction queues reanalysis of that asset only. Explicit **Обследвай този файл** also refreshes its hash/probe without restarting the full scan. **Обнови предложението** creates a fresh, independently reviewable one-asset normalization plan. It does not edit an already approved plan or inherit old approval.

## Preview and execution

Normalization status exposes paginated proposals with `review_state` and optional `review_state` filter: `Ready`, `NeedsReview`, `Unidentified`, `Conflict`, `AlreadyNormalized`. Previews show current/proposed path, English name, changed identity fields, associated file manifests, sidecar proposals, preserved sidecars, version considerations, warnings and conflict codes. Existing per-file execution states are retained for queue/recovery compatibility.

Approval binds the exact plan revision/hash and checks source asset revisions. Worker checks the production write gate, mount, containment, source fingerprints and complete file manifests before physical effects. It revalidates the frozen naming target and journals individual link/unlink relocations and sidecar publications. Unknown physical aliases are reviewed; only an alias proven by the current interrupted operation journal is resumable. No torrent command is issued and no legacy torrent state is rewritten. Jellyfin recognition remains required for successful normalization completion.

## API and persistence

All endpoints retain administrator session, CSRF, origin, idempotency and audit handling:

- `GET /library/assets?review=true` applies existing category/title/stream/sort/page semantics to the review queue. `GET /library/review` supplies a minimal paginated queue, and `GET /library/assets/{id}` supplies the current detail.
- `POST /library/assets/{id}/identity-search` queues title/type/year search; `identity-lookup` queues provider ID/type details. `identity-candidates` exposes candidates; `GET /library/inspections/{task_id}` exposes task completion.
- `POST /library/assets/{id}/identity` adds optional category and supplementary/edition annotations while preserving unrelated identity data. It invalidates prior inspection readiness.
- `POST /library/assets/{id}/reanalyze` queues a durable `LIBRARY_INSPECT` task. It remains usable with physical writes disabled.
- Normalization status adds the preview filter without changing approval semantics.

Paths above use the existing `/api/v1` prefix. Existing JSONB asset evidence and task tables store the additive fields; no schema migration or production database access is needed for this PR. Existing plans remain immutable; incompatible/stale plans require re-analysis and new approval. Restoring the prior application does not reverse any separately approved future filesystem operation.

## Verification

Regression coverage: `tests/acceptance/test_library_first.py`, existing `test_library_v11.py` and `test_english_naming.py`, `frontend/tests/library-first.test.ts`, and `frontend/e2e/library-first.spec.ts`. The interactive [Library wireframe v1.2](../../wireframes/vimag-media-manager-library-v1.2.html) demonstrates review/search/correction/refresh and proposal filters without external operations, retaining the approved analytics and dark design.

Final commands/results and any external limitations are recorded in the PR. Tests use disposable PostgreSQL, synthetic NAS media and emulated or mocked providers only.
