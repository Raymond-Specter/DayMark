#!/usr/bin/env bash
# Run from an extracted, verified offline bundle. Preserve the existing server secrets.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -ne 1 ]]; then
    echo "Usage: bash deploy/start_offline.sh /absolute/path/to/.env.cloud" >&2
    exit 2
fi
config=$(realpath -e "$1")
if [[ ! -f "$config" ]]; then
    echo "Cloud config is missing. Do not regenerate an existing encryption key." >&2
    exit 1
fi
if [[ "$(uname -m)" != x86_64 ]]; then
    echo "This bundle requires an AMD64 (x86_64) server." >&2
    exit 1
fi
sha256sum -c SHA256SUMS
admin=()
if [[ "$EUID" -ne 0 ]]; then admin=(sudo); fi
"${admin[@]}" docker load --input images.tar.gz
# The original /root/DayMark deployment defaults to this same project name.
# Keeping it avoids silently creating new, empty data and certificate volumes.
compose=("${admin[@]}" docker compose -p daymark --env-file "$config" --env-file release.env
    -f compose.yaml -f compose.offline.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --no-build --pull never
"${compose[@]}" ps -a
echo "Containers started without pulling or building images. Check your domain's HTTPS next."
