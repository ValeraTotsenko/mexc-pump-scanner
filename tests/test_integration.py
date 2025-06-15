import asyncio

import scanner
from collector import Tick
import features
import config


class FakeClient:
    def __init__(self, ticks):
        self._ticks = ticks

    async def connect(self):
        return None

    async def yield_ticks(self):
        for t in self._ticks:
            _time[0] = t.ts
            yield t

    def get_best(self, symbol):
        return ((99.0, 1.0), (100.0, 1.0))

    def get_cum_depth(self, symbol):
        return (100.0, 90.0)


def test_scanner_alert_generation(monkeypatch):
    cfg = {
        "mexc": {"ws_url": "wss://test"},
        "scanner": {
            "prob_threshold": 0.6,
            "metrics": {
                "vsr": 2,
                "pm": 0.02,
                "obi": -1,
                "spread": 0.02,
                "listing_age_min": 0,
            },
        },
    }
    monkeypatch.setattr(config, "load_config", lambda: cfg)
    monkeypatch.setattr(config, "get_thresholds", lambda: cfg["scanner"]["metrics"])
    monkeypatch.setattr(scanner, "load_config", lambda: cfg)
    monkeypatch.setattr(scanner, "get_thresholds", lambda: cfg["scanner"]["metrics"])

    ticks = [
        Tick(symbol="ABC", kline={"c": "100", "quoteVol": "10"}, depth={}, ts=0),
        Tick(symbol="ABC", kline={"c": "101", "quoteVol": "10"}, depth={}, ts=300),
        Tick(symbol="ABC", kline={"c": "150", "quoteVol": "200"}, depth={}, ts=21600),
    ]
    monkeypatch.setattr(scanner, "MexcWSClient", lambda symbols, ws_url=None: FakeClient(ticks))

    class NoTrim(features.RollingWindow):
        def _trim(self, now):
            pass

    monkeypatch.setattr(features, "RollingWindow", NoTrim)
    global _time
    _time = [0]
    monkeypatch.setattr(features.time, "time", lambda: _time[0])

    sc = scanner.Scanner(["ABC"])

    async def collect():
        res = []
        async for fv, prob, ts in sc.run():
            res.append(prob)
            break
        return res

    result = asyncio.run(collect())
    assert result and result[0] > 0.6
