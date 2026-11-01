# Operations and recovery

## Runtime control

`WRITE_ENABLED=false` and automatic intake false are the deployment defaults. Login/DB/inventory remain separate from write readiness. API uses one Argon2id admin, hashed persistent sessions (8h), Secure/HttpOnly/SameSite cookies, CSRF+Origin checks, idempotency keys and an append-only application audit. Setup requires a private one-time secret and a unique password of 14–256 characters. Setup cannot replace an enrolled admin. Password rotation invalidates all sessions.

API endpoints return reason codes and protected evidence, never service credentials. qBt, Jellyfin, TMDb and subtitle credentials are Worker-only files. Unexpected exception text is not emitted by Worker because remote/SQL errors can expose private media details. Docker logs are bounded. Operational audit is in PostgreSQL, not on NAS.

## Recovery rules

| Condition | Response |
|---|---|
| NAS offline, mount identity or capacity unsafe | Block external dependency; preserve staging, operation journal and partial destination |
| qBt move accepted or command timed out | Observe current mapping/state; never repeat uncertain move/rename blindly |
| Worker crash after destination exists | Reconcile hashes, mapping and journal, then continue verification |
| Lease expires / DB fails | Old worker loses permission for new effects; next worker reconciles first |
| qBt incomplete pieces or integrity mismatch | `RecoveryRequired`; no cleanup or terminal success |
| Category/file/policy/instance drift | `ReplanRequired`; exact approval becomes stale |
| Unknown/edited NFO or artwork | Preserve bytes; show old/new preview and exact revision approval; backup before replacement |
| Subtitle mismatch/provider outage | Preserve originals; review/sync proposal or explicit `Unavailable` warning |
| Jellyfin refresh accepted but item absent/wrong | `PublishPending`; no second NAS move and no successful completion |
| Quarantine dependency or restore collision | Block; approval cannot override shared bytes or overwrite another asset |

Queue claims use `FOR UPDATE SKIP LOCKED`. Tasks and resource leases are short transactions with monotonic epochs and heartbeat renewal; no SQL transaction spans network/media I/O. Intent is durable before command dispatch. Requested, observed and verified states are separate. Idempotent API requests return the same command result; restart reconciles external reality. Initial NAS move concurrency is one. Conservative limits are configuration, not measured production SLAs.

## Quarantine, sidecars and cleanup

Quarantine requires an exact plan approval and a fresh live torrent dependency scan. The same-share operation preserves bytes, records source/target/hash and remains reversible. Restore refuses collisions. There is no permanent library delete endpoint, Worker command or retention purge.

NFO/artwork auto-update requires an unchanged owned content hash and an unlocked manifest. Unknown/external changes require explicit revision approval and a retained backup. Any subsequent external edit invalidates that approval. Use the job's technical tab to inspect the diff and revision. Verify/Revoke BG audio records actor, time, exact file hash and stream digest. Changing proof after transfer creates a rename proposal; it does not silently rename active payloads.

Automatic staging cleanup is a separate primitive: exact independently owned orphan file, verified NAS bytes, mapping, completed pieces, seeding capability and complete zero-dependency scan. No recursive deletion; no CIFS inode-only inference; never delete a library/quarantine file. qBt normally already moved its source, so no second source removal is performed opportunistically.

## Incident procedure

Stop new write scheduling first. Preserve PostgreSQL, operation evidence, qBt state and all media. Inspect authenticated job/operation/audit views. Restore network/mount availability without recreating NAS directories on local fallback storage. Retry triggers reconciliation; it is not permission to repeat an unknown external command. Data mismatch requires a reviewed compensation plan. Never restore old DB state while Worker is issuing effects.

## Image and schema rollback

Stop Worker before changing images. Compare the DB schema with the previous immutable manifest using `python -m app.ops check-schema <manifest>`. `0001` is the RC1 schema. An incompatible revision blocks rollback; an image rollback is not a filesystem rollback. Use an independently restored empty database to rehearse recovery, and reconcile current NAS/qBt reality before resuming. Production downgrade/drop/recreate is disabled. Alembic destructive downgrade requires the explicit disposable-test option.
