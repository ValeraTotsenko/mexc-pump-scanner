import time
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Tuple

import httpx


@dataclass
class PairStat:
    """Simple ticker stats for volume scout."""

    symbol: str
    quote_volume: float
    vol_delta_5m: float
    pm_delta_5m: float
    hotness: float


async def poll_stats(rest_url: str, history: Dict[str, Deque[Tuple[float, float, float]]], cfg: Dict) -> List[PairStat]:
    """Fetch 24h stats and compute 5-minute deltas.

    Parameters
    ----------
    rest_url : str
        Base REST endpoint.
    history : dict
        Mapping ``symbol -> deque`` of ``(ts, volume, price)``.
    cfg : dict
        Configuration with ``min_quote_vol_usd`` and ``top_n``.
    """

    url = rest_url.rstrip("/") + "/api/v3/ticker/24hr"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    now = time.time()
    stats: List[PairStat] = []
    for item in data:
        symbol = item.get("symbol") or item.get("s")
        if not symbol:
            continue
        vol = float(
            item.get("quoteVolume")
            or item.get("quote_volume")
            or item.get("q")
            or item.get("volume")
            or item.get("v")
            or 0.0
        )
        price = float(
            item.get("lastPrice")
            or item.get("last")
            or item.get("c")
            or item.get("close")
            or 0.0
        )

        dq = history.setdefault(symbol, deque())
        dq.append((now, vol, price))
        while dq and now - dq[0][0] > 300:
            dq.popleft()

        if len(dq) >= 2:
            vol_delta = vol - dq[0][1]
            prev_price = dq[0][2]
        else:
            vol_delta = 0.0
            prev_price = price

        pm_delta = (price - prev_price) / prev_price if prev_price > 0 else 0.0

        if vol < cfg.get("min_quote_vol_usd", 0):
            continue

        hotness = vol_delta * 1 + pm_delta * 50
        stats.append(PairStat(symbol, vol, vol_delta, pm_delta, hotness))

    stats.sort(key=lambda x: x.hotness, reverse=True)
    top_n = cfg.get("top_n", len(stats))
    return stats[:top_n]
