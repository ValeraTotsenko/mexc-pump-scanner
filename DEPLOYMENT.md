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

Environment variables can be referenced in the YAML using `${VAR}` syntax. See `.env.example` for all available variables.

## Environment variables

Create a `.env` file based on the example below and fill in your keys:

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

## Running locally

1. Install Python 3.11+ and `pip`.
2. Create and activate a virtual environment:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies: `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and edit values.
5. Start the bot for selected pairs:

```bash
python -m scanner.bot BTC_USDT ETH_USDT
```

Prometheus metrics will be exposed on `http://localhost:8000/metrics`.

## Running with Docker

Build and start via `docker-compose`:

```bash
docker-compose up -d --build
```

The container uses variables from your `.env` file. The helper script
`deploy.sh` installs Docker Compose, downloads this file and starts the stack.
Run it in one command by piping the script from GitHub and passing the URL to
your secrets:

```bash
curl -fsSL https://raw.githubusercontent.com/you/mexc-pump-scanner/main/deploy.sh | bash -s -- https://host/your.env
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
