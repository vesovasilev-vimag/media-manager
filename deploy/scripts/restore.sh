#!/bin/sh
set -eu
source_dir=${1:?Usage: restore.sh /absolute/backup-directory empty_restore_database}
restore_database=${2:?An empty restore database must be explicitly named}
filename=${3:-predeploy.backup}
case "$filename" in *[!A-Za-z0-9_.-]*|.*|*/*) printf '%s\n' 'Unsafe backup filename' >&2; exit 1;; esac
case "$restore_database" in vimag_restore_*) ;; *) printf '%s\n' 'Restore must target an isolated vimag_restore_* database, never the live database.' >&2; exit 1;; esac
docker compose --env-file .env -f compose.prod.yaml run --rm --no-deps -e "VIMAG_DB_NAME=$restore_database" -v "$source_dir:/backups:ro" api python -m app.ops restore "/backups/$filename" --confirm-empty
