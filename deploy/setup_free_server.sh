#!/usr/bin/env bash
# Run on a new Ubuntu 24.04 VM; this does not create or upgrade cloud resources.
set -euo pipefail
umask 077

cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ $# -ne 2 || "$1" != "--public-ip" ]]; then
    echo "Usage: bash deploy/setup_free_server.sh --public-ip YOUR_PUBLIC_IPV4" >&2
    exit 2
fi

source /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 24.04 ]]; then
    echo "This installer supports Ubuntu 24.04 only." >&2
    exit 1
fi
architecture=$(dpkg --print-architecture)
if [[ "$architecture" != arm64 && "$architecture" != amd64 ]]; then
    echo "Use an ARM64 or AMD64 VM." >&2
    exit 1
fi
command -v python3 >/dev/null || { echo "Install python3 first." >&2; exit 1; }
hostname=$(python3 deploy/init_env.py --public-ip "$2" --print-domain)

# Never silently replace encryption keys or change an existing site's origin.
if [[ -e .env.cloud ]]; then
    python3 - "$hostname" <<'PY'
from pathlib import Path
import sys
lines = Path('.env.cloud').read_text(encoding='utf-8').splitlines()
domains = [line.split('=', 1)[1] for line in lines if line.startswith('DAYMARK_DOMAIN=')]
if domains != [sys.argv[1]]:
    raise SystemExit('Existing .env.cloud uses another domain. Keep its keys; update the domain explicitly or use the existing Compose deployment.')
PY
else
    python3 deploy/init_env.py --public-ip "$2"
fi
chmod 600 .env.cloud

admin=()
if [[ "$EUID" -ne 0 ]]; then
    command -v sudo >/dev/null || { echo "Root or sudo is required." >&2; exit 1; }
    admin=(sudo)
fi

if ! command -v docker >/dev/null; then
    # Do not remove packages or overwrite an administrator's existing Docker repository.
    for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q '^install ok installed$'; then
            echo "Existing package $package requires manual Docker setup. See the README." >&2
            exit 1
        fi
    done
    if [[ -e /etc/apt/sources.list.d/docker.sources || -e /etc/apt/sources.list.d/docker.list || -e /etc/apt/keyrings/docker.asc ]]; then
        echo "Existing Docker repository configuration found; finish Docker installation manually." >&2
        exit 1
    fi
    "${admin[@]}" apt-get update
    "${admin[@]}" apt-get install -y ca-certificates curl
    "${admin[@]}" install -m 0755 -d /etc/apt/keyrings
    "${admin[@]}" curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    "${admin[@]}" chmod a+r /etc/apt/keyrings/docker.asc
    "${admin[@]}" tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $architecture
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    "${admin[@]}" apt-get update
    "${admin[@]}" apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

"${admin[@]}" docker compose version >/dev/null || { echo "Install the Docker Compose plugin first." >&2; exit 1; }
"${admin[@]}" systemctl enable --now docker
"${admin[@]}" docker compose --env-file .env.cloud config --quiet
"${admin[@]}" docker compose --env-file .env.cloud up --build -d
"${admin[@]}" docker compose --env-file .env.cloud ps

echo "Containers started. HTTPS certificate issuance may take a few minutes."
echo "Open https://$hostname after verifying 80/443 are reachable."
echo "Read DAYMARK_INVITE_CODE privately from .env.cloud to register."
echo "Back up the data volume and .env.cloud together; do not use docker compose down -v."
