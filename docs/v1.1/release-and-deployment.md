# v1.1 release and read-only deployment handoff

**Status:** release preparation only. Publishing requires explicit manual GitHub Actions dispatch. Never reuse the v1.0 RC workflow or tag.

## Stable v1.1 release identity

The release is **ViMag Media Manager 1.1** (semantic version `1.1.0`). It is not an RC or prerelease. All new artifact labels, images and deployment manifest use `1.1.0`. The historical `v1.0.0-rc.1` remains immutable.

## GitHub publication

- Source: `codex/rc1` after PR #5, `bf350818408bf058885ff1ed4c51fd8076bf0610` at the time this document was authored.
- Workflow: `.github/workflows/publish-v11.yml` — **manual workflow_dispatch only**, on `codex/rc1`; reruns CI and security before creating immutable `v1.1.0` tag and two multiarchitecture Docker Hub images.
- Output: `v11-deployment.tar.gz` containing digest-locked `release-manifest.json`, original production Compose template and operator scripts. `deploy/scripts/validate-v11-release.py` validates exact v1.1 schema `0002` and image digests.
- No automatic host deployment or write flag activation. PR merge by itself must not auto-publish v1.1.
- Guard: existing tags and Docker image tags cannot be overwritten. Partially completed publication needs manual evidence reconciliation, not blind rerun. The original RC1 build workflow may run on source changes in `codex/rc1` and fail its immutable RC1 tag guard; **do not remove that guard or force RC1 republish**.

## Required production preflight, after images publish

1. Verify production access to ViMag host privately; check exact current Compose directory, image digests, service names, PostgreSQL schema, versions and volume paths. Do not assume local paths from dev docs.
2. Keep `VIMAG_WRITE_ENABLED=false` and `VIMAG_AUTOMATIC_INTAKE=false` in Compose; verify runtime env after restart.
3. Rotate the Jellyfin credential previously exposed in conversation; keep secrets entirely outside Git.
4. Quiesce Worker, check all uncompleted operation journals and preserve them.
5. Create consistent PostgreSQL custom-format backup, SHA-256 and a second independent copy; perform empty-DB restore and staged migration `0001`→`0002` from that backup; verify quarantined RC1 manifest state backfill and rollback/recovery strategy.
6. Run read-only host mount/permissions/qBt legacy baseline/Jellyfin version checks. Check NAS CIFS mount isn't a fallback local directory. No writes to legacy torrent payloads.
7. Only then download verified deployment artifact, validate manifest, set production image references using exact digests, `docker compose config` and pull exact images.
8. Upgrade database **once**, serially, while Worker stopped, then start read-only API, web and Worker according to documented `docs/deployment-and-backup.md` procedure.
9. Check Docker health, `/api/v1/health/ready`, library pagination and actual media counts, scan read-only and Jellyfin/qBt connectivity without file mutations. Confirm real media paths stay unchanged.
10. In case of failure, **do not** start RC1/schema-0001 backend against schema 0002. Preserve backups, stop Worker and consult `docs/v1.1/operations-and-recovery.md`. Database restore alone cannot undo NAS mutations.

## Release authorization boundaries

A successful CI, published Docker image or completed DB backup does **not** authorize destructive operations, global write activation, full normalization, quarantine or deletion. A later isolated pilot requires independent explicit authorization, validated NAS backups and torrent guards. The first deployment stage is strictly read-only at filesystem level.

## Remaining external requirements

Real ViMag host SSH access and secret/backup access are required for host-side execution. GitHub is not an SSH deployment channel. Do not claim live deployment from a GitHub PR or completed publication job.
