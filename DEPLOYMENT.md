# Deployment Guide

This document explains how to configure and run the project both locally and in Docker.

## Configuration (`config.yaml`)

- `mexc.ws_url` – WebSocket endpoint for market data.
- `mexc.rest_url` – REST API base URL.
- `mexc.api_key` / `mexc.api_secret` – API credentials used for optional trading.
- `scanner.stake_usdt` – amount in USDT used by the *Buy* button.
- `scanner.prob_threshold` – minimum probability required to send an alert.
- `scanner.metrics.*` – threshold values for VSR, PM, OBI, spread and listing age.
- `scout.min_quote_vol_usd` – minimum 24h quote volume for a pair to be tracked.
- `scout.top_n` – number of pairs returned by the volume scout.
- `ws.max_streams_per_conn` – max streams per WebSocket connection.
- `ws.max_msg_per_sec` – send rate limit per connection.
- `telegram.token` – Telegram bot token.
- `telegram.allowed_ids` – comma separated list of Telegram user IDs allowed to interact.

Environment variables can be referenced in the YAML using `${VAR}` syntax. The required names are listed below.

## Required environment variables

Set the following variables in your shell or add them to a `.env` file:

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

Copy `.env.example` to `.env` and fill in your own values. **Important:** never commit your secrets to version control.

## Running locally

1. Install Python 3.11+ and `pip`.
2. Create and activate a virtual environment:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies: `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and fill in your credentials.

5. Start the bot for selected pairs and run tests if desired:

```bash
python -m scanner.bot BTC_USDT ETH_USDT
pytest -q
```

Prometheus metrics will be exposed on `http://localhost:8000/metrics`.
The Grafana dashboard JSON remains in `monitoring/` and works as before.

## Running with Docker

Build and start via `docker-compose` (rebuild if dependencies changed):
Dependencies like `httpx[socks]` are installed during the build stage.

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

The scanner targets small VPS instances. With Volume‑Scout enabled it typically uses under **300&nbsp;MB RAM** and about 30% CPU on a **CX32 (2 vCPU / 4&nbsp;GB RAM)** machine. Higher loads may require more resources.

The service opens several WebSocket links (max 30 streams each) and polls the REST endpoint `/api/v3/ticker/24hr` every minute to adjust subscriptions.

## Limitations

- Only spot pairs on MEXC are supported.
- Orders are placed via market orders (code disabled by default).
- No external backups; data is stored in `./data`.
