# Deployment Guide

This document explains how to configure and run the project both locally and in Docker.

## Configuration (`config.yaml`)

- `mexc.ws_url` – WebSocket endpoint for market data.
- `mexc.rest_url` – REST API base URL.
- `mexc.api_key` / `mexc.api_secret` – API credentials used for optional trading.
- `scanner.stake_usdt` – amount in USDT used by the *Buy* button.
- `scanner.prob_threshold` – minimum probability required to send an alert.
- `scanner.metrics.*` – threshold values for VSR, PM, OBI, spread and listing age.
- `telegram.token` – Telegram bot token.
- `telegram.allowed_ids` – comma separated list of Telegram user IDs allowed to interact.

Environment variables can be referenced in the YAML using `${VAR}` syntax. The required names are listed below.

## Required environment variables

Set the following variables in your shell or add them to the virtual environment activation script:

```bash
MEXC_KEY=your_mexc_key
MEXC_SECRET=your_mexc_secret
TG_TOKEN=your_telegram_token
ALLOWED_IDS=123456789
STAKE_USDT=100
PROB_THRESHOLD=0.60
THRESH_VSR=5
THRESH_PM=0.02
THRESH_OBI=0.25
THRESH_SPREAD=0.015
THRESH_LISTING_AGE=900
```

**Important:** never commit your secrets to version control.

## Running locally

1. Install Python 3.11+ and `pip`.
2. Create and activate a virtual environment:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies: `pip install -r requirements.txt`.
4. Export the required variables, e.g. add them to `.venv/bin/activate`:

   ```bash
   export MEXC_KEY=your_mexc_key
   export MEXC_SECRET=your_mexc_secret
   export TG_TOKEN=your_telegram_token
   export ALLOWED_IDS=123456789
   ```

5. Start the bot for selected pairs and run tests if desired:

```bash
python -m scanner.bot BTC_USDT ETH_USDT
pytest -q
```

Prometheus metrics will be exposed on `http://localhost:8000/metrics`.
The Grafana dashboard JSON remains in `monitoring/` and works as before.

## Running with Docker

Build and start via `docker-compose`:

```bash
docker-compose up -d --build
```

The container reads variables from the host environment. The helper script
`deploy.sh` installs Docker if missing, clones the repo and runs `docker compose up -d --build`. It can also
create a systemd unit so the service restarts automatically.
Run it in one command by piping the script from GitHub:

```bash
curl -fsSL https://raw.githubusercontent.com/you/mexc-pump-scanner/main/deploy.sh | bash
```

Verify that the service is running:

```bash
docker compose ps
```

## Hardware requirements

The scanner targets small VPS instances. It uses less than 25% CPU and under 250&nbsp;MB RAM on a **CX32 (2 vCPU / 4&nbsp;GB RAM)** machine. Higher loads may require more resources.

## Limitations

- Only spot pairs on MEXC are supported.
- Orders are placed via market orders (code disabled by default).
- No external backups; data is stored in `./data`.
