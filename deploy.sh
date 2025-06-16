#!/usr/bin/env bash
set -euo pipefail

# Simple logger
echo_step(){ echo -e "\033[32m✅ $1\033[0m"; }
echo_info(){ echo -e "\033[34m$1\033[0m"; }
echo_err(){ echo -e "\033[31m$1\033[0m" >&2; }

# Verify required env vars exist
check_env(){
  local missing=0
  for v in "$@"; do
    if [ -z "${!v:-}" ]; then
      echo_err "Environment variable $v not set"
      missing=1
    fi
  done
  if [ $missing -eq 1 ]; then exit 1; fi
}

REQUIRED_VARS=(MEXC_KEY MEXC_SECRET TG_TOKEN ALLOWED_IDS)
check_env "${REQUIRED_VARS[@]}"

REPO_DIR="$(pwd)"
SERVICE_NAME="mexcscanner.service"

choose_deploy(){
  echo_info "Choose deployment method:"
  echo_info "1) Docker"
  echo_info "2) Python venv"
  read -rp "> " choice
  case "$choice" in
    1) deploy_docker ;;
    2) deploy_venv ;;
    *) echo_err "Invalid choice"; exit 1;;
  esac
}

deploy_docker(){
  echo_step "Installing Docker"
  if ! command -v docker >/dev/null; then
    sudo apt-get update
    sudo apt-get -y install docker.io
  fi
  if ! command -v docker-compose >/dev/null && ! docker compose version >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get -y install docker-compose docker-compose-plugin
  fi
  sudo systemctl enable --now docker

  echo_step "Building container"
  sudo docker compose up -d --build

  create_systemd_docker
}

deploy_venv(){
  echo_step "Setting up Python venv"
  if ! command -v python3 >/dev/null; then
    echo_err "python3 not installed" && exit 1
  fi
  python3 -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
  deactivate
  create_systemd_venv
}

create_systemd_docker(){
  if command -v systemctl >/dev/null; then
    sudo tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null <<SERVICE
[Unit]
Description=MEXC Pump Scanner (Docker)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=$REPO_DIR
EnvironmentFile=/etc/environment
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SERVICE
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME"
    sudo systemctl status "$SERVICE_NAME" --no-pager
  fi
}

create_systemd_venv(){
  if command -v systemctl >/dev/null; then
    sudo tee "/etc/systemd/system/$SERVICE_NAME" >/dev/null <<SERVICE
[Unit]
Description=MEXC Pump Scanner (venv)
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
EnvironmentFile=/etc/environment
ExecStart=$REPO_DIR/.venv/bin/python -m scanner.bot
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE
    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME"
    sudo systemctl status "$SERVICE_NAME" --no-pager
  fi
}

choose_deploy
