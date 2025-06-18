import asyncio
from collections import deque
import scanner.volume_scout as scout


class DummyResp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class DummyClient:
    def __init__(self, data):
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url):
        return DummyResp(self.data)


def test_poll_stats_rank_and_filter(monkeypatch):
    data = [
        {"symbol": "AAA_USDT", "quoteVolume": "1100", "lastPrice": "1.1"},
        {"symbol": "BBB_USDT", "quoteVolume": "700", "lastPrice": "1.9"},
        {"symbol": "CCC_USDT", "quoteVolume": "400", "lastPrice": "1.0"},
        {"symbol": "DDD_USDT", "quoteVolume": "100", "lastPrice": "1.0"},
    ]
    monkeypatch.setattr(scout.httpx, "AsyncClient", lambda: DummyClient(data))
    times = [300]
    monkeypatch.setattr(scout.time, "time", lambda: times[0])
    history = {
        "AAA_USDT": deque([(0, 1000.0, 1.0)]),
        "BBB_USDT": deque([(0, 500.0, 2.0)]),
        "CCC_USDT": deque([(0, 50.0, 1.0)]),
    }
    cfg = {"min_quote_vol_usd": 300, "top_n": 2}
    res = asyncio.run(scout.poll_stats("https://api.test", history, cfg))
    symbols = [p.symbol for p in res]
    assert symbols == ["CCC_USDT", "BBB_USDT"]
    assert res[0].hotness > res[1].hotness


def test_poll_stats_no_history(monkeypatch):
    data = [{"symbol": "AAA_USDT", "quoteVolume": "1000", "lastPrice": "1.0"}]
    monkeypatch.setattr(scout.httpx, "AsyncClient", lambda: DummyClient(data))
    times = [0]
    monkeypatch.setattr(scout.time, "time", lambda: times[0])
    history = {}
    cfg = {"min_quote_vol_usd": 500, "top_n": 1}
    res = asyncio.run(scout.poll_stats("https://api.test", history, cfg))
    ps = res[0]
    assert ps.vol_delta_5m == 0
    assert ps.pm_delta_5m == 0

