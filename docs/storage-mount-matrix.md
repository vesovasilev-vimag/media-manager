# Storage and mount contract

Only Worker receives media. API and web cannot touch media files. PostgreSQL stays on verified local ext4/XFS, never NTFS/FUSE, autofs or CIFS.

| Logical root | Host | Worker | qBt | Jellyfin |
|---|---|---|---|---|
| staging | `/mnt/storage/qbt/complete` | `/downloads/complete` | `/downloads/complete` | Excluded |
| library | `/mnt/nas/Movies/Library` | `/nas-movies/Library` | `/library` | `VIMAG_JELLYFIN_LIBRARY_ROOT` + relative path, verified at deployment |
| torrent store | `/mnt/nas/Movies/.vimag-torrent-store` | `/nas-movies/.vimag-torrent-store` | `/torrent-store` only after validated mount cutover | Excluded |
| quarantine | `/mnt/nas/Movies/Quarantine` | `/nas-movies/Quarantine` | No dependencies allowed | Excluded |
| sidecar backups | `/mnt/nas/Movies/.vimag-sidecar-backups` | Same single NAS bind | Excluded | Excluded |

Worker has **one** `/mnt/nas/Movies:/nas-movies` bind. Hardlinks are made within that bind. A hash/readback plus scratch write-through proof establishes content alias capability; CIFS inode or link counts alone never authorize cleanup. Active media bytes are never modified.

The five categories are fixed: `movies`, `series`, `animations`, `documentaries`, `concerts`. Animations and Documentaries each have `Movies` and `Series` subtrees. The selected top-level category cannot change implicitly. Episode plans include specials, ranges and part markers. Movie files start with the exact folder prefix; editions remain independent in the DB.

`bind.create_host_path=false` prevents accidental empty mount creation. Worker checks the exact configured CIFS source in `/proc/self/mountinfo`, free bytes and reserve immediately before transfer. Host preflight separately checks the mounted filesystem and PostgreSQL disk. Runtime UID/GID is 1000:1000; host scratch success does not establish final ACL proof.

Existing qBt `/downloads` and `/library` mounts are preserved. **This repository does not edit qBt or Jellyfin Compose.** Multi-file live import remains gated until `/torrent-store` is visible to qBt and the shared source maps to Worker's single NAS bind. Existing category save paths remain untouched. Jellyfin must not index the torrent store, quarantine, backups or overlapping parent/child library roots.

Dev Compose uses Docker-managed synthetic volumes. It has no production NAS or download binds. Its PostgreSQL port is loopback-only for local tests; production has no published DB/API/Worker ports.
