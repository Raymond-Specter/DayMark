#!/usr/bin/env sh
# Run from the repository root. Stop writes for a consistent DB + file backup.
set -eu
umask 077
mkdir -p cloud-backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="cloud-backups/daymark-$stamp.tar.gz"
docker compose --env-file .env.cloud stop backend
trap 'docker compose --env-file .env.cloud start backend' EXIT HUP INT TERM
docker compose --env-file .env.cloud run --rm --no-deps -T --entrypoint tar backend -czf - -C /app/data . > "$archive"
cp .env.cloud "cloud-backups/daymark-$stamp.env"
echo "Backup saved in cloud-backups. Copy BOTH files to private storage on another machine."
