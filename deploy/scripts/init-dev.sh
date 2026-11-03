#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
mkdir -p secrets
for name in db_password setup_token; do
  if [ ! -f "secrets/$name" ]; then
    openssl rand -base64 48 > "secrets/$name"
  fi
done
chmod 0444 secrets/db_password secrets/setup_token
printf '%s\n' 'Development secrets initialized without printing values.'
