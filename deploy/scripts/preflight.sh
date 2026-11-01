#!/bin/sh
set -eu
# Read-only host checks. Never creates mountpoints or changes qBt/Jellyfin configuration.
: "${PGDATA_HOST:?Set verified PGDATA_HOST}"
test -d "$PGDATA_HOST"
fs=$(findmnt -n -o FSTYPE -T "$PGDATA_HOST")
case "$fs" in ext4|xfs) ;; *) printf 'G-DB-01 blocked: PGDATA filesystem %s\n' "$fs" >&2; exit 1;; esac
test -d /mnt/storage/qbt/complete
test -d /mnt/nas/Movies/Library
nas_fs=$(findmnt -n -o FSTYPE -T /mnt/nas/Movies/Library)
test "$nas_fs" = cifs || { printf '%s\n' 'G-02 blocked: NAS is not an authenticated CIFS mount' >&2; exit 1; }
docker network inspect vimag_default --format '{{.Name}}' >/dev/null
docker info --format '{{.OSType}}/{{.Architecture}}'
printf '%s\n' 'Read-only host prerequisites passed. Worker UID, scratch hardlinks, secrets, backup and live gates remain independent.'
