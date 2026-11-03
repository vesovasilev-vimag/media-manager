#!/bin/sh
set -eu
destination=${1:?Usage: backup.sh /absolute/backup-directory}
test -d "$destination"
filename=${2:-$(date -u +%Y%m%dT%H%M%SZ).backup}
case "$filename" in *[!A-Za-z0-9_.-]*|.*|*/*) printf '%s\n' 'Unsafe backup filename' >&2; exit 1;; esac
docker compose --env-file .env -f compose.prod.yaml run --rm --no-deps -v "$destination:/backups" api python -m app.ops backup "/backups/$filename"
