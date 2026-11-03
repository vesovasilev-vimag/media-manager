# ViMag — Separate inventory and torrent lifecycle

## Approved separation

**Inventory is NAS-only.** It enumerates and updates media catalogue data and subtitle/NFO evidence without querying qBittorrent or attempting to determine live seeding dependencies. A temporary qBittorrent outage must never block a library scan. Inventory must not erase previously recorded torrent dependency metadata; it is owned by a different subsystem.

**Torrent lifecycle is event-driven.** Future completed downloads trigger a notification from qBittorrent to a secured ViMag intake endpoint. qBittorrent 5.x supports a configured **Run external program on torrent completion** command; a minimal bridge/command can POST a signed notification, with a torrent info hash and category. It is not a permanently open webhook connection, and no native qBittorrent HTTP webhook subscription is assumed.

The intake pipeline must:
1. Authenticate requests from the internal qBt environment; reject replays and non-whitelisted categories.
2. Persist an idempotent torrent event + info hash with durable queue/retry and crash recovery.
3. Fetch only that torrent's current data from qBittorrent API, inspect individual files, identify media, compare versions and plan layout.
4. Persist file-to-torrent mapping as first-class database ownership (not inferred by library scans).
5. Before moving/renaming a tracked torrent file, fence its job, use qBittorrent relocation/rename API as appropriate, and re-read its save path/file list to prove sync; if either side fails, reconcile without deleting any payload.
6. On remove/finish/error/changed path, reconcile that registered torrent's mapping, not rescan unrelated media. Periodic bounded reconciliation may repair lost webhook events; it must not be library inventory.

**Existing torrents:** user plans a separate one-time removal of old torrent records (not payload files) before mass normalization. No code/operation should silently remove them. Until a confirmed safe removal, destructive or relocating operations must preserve existing protections against unknown seeding dependencies. Never use 'delete files' in qBt removal. Clearing old torrent records is NOT part of this PR.

**Normalization and inventory:** scan discovers path, size, metadata, audio/subtitle tracks; then an explicit plan for media naming/organization; writes require production authorization and per-action approvals. Historical fingerprints cached from RC1 should be marked unverified when reused from matching file size, and freshly computed/checked before any file mutation.

## Scope of current PR #9

Implement NAS-only inventory with bounded PostgreSQL work, no qBittorrent API, improved incremental reuse and regression coverage. The secure event intake, durable file mapping, qBt relocation/reconciliation and legacy-torrent cleanup are separate deliverables, not falsely claimed as implemented here.
