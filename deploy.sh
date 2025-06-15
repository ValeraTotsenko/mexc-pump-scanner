#!/usr/bin/env bash
set -e

# URL of the .env file containing deployment secrets
ENV_URL="${1:-${ENV_URL:-}}"

if [ -z "$ENV_URL" ]; then
    echo "Usage: ENV_URL=<url> $0 [url]" >&2
    exit 1
fi

sudo apt update && sudo apt -y install docker.io docker-compose curl
git clone https://github.com/you/mexc-pump-scanner.git
cd mexc-pump-scanner
curl -fsS "$ENV_URL" -o .env
sudo docker-compose up -d --build
