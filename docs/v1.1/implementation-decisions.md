# v1.1 technical decisions

The owner-approved product decisions remain in [decisions.md](decisions.md). These choices implement that policy without authorizing production operations.

| ID | Choice | Reason |
|---|---|---|
| ENG-01 | Additive schema 0002; frozen RC1 metadata for migration 0001 | Upgrade tests must begin from the actual RC1 shape. Downgrade remains restricted to explicitly disposable databases; production rollback uses verified backups and reconciliation. |
| ENG-02 | Materialized searchable probe columns and PostgreSQL array indexes | Filters and counts operate across the whole catalogue. Unknown inspection stays distinct from a proven empty stream list. Byte size uses bounded integer parsing. |
| ENG-03 | Statement-triggered catalogue generation invalidates API aggregation caches | Worker and API processes observe the same durable invalidation; pagination never affects analytics. |
| ENG-04 | Scan outcome audit records commit with asset updates | Restart can reconstruct counts without probing unchanged files again. Missing classification requires complete enumeration and a final mount recheck. |
| ENG-05 | Reuse RC1 job/tasks/plans/approvals/journal with per-file maintenance records | One approval snapshots policy and exact manifests. Ambiguous files do not stop eligible siblings. Global NAS serialization preserves the original one-heavy-operation limit, with asset/destination leases and per-file checkpoints. |
| ENG-06 | Exact confirmed delete keeps inactive asset evidence plus tombstone | Active catalogue entries disappear only after all manifest removals are verified. Foreign keys and audit history remain intact. No torrent-delete command is introduced. |
| ENG-07 | Immutable subtitle generations under `.vimag-subtitle-history/<asset>/<generation>/`, outside Library | Each generation exposes historical `ver-02`, `ver-03` names in its manifest. A single atomic primary replacement avoids an unsafe in-place rename chain and prevents historical tracks competing in Jellyfin. Restore creates another generation, preserving the previous primary. |
| ENG-08 | Existing/manual sidecars require exact association or durable ownership | Exact video-stem subtitles/NFO and verified exclusive manifests can accompany an item. Shared collection/show art and unknown directory sidecars remain protected and are shown in the preview. |
| ENG-09 | Preserve provenance `BG_TAGGED`; accept it for v1.1 naming/preservation | This applies BG-01 without pretending a stream tag is human verification. Missing or contradictory evidence remains uncertain. |
| ENG-10 | Real Jellyfin compatibility fixture uses pinned 10.10.7 on an internal Docker network | Verifies actual collection-directory traversal, editions and subtitle parser behavior with original generated media. It is evidence for that version, not a claim about the production installation. |
