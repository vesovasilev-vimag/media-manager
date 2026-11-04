# v1.1 operations and recovery

This describes the implementation for a **separate deployment decision**. No v1.1 image has been published and no production NAS, torrent or setting was changed. Keep `VIMAG_WRITE_ENABLED=false` and `VIMAG_AUTOMATIC_INTAKE=false` until separately authorized. RC1 tags and image digests remain immutable.

## Catalogue and inventory

`GET /api/v1/library/assets` filters, sorts, counts and paginates in PostgreSQL for both views. Unknown probe information is distinct from proven absence. Size is a bounded integer from `probe.format.size`; volume is measured logical file bytes, not a capacity/allocation/dedup estimate. A statement-triggered generation invalidates aggregation caches across Worker/API processes.

`POST /library/scans` accepts category/all scopes; the old `/library/scan` remains compatible. Poll `/library/scans/{id}` for counts/errors. Scans write inventory/audit only. Unchanged path/size/mtime reuses a probe; changed/new files are inspected. Full fingerprints identify a unique rename; ambiguity stays reviewable. Incomplete traversal or failed mount checks prevent missing classification. Complete scans mark missing files `MISSING`, never delete them, and restore availability on reappearance. Outcome audit commits with asset updates for restart reconciliation. Availability is distinct from quarantine/deletion workflow state.

## Policies and identity

`GET/POST /library/policies` stores immutable revisions with optimistic `expected_revision`; `/library/policies/preview` uses the execution evaluator. Saving/previewing never enqueues filesystem work. The five qBt category identifiers remain stable. Scans cover historical/current roots needed by the catalogue.

Movie collections are optional levels enabled by default; absence omits the folder. Library identity correction records manual metadata and collection overrides without moving files. Known IDs are reused and enriched with IMDb/collection provenance, cached for one day. Filename IDs/episode mappings provide evidence, while title/year-only candidates remain reviewable. Provider 429 responses impose cooldown. Missing credentials produce unavailable/review states.

## Normalization

Create `/library/normalizations/plans` with exactly one of `asset_ids`, `category`, or `all:true`. Worker analysis snapshots policy, identity, hashes, exact destinations, sidecar proposals, selected subtitle and physical ownership evidence. Poll `/library/normalizations/{job_id}`; file results are paginated. One approval supplies `plan_revision`, `plan_sha256`, `confirmed:true`. Stale revisions, changed bytes, unknown links, escaping paths and collisions remain blocked. Maintenance never modifies a legacy torrent.

Phases are identity/metadata, hierarchy/naming and owned sidecars, subtitles, Jellyfin refresh/recognition. Correct files can be `NoChange`. Subtitle unavailability can warn; failed NAS integrity or Jellyfin recognition cannot produce successful normalization. Individual failures do not halt eligible siblings. No normalization step creates quarantine/delete intent.

`/pause`, `/resume`, `/cancel`, `/retry` control the job. Pause acts at a file checkpoint. Cancel leaves completed operations intact and cancels remaining files. Retry reconciles the same approved journal; failed analysis can retry without acquiring write permission. Ambiguous identity or external changes need correction/new planning rather than an unsafe override.

## Quarantine/restore

`/library/quarantines/plans` has its own exact scope and approval. Each item records original/destination paths and fingerprints. Proven exclusive sidecars accompany the video; shared/uncertain metadata is preserved and shown in preview. `.vimag-quarantine` is outside Jellyfin Library, with no expiry/purge.

Restore one manifest through `/library/quarantine/{id}/restore`, or selected v1.1 manifests through `/library/quarantines/restores` with `manifest_ids` and `confirmed:true`. Original paths remain fixed; targets are never overwritten. Per-file collision/failure preserves independent successes. `/library/quarantine/restores/{job_id}/retry` reconciles the same approved restore journal after resolving the problem. RC1 manifests retain individual compatible restore. `/jobs/{job_id}` includes restore file records and recovery evidence.

## Explicit deletion

Only `/library/deletions/plans` and its separate confirmed approval authorize DELETE-01. Preview lists exact video and proven-exclusive subtitle versions/NFO/artwork. Shared collection/show/edition metadata and unknown associations remain protected. Worker removes individual manifest entries, never recursively removes folders, deletes a torrent, or purges quarantine.

Only verified removal of every entry removes the asset from the active catalogue. Tombstone/audit persist. Partial failures remain active and reconcile on retry; changed/reappearing files block reconciliation. Jellyfin refresh follows filesystem success. There is no ViMag trash/undo: DB backups cannot recreate NAS bytes. Independent NAS backup/restore and operational authorization remain prerequisites.

## Subtitle improvement/history

Embedded/external tracks are inventoried. OpenSubtitles is a candidate provider, not sync proof. Evidence includes fingerprint/ID, edition/release, FPS, duration, encoding, completeness, language and type. Declared Windows-1251 can convert to UTF-8; unknown/bad encodings stay reviewable. Equal FPS/timestamps alone never establish synchronization. `/library/assets/{id}/subtitles/accept` records an explicitly verified candidate; normalization snapshots and applies it. Unknown/manual primaries are never overwritten.

Normal primary: `<video-stem>.bg.srt`; forced/SDH retain proper flag suffixes. Immutable generations under `.vimag-subtitle-history/<asset>/<generation>/` stay outside scanned roots. Their manifests map `ver-02`, `ver-03`, etc. Archive verification precedes one atomic primary publication; retries do not rotate again. `/library/assets/{id}/subtitles/versions/{generation}/restore` creates a new generation preserving the prior primary. There is no retention purge.

Real isolated Jellyfin 10.10.7 checks collection traversal, edition grouping, primary discovery and archive exclusion (`tests/fixtures/jellyfin_contract.py`). See [Jellyfin naming/subtitle/version conventions](https://jellyfin.org/docs/general/server/media/movies/) and [NFO conventions](https://jellyfin.org/docs/general/server/metadata/nfo/). The production version, paths, NFO saver and CIFS semantics require their own preflight.

## Migration/recovery and deployment prerequisites

Schema 0002 is additive; 0001 uses frozen RC1 metadata. Existing RC1 quarantine manifests backfill the new asset workflow state without filesystem access; restored manifests retain active assets and restore history is preserved. Before a separately authorized rollout: quiesce Worker, capture pending journals, make/check a custom-format PostgreSQL backup, rehearse an empty-database restore, and test 0001→0002 on the restored disposable copy. Automated fixtures exercise backfill, restricted down/up, backup/restore and pending-operation preservation. Runtime DB remains unprivileged, API has no media mounts, Worker retains one NAS bind.

An RC1/schema-0001 image is not a rollback target for schema 0002. Keep writes off during recovery. Reconcile NAS/qBt/journals first: DB restore does not undo filesystem operations. Never blindly replay an unobserved move, overwrite collisions, recreate deleted files from inventory or remove legacy torrents. Expired leases reclaim fencing epochs and durable operation keys. Production maintenance additionally requires G-06 inventory proof.

Deployment prerequisites: distinct v1.1 tag/digests, passing CI/security, rotated Jellyfin token, real provider/qBt/Jellyfin checks, mount/UID/ACL and same-share links, backup restore, correct library roots/history exclusion, and existing operational gates. Publication, deployment and write/intake activation are separately authorized work.

## Library-first inspection amendment (2026-11-04)

See [Library-first normalization](library-first-normalization.md). Library normalization no longer queries qBittorrent or gates on historical references, including `missingFiles`. Existing torrent records remain untouched. Delete/quarantine retain their existing dependency guards. Metadata inspection includes cached/unchanged videos; per-file reanalysis and manual TMDb lookup/search update catalogue evidence without moving files.
