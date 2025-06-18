import asyncio
import json
from scanner.collector import MexcWSClient

class DummyWS:
    def __init__(self):
        self.sent = []
    async def send(self, msg):
        self.sent.append(json.loads(msg))
    async def recv(self):
        await asyncio.sleep(0)
        return ""

def run(coro):
    return asyncio.run(coro)

async def dummy_reader(self, idx):
    return


def test_stream_limits(monkeypatch):
    conns = []
    async def fake_connect(url):
        ws = DummyWS()
        conns.append(ws)
        return ws
    monkeypatch.setattr(MexcWSClient, "_reader", dummy_reader)
    monkeypatch.setattr("scanner.collector.websockets.connect", fake_connect)
    client = MexcWSClient([f"S{i}" for i in range(31)])
    run(client.connect())
    assert len(client._conns) == 3
    assert all(c <= client.MAX_STREAMS_PER_CONN for c in client._stream_counts)
    assert client.active_streams == 62


def test_subscribe_unsubscribe(monkeypatch):
    conns = []
    async def fake_connect(url):
        ws = DummyWS()
        conns.append(ws)
        return ws
    monkeypatch.setattr(MexcWSClient, "_reader", dummy_reader)
    monkeypatch.setattr("scanner.collector.websockets.connect", fake_connect)
    client = MexcWSClient([])
    run(client.connect())
    for i in range(16):
        run(client.subscribe(f"A{i}"))
    assert len(client._conns) == 2
    assert client._stream_counts == [30, 2]
    run(client.unsubscribe("A0"))
    assert client._stream_counts == [28, 2]
    assert client.active_streams == 30
