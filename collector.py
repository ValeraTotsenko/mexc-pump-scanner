import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, AsyncIterator, Any

import websockets


logger = logging.getLogger(__name__)


@dataclass
class Tick:
    """Combined kline and depth snapshot."""

    symbol: str
    kline: Dict[str, Any]
    depth: Dict[str, Any]


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
        self._tasks: List[asyncio.Task] = []
        self._send_lock = asyncio.Lock()
        self._last_send: Dict[int, float] = {}
        self._kline_cache: Dict[str, Dict[str, Any]] = {}
        self._depth_cache: Dict[str, Dict[str, Any]] = {}

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
        for group in groups:
            ws = await websockets.connect(self._ws_url)
            idx = len(self._conns)
            self._conns.append(ws)
            await self._subscribe_group(idx, group)
            self._tasks.append(asyncio.create_task(self._reader(idx)))

    async def _subscribe_group(self, conn_idx: int, symbols: List[str]) -> None:
        params = []
        for sym in symbols:
            params.append(f"{sym}@kline_1s")
            params.append(f"{sym}@depth.diff")
        msg = {"method": "SUBSCRIPTION", "params": params, "id": conn_idx}
        await self._throttled_send(conn_idx, msg)

    async def subscribe(self, symbol: str) -> None:
        """Subscribe to additional symbol."""
        for idx, ws in enumerate(self._conns):
            current_streams = (len(self._symbols) // len(self._conns)) * 2
            if current_streams < self.MAX_STREAMS_PER_CONN:
                await self._throttled_send(
                    idx,
                    {
                        "method": "SUBSCRIPTION",
                        "params": [f"{symbol}@kline_1s", f"{symbol}@depth.diff"],
                        "id": idx,
                    },
                )
                self._symbols.append(symbol)
                return
        # need new connection
        ws = await websockets.connect(self._ws_url)
        idx = len(self._conns)
        self._conns.append(ws)
        await self._subscribe_group(idx, [symbol])
        self._tasks.append(asyncio.create_task(self._reader(idx)))
        self._symbols.append(symbol)

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe a symbol."""
        if symbol not in self._symbols:
            return
        self._symbols.remove(symbol)
        for idx, ws in enumerate(self._conns):
            await self._throttled_send(
                idx,
                {
                    "method": "UNSUBSCRIPTION",
                    "params": [f"{symbol}@kline_1s", f"{symbol}@depth.diff"],
                    "id": idx,
                },
            )
        self._kline_cache.pop(symbol, None)
        self._depth_cache.pop(symbol, None)

    async def _reader(self, conn_idx: int) -> None:
        ws = self._conns[conn_idx]
        while True:
            try:
                msg = await ws.recv()
            except websockets.ConnectionClosed:
                logger.warning("WS connection %s closed. Reconnecting", conn_idx)
                while True:
                    try:
                        ws = await websockets.connect(self._ws_url)
                        self._conns[conn_idx] = ws
                        await self._subscribe_group(conn_idx, [])
                        break
                    except Exception as exc:  # pragma: no cover - network
                        logger.error("Reconnect failed: %s", exc)
                        await asyncio.sleep(1)
                continue
            except Exception as exc:  # pragma: no cover - network
                logger.error("WebSocket error: %s", exc)
                await asyncio.sleep(1)
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
        elif "depth" in stream:
            symbol = data.get("symbol") or data.get("s")
            self._depth_cache[symbol] = data

    async def yield_ticks(self) -> AsyncIterator[Tick]:
        """Async generator yielding merged ticks."""
        queue: asyncio.Queue[Tick] = asyncio.Queue()

        async def merger() -> None:
            while True:
                await asyncio.sleep(0.001)
                for sym in list(self._kline_cache.keys() & self._depth_cache.keys()):
                    kl = self._kline_cache.pop(sym)
                    dp = self._depth_cache.pop(sym)
                    queue.put_nowait(Tick(symbol=sym, kline=kl, depth=dp))

        merge_task = asyncio.create_task(merger())
        try:
            while True:
                tick = await queue.get()
                yield tick
        finally:
            merge_task.cancel()

