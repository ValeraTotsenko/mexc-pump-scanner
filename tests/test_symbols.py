import asyncio
import types
from scanner import symbols

class DummyResp:
    def __init__(self, data):
        self.data = data
        self.status = 200
    async def json(self):
        return self.data
    def raise_for_status(self):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass

class DummySession:
    def __init__(self, data):
        self.data = data
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    def get(self, url):
        return DummyResp(self.data)

def test_fetch_all_pairs(monkeypatch):
    dummy = DummySession({"data": ["AAA_USDT", "BBB_USDT"]})
    monkeypatch.setattr(symbols.aiohttp, "ClientSession", lambda: dummy)
    res = asyncio.run(symbols.fetch_all_pairs("https://api.test"))
    assert res == ["AAA_USDT", "BBB_USDT"]
