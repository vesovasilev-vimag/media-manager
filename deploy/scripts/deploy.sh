#!/bin/sh
set -eu
manifest=${1:?Usage: deploy.sh release-manifest.json}
python3 scripts/deploy.py "$manifest"
