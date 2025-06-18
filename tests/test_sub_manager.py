import asyncio

import scanner.sub_manager as sub_manager
from scanner.sub_manager import SubscriptionManager


class StubClient:
    def __init__(self):
        self._symbols = []
        self.subscribed = []
        self.unsubscribed = []

    async def subscribe(self, sym: str) -> None:
        self._symbols.append(sym)
        self.subscribed.append(sym)

    async def unsubscribe(self, sym: str) -> None:
        if sym in self._symbols:
            self._symbols.remove(sym)
        self.unsubscribed.append(sym)


def run(coro):
    return asyncio.run(coro)


def test_eviction_lru(monkeypatch):
    times = [0]
    monkeypatch.setattr(sub_manager.time, "time", lambda: times[0])
    client = StubClient()
    mgr = SubscriptionManager(client, top_n=2, lru_ttl_sec=10)

    run(mgr.ensure_subscribed(["AAA"]))
    times[0] = 1
    run(mgr.ensure_subscribed(["BBB"]))
    times[0] = 2
    run(mgr.ensure_subscribed(["CCC"]))

    assert client.subscribed == ["AAA", "BBB", "CCC"]
    assert client.unsubscribed == ["AAA"]
    assert set(mgr.active_pairs) == {"BBB", "CCC"}


def test_eviction_ttl(monkeypatch):
    times = [0]
    monkeypatch.setattr(sub_manager.time, "time", lambda: times[0])
    client = StubClient()
    mgr = SubscriptionManager(client, top_n=10, lru_ttl_sec=5)

    run(mgr.ensure_subscribed(["AAA", "BBB"]))
    times[0] = 6
    run(mgr.ensure_subscribed([]))

    assert set(client.subscribed) == {"AAA", "BBB"}
    assert set(client.unsubscribed) == {"AAA", "BBB"}
    assert not mgr.active_pairs
