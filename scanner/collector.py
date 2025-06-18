import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, AsyncIterator, Any, Tuple
from collections import deque

from .metrics import WS_RECONNECTS

import websockets


logger = logging.getLogger(__name__)


@dataclass
class Tick:
    """Combined kline and depth snapshot."""

    symbol: str
    kline: Dict[str, Any]
    depth: Dict[str, Any]
    ts: float


class MexcWSClient:
    """Minimal MEXC WebSocket collector.

    Parameters
    ----------
    symbols:
        Trading pairs to subscribe to.
    ws_url:
        Base WebSocket URL.
    """

    MAX_STREAMS_PER_CONN = 30
    MAX_MSG_PER_SEC = 100

    def __init__(self, symbols: List[str], ws_url: str = "wss://wbs.mexc.com/ws"):
        self._symbols = list(dict.fromkeys(symbols))
        self._ws_url = ws_url
        self._conns: List[websockets.WebSocketClientProtocol] = []
        self._stream_counts: List[int] = []
        self._symbol_conn: Dict[str, int] = {}
        self._tasks: List[asyncio.Task] = []
        self._send_lock = asyncio.Lock()
        self._last_send: Dict[int, float] = {}
        self._kline_cache: Dict[str, Dict[str, Any]] = {}
        self._depth_cache: Dict[str, Dict[str, Any]] = {}
        self._order_books: Dict[str, Dict[str, Dict[float, float]]] = {}
        self._volume_window: Dict[str, deque] = {}

    @property
    def active_streams(self) -> int:
        """Total number of active kline/depth streams."""
        return sum(self._stream_counts)

    async def _throttled_send(self, conn_idx: int, msg: dict) -> None:
        async with self._send_lock:
            last = self._last_send.get(conn_idx, 0.0)
            delta = asyncio.get_running_loop().time() - last
            if delta < 1 / self.MAX_MSG_PER_SEC:
                await asyncio.sleep(1 / self.MAX_MSG_PER_SEC - delta)
            await self._conns[conn_idx].send(json.dumps(msg))
            self._last_send[conn_idx] = asyncio.get_running_loop().time()

    async def connect(self) -> None:
        """Open all required sockets and subscribe."""

        groups = [
            self._symbols[i : i + self.MAX_STREAMS_PER_CONN // 2]
            for i in range(0, len(self._symbols), self.MAX_STREAMS_PER_CONN // 2)
        ]
        logger.info("Connecting to %s (%d symbols in %d groups)", self._ws_url, len(self._symbols), len(groups))
        for group in groups:
            ws = await websockets.connect(self._ws_url)
            idx = len(self._conns)
            self._conns.append(ws)
            self._stream_counts.append(len(group) * 2)
            for sym in group:
                self._symbol_conn[sym] = idx
            await self._subscribe_group(idx, group)
            logger.info("WS %d subscribed to %d symbols", idx, len(group))
            self._tasks.append(asyncio.create_task(self._reader(idx)))
        logger.info("All websocket connections established")

    async def _subscribe_group(self, conn_idx: int, symbols: List[str]) -> None:
        params = []
        for sym in symbols:
            params.append(f"{sym}@kline_1s")
            params.append(f"{sym}@depth.diff")
        msg = {"method": "SUBSCRIPTION", "params": params, "id": conn_idx}
        await self._throttled_send(conn_idx, msg)

    async def subscribe(self, symbol: str) -> None:
        """Subscribe to additional symbol."""
        if symbol in self._symbol_conn:
            return
        for idx, _ in enumerate(self._conns):
            if self._stream_counts[idx] + 2 <= self.MAX_STREAMS_PER_CONN:
                logger.info("Subscribing %s on existing WS %d", symbol, idx)
                await self._throttled_send(
                    idx,
                    {
                        "method": "SUBSCRIPTION",
                        "params": [f"{symbol}@kline_1s", f"{symbol}@depth.diff"],
                        "id": idx,
                    },
                )
                self._stream_counts[idx] += 2
                self._symbol_conn[symbol] = idx
                self._symbols.append(symbol)
                return
        logger.info("Opening new WS for %s", symbol)
        ws = await websockets.connect(self._ws_url)
        idx = len(self._conns)
        self._conns.append(ws)
        self._stream_counts.append(2)
        self._symbol_conn[symbol] = idx
        await self._subscribe_group(idx, [symbol])
        logger.info("WS %d subscribed to %s", idx, symbol)
        self._tasks.append(asyncio.create_task(self._reader(idx)))
        self._symbols.append(symbol)

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe a symbol."""
        if symbol not in self._symbols:
            return
        self._symbols.remove(symbol)
        idx = self._symbol_conn.pop(symbol, None)
        if idx is not None:
            logger.info("Unsubscribing %s from WS %d", symbol, idx)
            await self._throttled_send(
                idx,
                {
                    "method": "UNSUBSCRIPTION",
                    "params": [f"{symbol}@kline_1s", f"{symbol}@depth.diff"],
                    "id": idx,
                },
            )
            self._stream_counts[idx] -= 2
        self._kline_cache.pop(symbol, None)
        self._depth_cache.pop(symbol, None)
        self._order_books.pop(symbol, None)
        self._volume_window.pop(symbol, None)

    async def _reader(self, conn_idx: int) -> None:
        ws = self._conns[conn_idx]
        backoff = 1.0
        first = True
        while True:
            try:
                msg = await ws.recv()
                if first:
                    logger.info("WS %d received first message", conn_idx)
                    first = False
                backoff = 1.0
            except websockets.ConnectionClosed:
                logger.warning("WS connection %s closed. Reconnecting", conn_idx)
                WS_RECONNECTS.inc()
                while True:
                    try:
                        await asyncio.sleep(backoff)
                        ws = await websockets.connect(self._ws_url)
                        self._conns[conn_idx] = ws
                        await self._subscribe_group(conn_idx, [])
                        logger.info("WS %d reconnected", conn_idx)
                        first = True
                        backoff = 1.0
                        break
                    except Exception as exc:  # pragma: no cover - network
                        logger.error("Reconnect failed: %s", exc)
                        backoff = min(backoff * 2, 60.0)
                continue
            except Exception as exc:  # pragma: no cover - network
                logger.error("WebSocket error: %s", exc)
                backoff = min(backoff * 2, 60.0)
                await asyncio.sleep(backoff)
                continue
            data = json.loads(msg)
            await self._handle_message(data)

    async def _handle_message(self, msg: dict) -> None:
        stream = msg.get("stream") or msg.get("channel")
        data = msg.get("data") or msg
        if not stream:
            return
        if "kline" in stream:
            symbol = data.get("symbol") or data.get("s")
            self._kline_cache[symbol] = data
            self._update_kline(symbol, data)
            await self._check_quality(symbol)
        elif "depth" in stream:
            symbol = data.get("symbol") or data.get("s")
            self._depth_cache[symbol] = data
            self._update_depth(symbol, data)
            await self._check_quality(symbol)

    async def yield_ticks(self) -> AsyncIterator[Tick]:
        """Async generator yielding merged ticks."""
        queue: asyncio.Queue[Tick] = asyncio.Queue()

        async def merger() -> None:
            while True:
                await asyncio.sleep(0.001)
                for sym in list(self._kline_cache.keys() & self._depth_cache.keys()):
                    kl = self._kline_cache.pop(sym)
                    dp = self._depth_cache.pop(sym)
                    queue.put_nowait(
                        Tick(
                            symbol=sym,
                            kline=kl,
                            depth=dp,
                            ts=asyncio.get_running_loop().time(),
                        )
                    )

        merge_task = asyncio.create_task(merger())
        first = True
        try:
            while True:
                tick = await queue.get()
                if first:
                    logger.info("Data stream started")
                    first = False
                yield tick
        finally:
            merge_task.cancel()

    def _update_depth(self, symbol: str, data: Dict[str, Any]) -> None:
        """Update L10 order book from depth diff message."""
        book = self._order_books.setdefault(symbol, {"bids": {}, "asks": {}})
        bids = data.get("b") or data.get("bids") or []
        asks = data.get("a") or data.get("asks") or []
        for price, qty in bids:
            p, q = float(price), float(qty)
            if q == 0:
                book["bids"].pop(p, None)
            else:
                book["bids"][p] = q
        for price, qty in asks:
            p, q = float(price), float(qty)
            if q == 0:
                book["asks"].pop(p, None)
            else:
                book["asks"][p] = q
        sorted_bids = sorted(book["bids"].items(), key=lambda x: -x[0])
        sorted_asks = sorted(book["asks"].items(), key=lambda x: x[0])
        if sorted_bids and sorted_asks:
            mid = (sorted_bids[0][0] + sorted_asks[0][0]) / 2
            bid_min = mid * 0.999
            ask_max = mid * 1.001
            sorted_bids = [b for b in sorted_bids if b[0] >= bid_min][:10]
            sorted_asks = [a for a in sorted_asks if a[0] <= ask_max][:10]
        book["bids"] = dict(sorted_bids)
        book["asks"] = dict(sorted_asks)

    def _update_kline(self, symbol: str, data: Dict[str, Any]) -> None:
        """Track 5m quote volume using 1s kline updates."""
        vol = float(
            data.get("quoteVol")
            or data.get("q")
            or data.get("quote_volume")
            or data.get("v")
            or 0.0
        )
        dq = self._volume_window.setdefault(symbol, deque())
        now = asyncio.get_running_loop().time()
        dq.append((now, vol))
        while dq and now - dq[0][0] > 300:
            dq.popleft()

    def get_best(self, symbol: str) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        book = self._order_books.get(symbol)
        if not book or not book["bids"] or not book["asks"]:
            return None
        best_bid = max(book["bids"].items(), key=lambda x: x[0])
        best_ask = min(book["asks"].items(), key=lambda x: x[0])
        return best_bid, best_ask

    def get_cum_depth(self, symbol: str) -> Optional[Tuple[float, float]]:
        best = self.get_best(symbol)
        if not best:
            return None
        book = self._order_books[symbol]
        (bid_p, _), (ask_p, _) = best
        mid = (bid_p + ask_p) / 2
        depth_bid = 0.0
        for p, q in sorted(book["bids"].items(), key=lambda x: -x[0]):
            if p < mid * 0.999:
                break
            depth_bid += q
        depth_ask = 0.0
        for p, q in sorted(book["asks"].items(), key=lambda x: x[0]):
            if p > mid * 1.001:
                break
            depth_ask += q
        return depth_bid, depth_ask

    async def _check_quality(self, symbol: str) -> None:
        best = self.get_best(symbol)
        if not best:
            return
        (bid_p, _), (ask_p, _) = best
        spread = (ask_p - bid_p) / ((ask_p + bid_p) / 2)
        volume = sum(v for _, v in self._volume_window.get(symbol, []))
        if spread > 0.015 or volume < 20000:
            logger.info(
                "Dropping %s due to data quality (spread %.4f vol %.1f)",
                symbol,
                spread,
                volume,
            )
            await self.unsubscribe(symbol)

