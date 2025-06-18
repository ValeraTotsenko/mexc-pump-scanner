import asyncio

import scanner
from scanner.collector import Tick
import scanner.features as features
import config


class FakeClient:
    def __init__(self, ticks):
        self._ticks = ticks

    async def connect(self):
        return None

    async def yield_ticks(self):
        for t in self._ticks:
            _time[0] = t.ts
            await asyncio.sleep(0)
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
    monkeypatch.setattr(scanner.scanner, "MexcWSClient", lambda symbols, ws_url=None: FakeClient(ticks))

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


def test_scanner_dynamic_subscription(monkeypatch):
    cfg = {
        "mexc": {"ws_url": "wss://test", "rest_url": "https://api.test"},
        "scanner": {
            "prob_threshold": 0.0,
            "metrics": {"vsr": 0, "pm": 0, "obi": 0, "spread": 1, "listing_age_min": 0},
        },
        "subscriptions": {"poll_interval": 0.01},
    }
    monkeypatch.setattr(config, "load_config", lambda: cfg)
    monkeypatch.setattr(config, "get_thresholds", lambda: cfg["scanner"]["metrics"])
    monkeypatch.setattr(scanner, "load_config", lambda: cfg)
    monkeypatch.setattr(scanner, "get_thresholds", lambda: cfg["scanner"]["metrics"])

    ticks = [Tick(symbol="AAA", kline={"c": "1", "quoteVol": "1"}, depth={}, ts=0)]
    monkeypatch.setattr(scanner.scanner, "MexcWSClient", lambda symbols, ws_url=None: FakeClient(ticks))

    class DummyScout:
        def __init__(self, *a, **k):
            self.polled = 0

        async def poll(self):
            self.polled += 1
            from scanner.volume_scout import PairStat

            return [PairStat("NEW", 0, 0, 0, 1.0)]

    class DummyManager:
        def __init__(self, *a, **k):
            self.calls = []

        async def ensure_subscribed(self, pairs):
            self.calls.append(list(pairs))

    monkeypatch.setattr(scanner.scanner, "VolumeScout", DummyScout)
    monkeypatch.setattr(scanner.scanner, "SubscriptionManager", DummyManager)

    class NoTrim(features.RollingWindow):
        def _trim(self, now):
            pass

    monkeypatch.setattr(features, "RollingWindow", NoTrim)
    global _time
    _time = [0]
    monkeypatch.setattr(features.time, "time", lambda: _time[0])

    sc = scanner.Scanner(["AAA"])

    async def collect():
        async for _ in sc.run():
            break

    asyncio.run(collect())
    assert sc.sub_manager.calls and sc.sub_manager.calls[0] == ["NEW"]
