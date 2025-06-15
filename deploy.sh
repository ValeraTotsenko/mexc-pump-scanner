#!/usr/bin/env bash
set -euo pipefail

# URL of the .env file containing deployment secrets
ENV_URL="${1:-${ENV_URL:-}}"
REPO_URL="https://github.com/you/mexc-pump-scanner.git"
REPO_DIR="mexc-pump-scanner"

if [ -z "$ENV_URL" ]; then
    echo "Usage: ENV_URL=<url> $0 [url]" >&2
    exit 1
fi

# Install Docker and Docker Compose if missing
if ! command -v docker >/dev/null; then
    sudo apt-get update
    sudo apt-get -y install docker.io
fi
if ! command -v docker-compose >/dev/null && ! docker compose version >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get -y install docker-compose docker-compose-plugin
fi
sudo systemctl enable --now docker

# Clone the repo if absent
if [ ! -d "$REPO_DIR" ]; then
    git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

# Fetch secrets
curl -fsS "$ENV_URL" -o .env

# Build and start the container
sudo docker compose up -d --build

# Optionally configure a systemd unit
if command -v systemctl >/dev/null; then
    SERVICE_FILE=/etc/systemd/system/mexc-pump-scanner.service
    sudo tee "$SERVICE_FILE" >/dev/null <<SERVICE
[Unit]
Description=MEXC Pump Scanner
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE
    sudo systemctl daemon-reload
    sudo systemctl enable --now mexc-pump-scanner.service
fi
