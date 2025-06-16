#!/usr/bin/env bash
set -euo pipefail

# --- Logging ---
echo_step() { echo -e "\033[32m✅ $1\033[0m"; }
echo_info() { echo -e "\033[34m$1\033[0m"; }
echo_err()  { echo -e "\033[31m$1\033[0m" >&2; }

# --- Проверка окружения ---
REQUIRED_VARS=(MEXC_KEY MEXC_SECRET TG_TOKEN ALLOWED_IDS)
check_env() {
  local missing=0
  for v in "$@"; do
    if [ -z "${!v:-}" ]; then
      echo_err "❌ Переменная окружения $v не задана"
      missing=1
    fi
  done
  if [ $missing -eq 1 ]; then exit 1; fi
}
check_env "${REQUIRED_VARS[@]}"

REPO_DIR="$(pwd)"
SERVICE_NAME="mexcscanner.service"

# --- Выбор способа установки ---
choose_deploy() {
  echo_info "Choose deployment method:"
  echo_info "1) Docker"
  echo_info "2) Python venv"
  read -rp "> " choice
  case "$choice" in
    1) deploy_docker ;;
    2) deploy_venv ;;
    *) echo_err "Invalid choice"; exit 1 ;;
  esac
}

# --- Docker ---
deploy_docker() {
  echo_step "Installing Docker stack"
  sudo apt-get update -qq
  sudo apt-get install -y docker.io docker-compose docker-compose-plugin
  sudo systemctl enable --now docker

  echo_step "Building and starting container"
  sudo docker compose up -d --build

  create_systemd_docker
}

# --- Venv ---
deploy_venv() {
  echo_step "Installing Python 3.11 and system packages"
  sudo apt-get update -qq
  sudo apt-get install -y python3.11 python3.11-venv python3.11-distutils build-essential git cron

  echo_step "Creating virtual environment"
  python3.11 -m venv .venv
  source .venv/bin/activate

  echo_step "Installing Python dependencies"
  pip install --upgrade pip
  pip install -r requirements.txt
  deactivate

  create_systemd_venv
}

# --- systemd для Docker ---
create_systemd_docker() {
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
}

# --- systemd для venv ---
create_systemd_venv() {
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
}

# --- Запуск ---
choose_deploy
