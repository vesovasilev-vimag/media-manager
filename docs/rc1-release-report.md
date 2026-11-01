# ViMag Media Manager RC1 — release evidence report

**State:** NOT BUILT — template only. **Do not change to PASS without executed evidence.**

## Version identity

- RC tag: `v1.0.0-rc.1` (target; not created)
- Source commit SHA: `PENDING`
- CI URL / run ID: `PENDING`
- Security scan/SBOM/build provenance: `PENDING`
- Docker Hub web image digest: `PENDING — NOT PUBLISHED`
- Docker Hub backend image digest: `PENDING — NOT PUBLISHED`
- Digest-pinned release manifest: `PENDING`

## Feature completeness

- Seven production UI screens bound to real API: **NOT VERIFIED**
- PostgreSQL queue + migrations + crash recovery: **NOT VERIFIED**
- qBittorrent/Jellyfin/NAS + media policies: **NOT VERIFIED**
- Quarantine/restore + no permanent library deletion: **NOT VERIFIED**
- Backup/restore, security and operator runbooks: **NOT VERIFIED**

## Automated evidence

Use [RC1 traceability](rc1-traceability.md); do not copy optimistic statuses.

| Suite | Result | Command/CI URL | Evidence |
|---|---|---|---|
| T-01..T-43 | NOT_RUN | — | — |
| IT-01..IT-17 | NOT_RUN | — | — |
| Backend/API/DB | NOT_RUN | — | — |
| Frontend | NOT_RUN | — | — |
| Security/containers | NOT_RUN | — | — |
| Synthetic failure/recovery | NOT_RUN | — | — |

## Deployment and one-torrent pilot

| Step | Result | Exact evidence |
|---|---|---|
| Docker Hub image publication | NOT_RUN | — |
| ViMag backup and preflight | NOT_RUN | — |
| Compose pull & start (read-only) | NOT_RUN | — |
| qBt legacy baseline before/after | NOT_RUN | — |
| NAS Worker mount/permissions | NOT_RUN | — |
| Real Jellyfin/QBt integration | NOT_RUN | — |
| One newly created harmless test torrent | NOT_RUN | — |
| Completion, move, seeding/recheck, Jellyfin recognition | NOT_RUN | — |
| Final `WRITE_ENABLED` state | NOT_KNOWN | — |

## Open gates / blocking dependencies

- G-01: read-only API proven; write fixture not yet validated.
- G-02: hardlinks in host and Docker scratch pass; production Worker UID/mount validation outstanding.
- G-03, G-04, G-05, G-06, G-DB-01: no final production sign-off yet.
- Potential external access: Docker Hub push token, SSH/deploy access, fresh Jellyfin token, provider credentials.

## Final decision

**NOT RC1 PASS** until the code, images, required automated evidence and authorized integration/pilot evidence exist. Codex should replace this template with real run records at delivery. Release and production-wide write activation are separate authorizations.
