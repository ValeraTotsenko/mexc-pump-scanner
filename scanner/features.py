import time
from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, Tuple, Optional

import numpy as np

from .collector import MexcWSClient, Tick


class RollingWindow:
    """Time-based rolling window using ``deque`` and NumPy arrays."""

    def __init__(self, size_sec: float) -> None:
        self.size_sec = size_sec
        self._dq: Deque[Tuple[float, np.ndarray]] = deque()

    def append(self, ts: float, value) -> None:
        arr = np.asarray(value, dtype=float)
        self._dq.append((ts, arr))
        self._trim(ts)

    def _trim(self, now: float) -> None:
        while self._dq and now - self._dq[0][0] > self.size_sec:
            self._dq.popleft()

    def values(self) -> np.ndarray:
        if not self._dq:
            return np.empty((0,))
        return np.stack([v for _, v in self._dq], axis=0)

    def sum(self) -> np.ndarray:
        vals = self.values()
        return vals.sum(axis=0) if vals.size else np.zeros(1)

    def median(self) -> np.ndarray:
        vals = self.values()
        return np.median(vals, axis=0) if vals.size else np.zeros(1)

    def max(self) -> np.ndarray:
        vals = self.values()
        return vals.max(axis=0) if vals.size else np.zeros(1)

    def oldest(self) -> Optional[np.ndarray]:
        return self._dq[0][1] if self._dq else None

    def first_timestamp(self) -> Optional[float]:
        return self._dq[0][0] if self._dq else None

    def __len__(self) -> int:
        return len(self._dq)


@dataclass
class FeatureVector:
    symbol: str
    vsr: float
    pm: float
    obi: float
    cum_depth_delta: float
    spread: float
    listing_age: float
    ready: bool


class FeatureEngine:
    """Compute microstructure metrics each second."""

    def __init__(self) -> None:
        self._vol_5m: Dict[str, RollingWindow] = {}
        self._vol_6h: Dict[str, RollingWindow] = {}
        self._price_vol_5m: Dict[str, RollingWindow] = {}
        self._vol1m: Dict[str, RollingWindow] = {}
        self._depth_net: Dict[str, RollingWindow] = {}
        self._first_seen: Dict[str, float] = {}

    def update(self, tick: Tick, client: MexcWSClient) -> FeatureVector:
        now = time.time()
        symbol = tick.symbol
        price = float(
            tick.kline.get("c")
            or tick.kline.get("close")
            or tick.kline.get("p")
            or 0.0
        )
        vol = float(
            tick.kline.get("quoteVol")
            or tick.kline.get("q")
            or tick.kline.get("quote_volume")
            or tick.kline.get("v")
            or 0.0
        )
        self._first_seen.setdefault(symbol, now)

        w5 = self._vol_5m.setdefault(symbol, RollingWindow(300))
        w6h = self._vol_6h.setdefault(symbol, RollingWindow(21600))
        pv5 = self._price_vol_5m.setdefault(symbol, RollingWindow(300))
        vol1 = self._vol1m.setdefault(symbol, RollingWindow(60))
        depth_w = self._depth_net.setdefault(symbol, RollingWindow(180))

        for w in (w5, w6h, vol1):
            w.append(now, vol)
        pv5.append(now, np.array([price * vol, vol]))


        depth = client.get_cum_depth(symbol) or (0.0, 0.0)
        net = depth[0] - depth[1]
        depth_w.append(now, net)
        oldest_net = depth_w.oldest()
        cum_depth_delta = float(net - oldest_net) if oldest_net is not None else 0.0

        vol_5m = float(w5.sum())
        median_6h = float(w6h.median())
        vsr = vol_5m / median_6h if median_6h > 0 else 0.0


        pv_vals = pv5.values()
        if pv_vals.size:
            pv_sum = pv_vals.sum(axis=0)
            vwap = pv_sum[0] / pv_sum[1] if pv_sum[1] > 0 else 0.0
        else:
            vwap = 0.0
        pm = (price - vwap) / vwap if vwap > 0 else 0.0

        best = client.get_best(symbol)
        if best:
            (bid_p, _), (ask_p, _) = best
            spread = (ask_p - bid_p) / ((ask_p + bid_p) / 2)
            obi = (bid_p - ask_p) / (bid_p + ask_p)
        else:
            spread = 0.0
            obi = 0.0

        listing_age = now - self._first_seen[symbol]

        ready = (
            w5.first_timestamp() is not None
            and now - w5.first_timestamp() >= 300
            and w6h.first_timestamp() is not None
            and now - w6h.first_timestamp() >= 21600
            and depth_w.first_timestamp() is not None
            and now - depth_w.first_timestamp() >= 180
        )

        return FeatureVector(
            symbol=symbol,
            vsr=float(vsr),
            pm=float(pm),
            obi=float(obi),
            cum_depth_delta=cum_depth_delta,
            spread=float(spread),
            listing_age=float(listing_age),
            ready=ready,
        )
