import time
from typing import Dict, List

from .collector import MexcWSClient
from .metrics import ACTIVE_STREAMS


class SubscriptionManager:
    """Manage dynamic subscriptions with LRU eviction."""

    def __init__(self, client: MexcWSClient, top_n: int, lru_ttl_sec: float) -> None:
        self.client = client
        self.top_n = top_n
        self.lru_ttl_sec = lru_ttl_sec
        self.active_pairs: Dict[str, float] = {}
        ACTIVE_STREAMS.set(0)

    async def ensure_subscribed(self, pairs: List[str]) -> None:
        """Subscribe to new pairs and evict stale ones."""
        now = time.time()
        for p in pairs:
            self.active_pairs[p] = now
            if p not in self.client._symbols and hasattr(self.client, "subscribe"):
                await self.client.subscribe(p)
        # remove expired
        for symbol, ts in list(self.active_pairs.items()):
            if now - ts > self.lru_ttl_sec:
                await self.client.unsubscribe(symbol)
                self.active_pairs.pop(symbol, None)
        # evict LRU if over limit
        while len(self.active_pairs) > self.top_n:
            oldest = min(self.active_pairs.items(), key=lambda x: x[1])[0]
            await self.client.unsubscribe(oldest)
            self.active_pairs.pop(oldest, None)
        ACTIVE_STREAMS.set(len(self.active_pairs) * 2)
