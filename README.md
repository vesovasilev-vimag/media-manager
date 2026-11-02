# ViMag Media Manager

> **v1.1 Library Maintenance:** [PR #4](https://github.com/vesovasilev-vimag/media-manager/pull/4) targets `codex/rc1`; the [implementation report](docs/v1.1/implementation-report.md) records passing CI/security and test evidence. Approved [requirements](docs/v1.1/README.md), [traceability](docs/v1.1/traceability.md), [technical decisions](docs/v1.1/implementation-decisions.md) and [operations/recovery](docs/v1.1/operations-and-recovery.md) are versioned separately. Production writes, intake, release publication and deployment remain separately authorized.


Self-hosted media imports for qBittorrent and Jellyfin: Vue 3, FastAPI, a separate Python/ffprobe Worker and PostgreSQL. Four runtime containers and two custom images, with Bulgarian-first, edition-aware organization, guarded torrent moves, hardlinks, sidecars, subtitles and reversible quarantine.

**RC1 implementation is on `codex/rc1`. See the [release report](docs/rc1-release-report.md) for actual publication, deployment and gate status. Local builds and synthetic tests are separate from production verification.**

The seven screens use persisted APIs: dashboard, job details, library, duplicate comparison, move queue, subtitles and settings. Imports succeed only after NAS integrity, qBt mapping/pieces/seeding capability, Jellyfin recognition and all critical children are verified.

## Development and automated validation

Development uses emulated providers, generated secret files and synthetic Docker volumes, with no production mounts or credentials.

```sh
sh deploy/scripts/init-dev.sh
docker compose -f deploy/compose.dev.yaml build
docker compose -f deploy/compose.dev.yaml up -d --wait db
docker compose -f deploy/compose.dev.yaml run --rm api python -m alembic upgrade head
docker compose -f deploy/compose.dev.yaml up -d --wait
```

Open `http://localhost:8088`. Enrollment uses the private generated `deploy/secrets/setup_token` and a new admin password. There is no default account. Windows also has a PowerShell initializer. Secret values stay outside Git and chat.

```sh
mkdir -p .test-artifacts
docker build -f tests/Dockerfile -t vimag-tests .
docker run --rm --network vimag-dev_default -v "$PWD/deploy/secrets:/workspace/deploy/secrets:ro" -v "$PWD/.test-artifacts:/results" vimag-tests
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
npx playwright install chromium
npx playwright test
```

Linux tests exercise real PostgreSQL migrations, concurrency, backup/restore, generated ffprobe media, hardlinks, replay/failure injection, security and mocked external contracts. [Traceability](docs/rc1-traceability.md) records the 43 T and 17 IT scenarios. CI/security repeat the checks before release.

## Safety and delivery

First deployment is `WRITE_ENABLED=false`, automatic intake disabled. Snapshot the actual existing torrent set as legacy read-only; 92 is the historical observation, not a fixed count. No automatic adoption after remove/re-add. Only eligible new owned torrents use Manual TMM and `/downloads/complete`. Preserve the five categories and existing mounts; file presence is not download completion.

qBt owns active payload moves/renames. An accepted request is not verification. Preserve paused/queued/ratio policy; zero upload is not failure. Worker alone receives the single NAS bind. No transcoding/remux or media-byte editing. BG naming requires stream-bound evidence.

There is no permanent library/quarantine delete. Quarantine requires exact approval and fresh dependency proof. Unknown sidecars cannot auto-overwrite. Cleanup is limited to proven disposable staging files.

GitHub Actions publishes `vesovasilev/media-manager-web:1.0.0-rc.1` and `vesovasilev/media-manager-backend:1.0.0-rc.1` only after CI/security pass, recording actual digests, SBOM and provenance. ViMag pulls immutable artifacts, with no source build, unattended update or new public DB/API/qBt ports. Deployment and exactly one new harmless torrent test require actual access, private secrets, backups and a rotated Jellyfin token. General activation is a separate gated cutover.

Read [deployment/backup](docs/deployment-and-backup.md), [recovery](docs/operations-and-recovery.md), [qBt integration](docs/qbt-integration-runbook.md), [mounts](docs/storage-mount-matrix.md), [OpenAPI](docs/api-contract-v1.yaml) and [security review](docs/security-review.md).

Approved sources: [scope](docs/technical-scope-v1.0.md), [design](docs/implementation-design-v1.0.md), [wireframe](wireframes/vimag-media-manager-v1.0.html) and [kickoff](docs/rc1-kickoff.md). The wireframe is a design reference, not the running application.
