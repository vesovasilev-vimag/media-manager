# Deployment and backup

The deliverable is two immutable custom images and four runtime services: Vue/Nginx, FastAPI, Worker (shared backend image), PostgreSQL. ViMag pulls published artifacts. No source checkout, build, Docker socket or unattended updater is used in production.

## Developer validation

Initialize local secrets with `sh deploy/scripts/init-dev.sh` (or the PowerShell equivalent). Values are random, private and ignored. Start the disposable DB with `docker compose -f deploy/compose.dev.yaml up -d --wait db`. Build `tests/Dockerfile`, then run on network `vimag-dev_default`, mounting only generated dev secrets and an evidence output directory. The Linux suite creates only fixed `vimag_rc1_*test` databases and synthetic media. It tests real migrations, PostgreSQL concurrency, restore, ffprobe, hardlinks, API/security and mocked qBt/Jellyfin contracts. No live provider is contacted by tests.

For the dev UI, build the four dev services, run `docker compose -f deploy/compose.dev.yaml run --rm api python -m alembic upgrade head`, then `up -d`. Open loopback `http://localhost:8088`. Enrollment reads the generated private setup token file locally; there is no default admin/password. Dev uses emulators and synthetic volumes; production settings reject these adapters.

CI runs backend/frontend checks and both image builds. The security workflow audits hash-locked Python/npm dependencies, Bandit and Gitleaks, and scans both runtime images. The release workflow repeats CI/security on `codex/rc1`, checks registry credentials, creates the exact immutable RC tag and checks out that verified commit before pushing. A tag-triggered run follows the same gates. Required repository secrets are `DOCKERHUB_USERNAME=vesovasilev` and a scoped `DOCKERHUB_TOKEN`; values must never be sent in chat or logs.

`build-release.yml` produces SBOM/provenance through Buildx, actual registry digests and `rc1-deployment.tar.gz`. The manifest records source commit, compatible schema and both supported Linux architectures. A pending manifest is deliberately undeployable. Existing RC image tags are not overwritten blindly.

## Host preconditions

Use a private deployment directory such as `/home/veso/docker/media-manager`, containing only the deployment artifacts, private `.env`, secret files, config/evidence, backups and local Linux PGDATA. All secret directories/files need restrictive permissions and ownership readable by the intended container UID. API receives only DB/setup secrets; provider keys stay Worker-only. Rotate/revoke the previously exposed Jellyfin token before any pilot.

Validate architecture against the manifest; confirm `vimag_default`, the existing private access middleware, TLS host, and no public DB/API/qBt port exposure. `preflight.sh` is read-only and rejects PostgreSQL on non-ext4/XFS storage and NAS fallback mounts. Do not alter qBt/Jellyfin mount configurations during development. Final Worker UID/ACL, same-share hardlinks and qBt torrent-store mount remain live gates.

Private `.env` image references must exactly match the validated release manifest; never use mutable tags or placeholders. Supply the verified Jellyfin-side mount root, not an assumed universal container path. Production Compose pins `WRITE_ENABLED=false` and automatic intake false. A feature-specific scoped fixture process is separate from general production activation.

## Backup and restore

The backend image includes PostgreSQL 17 `pg_dump`/`pg_restore`. `python -m app.ops backup /backups/predeploy.backup` makes a consistent custom-format backup, checksum, schema/version manifest and private file mode. Backups go outside PGDATA and need a separate off-disk copy. Database audit, ownership, approvals, journal and schema history are all included.

`restore.sh` only accepts an explicitly named empty `vimag_restore_*` database. Restore checks checksum, schema compatibility and emptiness, then performs one transaction. It never cleans/replaces a live DB. The automated suite restores jobs/audit/operation intents and schema into an empty disposable database and verifies them. Scheduled backup cadence starts daily, with an independent weekly copy; retention does not authorize library/quarantine deletion.

Before upgrade, stop Worker, back up the current database, capture compatibility and current qBt config/fastresume safely. For the first installation, migrate a verified empty DB, capture its initial backup before any write-capable integration, then start API/Worker read-only. Keep before/after preflight evidence privately. An empty initial backup is not a substitute for qBt/media backups before a fixture.

## Postpublication deployment

Validate the actual manifest and host preconditions, then pull exact digests, start DB, apply one serialized Alembic migration and start the four services. Inspect health and authenticated read-only integrations. Follow the [qBt runbook](qbt-integration-runbook.md) for exactly one new synthetic torrent after all operational prerequisites are present. Full activation and global default TMM cutover remain separate authorizations. No legacy torrent is part of the fixture.

See [recovery](operations-and-recovery.md), [mount matrix](storage-mount-matrix.md), [traceability](rc1-traceability.md) and the truthful [release report](rc1-release-report.md). Published images, deployment and live gates cannot be inferred from local builds.
