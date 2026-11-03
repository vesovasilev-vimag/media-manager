# ViMag 1.1 — permanent production activation

**Target release**: `1.1.0` (stable). **Source of truth**: `main`. Do not deploy old `1.0.0-rc.1` images against PostgreSQL schema `0002`.

## Status and activation model

ViMag is a real production application, **not** a mock/demo. The production API uses the real adapters, PostgreSQL, NAS and qBittorrent/Jellyfin integrations. Permanent production operation uses two independent controls:

- Private Compose environment: `VIMAG_ENVIRONMENT=production`, `VIMAG_WRITE_ENABLED=true`, `VIMAG_AUTOMATIC_INTAKE=true`.
- Durable PostgreSQL `operational_authorization`, which confirms genuine backup, restore, mount, provider, seeding and recovery checks. This is configured **once**, retained across Worker restarts/upgrades, and recorded in the audit journal. Automatic intake does not authorize overriding a blocked torrent or unsafe library move.

`python -m app.ops status` reports production authorization status and missing checks without exposing secrets. API/UI show actual operational availability, not a fake demo/RC label.

## Prerequisites: do not self-attest without verifying

1. Publish stable digest-pinned `1.1.0` web/backend images from `main`, with CI + security passing. Keep historical RC1 tag immutable.
2. Confirm actual host Docker Compose deployment location, services, network, NAS CIFS mount source, qBt path mapping, Jellyfin path and version, UID/ACL, secret file mounts, installed binaries and startup health.
3. Stop/quiesce Worker without deleting job journals. Export current qBt torrent mappings and check ~92 protected legacy torrents and their path/seed state. Preserve their payloads.
4. Create a PostgreSQL custom-format backup, verify checksum, store a second off-host copy, rehearse empty-DB restore, then rehearse schema `0001`→`0002` migration and validate historical quarantine manifests. Ensure sufficient NAS backup/recovery for destructive operations: database backup alone cannot restore media.
5. Check production secrets (qBt, TMDb, OpenSubtitles, Jellyfin); rotate any exposed Jellyfin token. Verify real mounts and space, hardlink conditions, ACLs and that no pending destructive journal is unresolved.
6. Validate all documented operational gates `G-01` through `G-06`, `G-DB-01` and evidence fields. A failed or unknown gate stays **blocked**.

## Stage production once, then leave it active

First deploy and migrate with both flags `false` **only for the maintenance window**; this is not a permanent mode. After the checks above, prepare a **private**, operator-signed JSON file on the ViMag host (never in Git):

```json
{
  "mode": "production",
  "authorized_by": "your-operator-identifier",
  "backup_verified": true,
  "database_restore_verified": true,
  "mounts_verified": true,
  "jellyfin_token_rotated": true,
  "legacy_baseline_verified": true,
  "recovery_fixtures_verified": true,
  "G-01": true,
  "G-02": true,
  "G-03": true,
  "G-04": true,
  "G-05": true,
  "G-DB-01": true,
  "G-06": true,
  "confirm": "I_VERIFIED_PRODUCTION_PREREQUISITES"
}
```

Set the host file mode to `0600`; provide a secure read-only bind to the trusted Worker for the single registration command. Do **not** grant a network API endpoint for this privileged operation. Run `python -m app.ops authorize-production /path/inside/worker/authorization.json` in the running Worker image with production DB access. It validates the actual schema and all required signed-off flags; it never automatically creates a successful evidence record. Inspect `python -m app.ops status`.

Then update **private host** `.env` to:

```dotenv
VIMAG_WRITE_ENABLED=true
VIMAG_AUTOMATIC_INTAKE=true
```

Reconcile `docker compose config`, restart API/Worker under the correct digest-pinned release, verify status and health, and check existing torrent path mappings unchanged. No permanent read-only mode. Incomplete safety evidence remains a legitimate block, not a demo state.

## Operating rules

- User confirmation is still required for irreversible DELETE-01; never auto-delete or auto-quarantine from normalization.
- Protected torrents, unknown dependencies, changed file fingerprints, hardlink/mount problems and filesystem conflicts **still block individual jobs**. Workers continue eligible independent files.
- `read_only: true` in Compose hardens the container root filesystem. It does **not** block valid writes to the separately mounted NAS when worker authorization permits them.
- Do not use a migration rollback by booting RC1 against schema `0002`. Follow `docs/v1.1/operations-and-recovery.md`.
- This document does not claim that production has been activated. Actual host access, backup evidence, release artifacts and operator verification are required.
