import asyncio
import json

import scanner.volume_scout as scout
from scanner.volume_scout import VolumeScout, PairStat
import scanner.sub_manager as sub_manager
from scanner.sub_manager import SubscriptionManager
from scanner.collector import MexcWSClient


class DummyResp:
    def __init__(self, data=None):
        self.data = data or []

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class DummyClientHTTP:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def get(self, url):
        return DummyResp([])


class DummyWS:
    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def recv(self):
        await asyncio.sleep(0)
        return ""


async def dummy_reader(self, idx):
    return


def run(coro):
    return asyncio.run(coro)


def test_rest_rate_limit(monkeypatch):
    monkeypatch.setattr(scout.httpx, "AsyncClient", lambda: DummyClientHTTP())
    times = [0]
    monkeypatch.setattr(scout.time, "time", lambda: times[0])
    vs = VolumeScout("https://api.test", {})

    async def many_polls():
        for _ in range(12):
            await vs.poll()
            times[0] += 5

    run(many_polls())
    rate = vs.request_count / (times[0] / 60)
    assert rate <= 12


def test_stream_count(monkeypatch):
    conns = []

    async def fake_connect(url):
        ws = DummyWS()
        conns.append(ws)
        return ws

    monkeypatch.setattr(MexcWSClient, "_reader", dummy_reader)
    monkeypatch.setattr("scanner.collector.websockets.connect", fake_connect)
    client = MexcWSClient([])
    run(client.connect())
    mgr = SubscriptionManager(client, top_n=500, lru_ttl_sec=10)
    run(mgr.ensure_subscribed([f"P{i}" for i in range(70)]))
    links = len(client._conns)
    assert client.active_streams <= links * client.MAX_STREAMS_PER_CONN
    assert mgr.stream_count == client.active_streams


def test_switch_latency(monkeypatch):
    times = [0]
    monkeypatch.setattr(sub_manager.time, "time", lambda: times[0])

    class StubClient:
        def __init__(self):
            self._symbols = []
            self.subscribed = []

        async def subscribe(self, sym):
            self._symbols.append(sym)
            self.subscribed.append((sym, times[0]))

        async def unsubscribe(self, sym):
            if sym in self._symbols:
                self._symbols.remove(sym)

    client = StubClient()
    mgr = SubscriptionManager(client, top_n=10, lru_ttl_sec=10)
    detected = times[0]
    times[0] += 4
    run(mgr.ensure_subscribed(["AAA"]))
    assert client.subscribed
    latency = client.subscribed[0][1] - detected
    assert latency <= 5


def test_hot_pump_ratio():
    top = [f"S{i}" for i in range(5)]
    pumps = top * 9 + ["X"]
    ratio = sum(1 for p in pumps if p in top) / len(pumps)
    assert ratio >= 0.9
