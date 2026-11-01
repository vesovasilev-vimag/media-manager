# ViMag Media Manager

**Reliable post-download media organization for qBittorrent and Jellyfin.**

> **Project status:** Technical Scope v1.0 and Implementation Design v1.0 approved and published (2026-11-01). No production application, container image, or deployment exists yet. The interactive HTML wireframe is a simulation only.

ViMag Media Manager is a planned self-hosted web application for safely importing completed qBittorrent downloads into a NAS-based Jellyfin media library. It will identify media, compare library versions, prioritize verified Bulgarian audio, apply consistent filenames and directory structures, find Bulgarian subtitles, publish to Jellyfin, and verify that torrents still seed correctly after relocation.

## Project principles

- **qBittorrent category is the chosen top-level library destination.** Users select `movies`, `series`, `animations`, `documentaries`, or `concerts` while downloading. ViMag manages identification, naming and subdirectories *within* that category; it must not silently override it.
- **Bulgarian-first with quality safeguards.** Preserve verified BG-audio editions. Materially better non-BG video may coexist as a separate version when justified.
- **No unexpected data loss.** No permanent deletion of library versions in v1. Only verified, unnecessary temporary download/staging copies may be cleaned automatically after all dependency and integrity checks.
- **Torrent-aware operations.** qBittorrent owns torrent file mappings and seeding. ViMag must not independently rename/move active torrent files in ways that break those mappings.
- **Observable, resumable jobs.** Every operation is auditable, idempotent where possible, and recoverable after an interrupted NAS/API connection.
- **Human review for ambiguity.** Uncertain matches, duplicate decisions, category mismatches, subtitle mismatches and potentially destructive actions require review.

## Workflow

```text
qBittorrent: completed download
      |
      v
01  Intake / torrent identification
02  Identify and inspect (TMDb + ffprobe / MediaInfo)
03  Compare with library (BG-first + quality + editions)
04  Organize and enrich (safe NAS relocation + NFO/artwork)
05  Find and validate Bulgarian subtitles
06  Publish and verify in Jellyfin
07  Verify final torrent location, integrity and seeding
      |
      v
Completed only after required checks pass
```

**Important:** Seeding recovery must happen as early as safely possible during step 04. Step 07 is the final confirmation, not the first attempt to resume seeding.

## Storage and category routing

| qBittorrent category | NAS library root |
| --- | --- |
| `movies` | `/mnt/nas/Movies/Library/Movies` |
| `series` | `/mnt/nas/Movies/Library/Series` |
| `animations` | `/mnt/nas/Movies/Library/Animations` |
| `documentaries` | `/mnt/nas/Movies/Library/Documentaries` |
| `concerts` | `/mnt/nas/Movies/Library/Concerts` |

Download staging: `/mnt/storage/qbt`. The download disk and NAS are separate physical storage resources. Preserving qBittorrent seeding during and after relocation is the principal engineering risk.

Approved illustrative movie naming convention:

```text
Movies/
  The Matrix (1999) [tmdbid-603]/
    The Matrix (1999) [tmdbid-603] - 2160p HDR.mkv
    The Matrix (1999) [tmdbid-603] - 2160p HDR.bg.srt
    movie.nfo
    poster.jpg
    backdrop.jpg
```

The movie file prefix intentionally matches the folder name for Jellyfin multiple-version detection. TV episodes use a series/season/episode layout. Animations and Documentaries use `Movies/` and `Series/` subdirectories; concerts use `Artist - Event (Year)` when adequately identified.

## Approved safety and automation policies

- **Local administrator:** one authenticated admin account with server-side authorization; Tailscale/VPN is an additional security boundary.
- **Torrent-safe relocation:** qBittorrent-managed moves for compatible torrents; NAS torrent tree and hardlinks for compatible multi-file packages; manual review for unsafe fallbacks.
- **Bulgarian-first:** verified BG audio takes priority; materially better non-BG editions may coexist; multi-factor comparison never auto-deletes old library media.
- **Safe metadata ownership:** updates are automatic only for unchanged ViMag-owned NFO/artwork; external edits require review.
- **Quarantine and restore:** approved and dependency-safe; permanent deletion of library files is out of scope for v1.
- **Seeding and publish verification:** no successful completion without valid torrent mapping and Jellyfin verification; missing noncritical subtitles can yield `CompletedWithWarnings`.
- **Technical prerequisites:** G-01..G-06 are not yet verified and block write-capable production operations.

## Planned capabilities

| Area | Scope |
| --- | --- |
| Automatic Intake | Completion hook plus reconciliation for missed events; one parent job per torrent; support multi-item/season packs |
| Job Dashboard | Status, step progress, detailed audit trail, pause/resume/retry/review |
| Identification | Movie/show detection, provider match, media streams, language confidence, integrity |
| Quality & Duplicates | Version comparison, edition-aware decisions, BG-first policy, seeding dependency checks |
| Safe Move Queue | Physical transfer progress, copy/integrity verification, qBittorrent mapping and recovery |
| Library Maintenance | Non-destructive scan, detect/organize pre-existing media, explicit cleanup approvals |
| Subtitles | Existing/embedded/external BG tracks, release matching, timing/sync and manual review |
| Jellyfin | Refresh request, wait for recognition, validate title, category, versions and track availability |
| Settings | Connections, storage, naming, quality, automation, service health and logs |

## Deployment context (planned, not implemented)

- Host: ViMag (Linux / Docker Compose), reverse proxy Traefik v3.6, private access via Tailscale/internal DNS.
- Proposed internal URL: `https://manager.vimag.app`.
- Existing Docker network: `vimag_default`.
- Proposed stack: Vue 3 frontend; FastAPI backend; persistent background worker; SQLite initially; ffprobe / MediaInfo; qBittorrent Web API; Jellyfin REST API; TMDb and configurable subtitle providers.
- Target Docker Hub account for **future** images: `vesovasilev` (publication/CI/CD not configured).
- No extra message broker or database infrastructure until measurements justify it.

No Docker image, GitHub Actions workflow, token, or `docker-compose.yml` is created by this documentation phase.

## Documentation and approved UX reference

- [Approved Technical Scope v1.0](docs/technical-scope-v1.0.md): boundaries, design decisions, workflows, data model, safety rules, acceptance tests and open questions.
- [Approved Implementation Design v1.0](docs/implementation-design-v1.0.md): Docker architecture, PostgreSQL job queue, qBittorrent/Jellyfin contracts, operation journal, safety gates and rollout plan; documentation approval is not authorization to deploy.
- [Approved interactive HTML wireframe v1.0](wireframes/vimag-media-manager-v1.0.html): local, browser-run demo with simulated jobs; **not** a running application.

## Project phases

| Phase | Status | Gate |
| --- | --- | --- |
| A. UX wireframe | **Approved** | Interactive scenarios reviewed |
| B. Technical scope and architecture | **Approved — v1.0** | All 22 product decisions confirmed; six technical safety gates remain before real file operations |
| C. Implementation | **Not started** | Scope approval |
| D. Test in isolated media fixtures | **Not started** | Tests demonstrate torrent integrity and recoverability |
| E. NAS/qBittorrent pilot | **Not started** | Backup, rollback and read-only baseline verified |
| F. Production deployment / Docker Hub publishing | **Not started** | Operational acceptance |

## Safety and security notes

- This repository is planned to be public. Never commit qBittorrent credentials, Docker Hub tokens, TMDb keys, NAS secrets, torrent identifiers from private trackers, or real library paths that reveal confidential data beyond the documented generic mounts.
- No video/audio content is stored in this source repository.
- The wireframe performs **no** filesystem, torrent or Docker operations.
- No automatic transcoding, remux, track deletion, or media-file mutation is planned for the first release.
- Service accounts and NAS permissions must be least-privilege; remote access stays within the existing trusted network.

## References

- [qBittorrent WebUI API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-4.1%29)
- [Jellyfin movie organization and multiple versions](https://jellyfin.org/docs/general/server/media/movies/)
- [Jellyfin TV show organization](https://jellyfin.org/docs/general/server/media/shows/)
- [Docker Build in GitHub Actions](https://docs.docker.com/build/ci/github-actions/)

---

**Project rule:** Technical scope and safe import semantics are agreed **before** application development or deployment begins.
