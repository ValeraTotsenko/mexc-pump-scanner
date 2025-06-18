# mexc-pump-scanner
## Техническое задание (ТЗ)

**Проект:** «MEXC Pump-Scanner»
**Версия:** 0.9 (MVP, real-time скринер + Telegram-бот, без блока бэктеста)
**Дата:** 15 июня 2025 г.

Дополнительные инструкции по конфигурации и развёртыванию см. в [DEPLOYMENT.md](DEPLOYMENT.md).

---

### 1. Цель и результат

Создать лёгкий скринер, который *в режиме реального времени* отслеживает все спотовые пары на бирже **MEXC**, вычисляет набор микроструктурных метрик, оценивает вероятность краткосрочного «пампа» (≥ 10 % роста цены в горизонте ≤ 20 мин) и отправляет сигналы в Telegram-чат. Система развёртывается одной командой на VPS и работает 24 × 7 без ручного вмешательства.

---

### 2. Функциональные требования

| №    | Требование                                                                                                                          |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------- |
| F-1  | Подключиться к **WebSocket Spot V3** MEXC, подписаться на *все* пары (≈ 1 200+) по потокам **kline\@1s** и **depth.diff**.          |
| F-2  | Поддерживать собственный order-book L10 (± 10 bps) для каждой пары.                                                                 |
| F-3  | Каждую секунду вычислять метрики:<br>**VSR, PM, OBI, VC, CumDepthΔ, Spread%, ListingAge** (формулы — см. § 5).                      |
| F-4  | Пропускать метрики через **Rule Filter** → **Logistic Regression**.                                                                 |
| F-5  | При `prob_pump ≥ 0.60` формировать сигнал и отправлять карточку в Telegram-чат/группу.                                              |
| F-6  | Добавлять к карточке две инлайн-кнопки: **«Купить \$100»** (прокси-вызов PUT ордера через REST) и **«Пропустить»**.                 |
| F-7  | Сохранять в **SQLite** все сигналы и действия пользователя.                                                                         |
| F-8  | Позволять администратору изменять пороги и веса без перезапуска (команда `/reload`).                                                |
| F-9  | Автоматически переподнимать WS-соединения при разрыве, соблюдать лимит 30 стримов на линк и 100 msg/s ([mexcdevelop.github.io][1]). |
| F-10 | Латентность от прихода тика до отправки сигнала ≤ 2 с.                                                                              |

---

### 3. Нефункциональные требования

| Категория          | Ограничение / цель                                                     |                                |
| ------------------ | ---------------------------------------------------------------------- | ------------------------------ |
| Производительность | ≤ 25 % CPU и ≤ 250 MB RAM на **CX32 (2 vCPU / 4 GB)**.                 |                                |
| Качество данных    | Дропает пару, если спред > 1.5 % или объём < \$20 k / 5 мин.           |                                |
| Безопасность       | Все API-ключи задаются в окружении, доступ к Telegram-боту — по `ALLOWED_IDS`.     |                                |
| Надёжность         | Авто-retry при HTTP 429/418, журнал ошибок в `stderr` + ротация.       |                                |
| Развёртывание      | `curl -fsSL https://raw.githubusercontent.com/you/mexc-pump-scanner/main/deploy.sh | bash` — единственная команда. |

---

### 4. Высокоуровневая архитектура

```
                      REST polling
┌──────────────────┐   /api/v3/ticker/24hr
│  Volume-Scout    │◀─────────────────────┐
└────────┬─────────┘                      │
         │ hot pairs                      │
┌────────▼────────┐                      │
│ SubscriptionMgr │                      │
└────────┬────────┘                      │
         │ subscribe/unsub               │
┌────────▼────────────┐                  │
│   WS-Collector       │─────────────────┘
│  > 30-stream links   │
└────────┬────────────┘
         │ ticks (1 s)
┌────────▼────────────┐
│  Feature Engine     │
└────────┬────────────┘
         │ FeatureVector
┌────────▼────────────┐
│ Rule-Filter │ Model │
└────────┬────────────┘
         │ Signal(p,features)
┌────────▼────────────┐
│  Alert-Engine (Bot) │
│ + optional REST     │
└────────┬────────────┘
         │ user actions
┌────────▼────────────┐
│ Persistence (DB)    │
└─────────────────────┘
```

---

### 5. Метрики, формулы и пороги (MVP-профиль «Alpha-1»)

| Метрика        | Формула (Python-like)                    | Окно  | Порог   |
| -------------- | ---------------------------------------- | ----- | ------- |
| **VSR**        | `vol_5m / median(vol_6h)`                | 5 мин | > 5     |
| **VC**         | `max(vol_1m_last5) / vol_5m`             | 5 мин | < 0.5   |
| **PM**         | `(last - vwap_5m)/vwap_5m`               | 5 мин | > 0.02  |
| **OBI**        | `(bid1 - ask1)/(bid1+ask1)`              | —     | > 0.25  |
| **CumDepthΔ**  | `sum_bid±3bps(t) - sum_bid±3bps(t-180s)` | 3 мин | > 0     |
| **Spread%**    | `(ask1 - bid1)/mid`                      | —     | < 0.015 |
| **ListingAge** | `now - first_trade_ts`                   | —     | > 900 с |

**Скоринг:**
`score = 0.4·VSR_norm + 0.35·PM_norm + 0.25·OBI_norm`
`prob_pump = sigmoid( β₀ + β·features )` (коэффициенты в `model.json`).
Сигнал генерируется при `prob_pump ≥ 0.60`.

---

### 6. Компоненты и их интерфейсы

#### 6.1 Collector (`scanner/collector.py`)

* **Класс** `MexcWSClient`

  * `connect()` — открывает N сокетов, автосплит по 30 стримов ([mexcdevelop.github.io][1], [mexc.com][2]).
  * `subscribe(pair)` / `unsubscribe(pair)`
  * авто-отписка при `spread > 1.5 %` или `volume_5m < $20k`
  * `yield ticks` → `Tick(kline: dict, depth: dict)`
  * `get_best(pair)` — лучшая цена bid/ask
  * `get_cum_depth(pair)` — суммарный объём внутри ±10 bps

#### 6.2 Feature Engine (`scanner/features.py`)

* `RollingWindow(size_sec)` реализован на `collections.deque` + NumPy vector ops.
* Возвращает `FeatureVector` (`namedtuple`) с флагом `ready`.

#### 6.3 RuleFilter (`scanner/rules.py`)

```python
def is_candidate(fv: FeatureVector, cfg: Dict) -> bool:
    return (
        fv.vsr > cfg['vsr'] and
        fv.pm  > cfg['pm']  and
        fv.obi > cfg['obi'] and
        fv.spread < cfg['spread'] and
        fv.listing_age > cfg['listing_age_min']
    )
```

#### 6.4 Model (`scanner/model.py`)

* Однофайловая `LogisticRegression` (pickle \~ 1 KB).
* `predict_proba(fv: FeatureVector) -> float`.

#### 6.5 AlertEngine / Telegram-бот (`scanner/bot.py`)

* Библиотека `python-telegram-bot≥21`.
* **Команды:** `/start`, `/help`, `/status`, `/reload`, `/cfg key val`.
* Формат сигнала (Markdown V2):

  ```
  🚀 *{pair}*  — VSR {vsr:.1f}  PM {pm:.2%}  Prob {p:.2f}
  Цена: `{price:.6f}`  ⏱ {timestamp}
  ```
* Инлайн-кнопки:

  * `buy_{pair}` — POST `/api/v3/order` (MEXC REST, MARKET, qty=\$stake/price)
  * `skip_{id}` — бот присылает «Ignored».

#### 6.6 Persistence (`storage.py`)

* **SQLite** (`sqlite3`): таблицы `signals`, `actions`.
* **Parquet** (`signals_YYYYMM.parquet`): дублирование сигналов.

#### 6.7 Config (`config.yaml`)

```yaml
mexc:
  # WebSocket Spot V3 endpoint
  ws_url: wss://wbs.mexc.com/ws
  rest_url: https://api.mexc.com
  api_key: ${MEXC_KEY}
  api_secret: ${MEXC_SECRET}
scanner:
  stake_usdt: ${STAKE_USDT}
  prob_threshold: ${PROB_THRESHOLD}
  metrics:
    vsr: ${THRESH_VSR}
    pm: ${THRESH_PM}
    obi: ${THRESH_OBI}
    spread: ${THRESH_SPREAD}
    listing_age_min: ${THRESH_LISTING_AGE}
scout:
  min_quote_vol_usd: 100000
  top_n: 200
ws:
  max_streams_per_conn: 30
  max_msg_per_sec: 100
telegram:
  token: ${TG_TOKEN}
  allowed_ids: [${ALLOWED_IDS}]
```

**Пояснения к параметрам**

- `scout.min_quote_vol_usd` — пары с меньшим суточным объёмом игнорируются.
- `scout.top_n` — сколько «горячих» пар возвращает Volume‑Scout.
- `ws.max_streams_per_conn` — предел потоков на одном WS‑линке.
- `ws.max_msg_per_sec` — ограничение скорости отправки команд.

---

### 7. Развёртывание

#### 7.1 Dockerfile (алгоритм)

1. `FROM python:3.12-slim`
2. `RUN pip install -r requirements.txt`
3. Копирование исходного кода.
4. `CMD ["python", "-m", "scanner.bot"]`

#### 7.2 docker-compose.yml

```yaml
services:
  scanner:
    build: .
    volumes:
      - ./data:/app/data
    logging:
      driver: "json-file"
      options: {max-size: "10m", max-file: "5"}
```

#### 7.3 deploy.sh (единственный скрипт)

```bash
#!/usr/bin/env bash
# installs Docker if needed, fetches secrets and runs the service
git clone https://github.com/you/mexc-pump-scanner.git || true
cd mexc-pump-scanner
sudo docker compose up -d --build
# rebuild to install new dependencies like httpx[socks]
```

Скрипт ставит Docker при необходимости и может создать unit `systemd`, чтобы
контейнер автоматически перезапускался после перезагрузки.

После выполнения можно проверить состояние контейнера командой:

```bash
docker compose ps
```

---

### 8. Мониторинг и логирование

| Метод                        | Что отслеживаем                                                  |
| ---------------------------- | ---------------------------------------------------------------- |
| **Prometheus-exporter**      | latency\_pipeline\_ms, ws\_reconnects\_total, signals\_per\_hour |
| **Grafana dashboard** (json) | график сигналов, CPU/RAM, WS-traffic.                            |
| **stderr**                   | исключения Python, stack-trace → `alerts.log`                    |

Экспорт метрик доступен на `http://localhost:8000/metrics`.

Мониторинг не затронут реорганизацией: JSON-дэшборд лежит в `monitoring/` и
метрики по-прежнему слушают на том же порту.

---

### 9. Тесты и приёмка

| ID  | Критерий              | Условие принятия                                                 |
| --- | --------------------- | ---------------------------------------------------------------- |
| A-1 | Латентность           | `metrics.latency_pipeline_ms_p95 ≤ 2000`                         |
| A-2 | Устойчивость          | 24 ч без падений, не более 5 reconnect/час                       |
| A-3 | Корректность сигналов | На тестовом set-е (1 сутки тик-дампа) число сигналов = 92 ± 5 %. |
| A-4 | Безопасность          | Бот игнорирует сообщения от ID вне `allowed_ids`.                |
| A-5 | Запуск                | `deploy.sh` завершился без ошибок, контейнер “healthy”.          |
| A-6 | Volume‑Scout         | REST опрос `/api/v3/ticker/24hr` каждые `poll_interval` секунды и корректные подписки |
| A-7 | Лимит потоков        | число активных стримов ≤ `ws.max_streams_per_conn` × кол‑во соединений |

---

### 10. Ограничения MVP

* Только спотовые пары MEXC; деривативы и Twitter-фичи **не входят**.
* Открытие сделок — через Market-ордера; продвинутый риск-менеджер добавим позже.
* Нет внешнего бэкапа (S3); данные лежат локально `/data`.

---

### 11. Дальнейшие шаги (после MVP)

1. **Модуль бэктеста** (описание уже сделано, интеграция с текущим `FeatureEngine`).
2. Поддержка Gate + OKX через адаптер‐интерфейсы.
3. LightGBM-модель и self-training раз в сутки.
4. S3-архив данных и Auto-Retrain CI.

---

> **Итого:** документ охватывает все блоки необходимого скринера: сбор данных, вычисление метрик, логистическую модель, Telegram-бот, хранение, деплой и приёмку. Готов приступить к детализации кода или оценке сроков.

[1]: https://mexcdevelop.github.io/apidocs/spot_v3_en/?utm_source=chatgpt.com "Introduction – API Document - GitHub Pages"
[2]: https://www.mexc.com/support/articles/17827791522393?utm_source=chatgpt.com "MEXC V3 WebSocket Service Replacement Announcement"
