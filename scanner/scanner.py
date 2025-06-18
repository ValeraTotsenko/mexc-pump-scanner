from typing import AsyncIterator, Dict, Any
import asyncio
import logging
import contextlib
from .collector import MexcWSClient
from .features import FeatureEngine, FeatureVector
from .rules import is_candidate
from .model import load_model
from .volume_scout import VolumeScout
from .sub_manager import SubscriptionManager
import config


logger = logging.getLogger(__name__)


class Scanner:
    """Realtime pump scanner using config-driven thresholds."""

    def __init__(self, symbols: list[str]) -> None:
        self.config = config.load_config()
        self.symbols = list(symbols)
        self.client = MexcWSClient(self.symbols, self.config['mexc']['ws_url'])
        self.engine = FeatureEngine()
        self.model = load_model()
        scout_cfg = self.config.get('scout', {})
        self.scout = VolumeScout(self.config['mexc'].get('rest_url', ''), scout_cfg)
        sub_cfg = self.config.get('subscriptions', {})
        self.sub_manager = SubscriptionManager(
            self.client,
            sub_cfg.get('top_n', 200),
            sub_cfg.get('lru_ttl_sec', 900),
        )
        self.poll_interval = float(sub_cfg.get('poll_interval', 60))
        self._poll_task: asyncio.Task | None = None

    @property
    def thresholds(self) -> Dict[str, Any]:
        return config.get_thresholds()

    async def _poll_loop(self) -> None:
        while True:
            try:
                stats = await self.scout.poll()
                symbols = [s.symbol for s in stats]
                await self.sub_manager.ensure_subscribed(symbols)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - runtime
                logger.error("Volume scout error: %s", exc)
            await asyncio.sleep(self.poll_interval)

    async def run(self) -> AsyncIterator[tuple[FeatureVector, float, float]]:
        logger.info("Scanner starting with %d symbols", len(self.symbols))
        await self.client.connect()
        self._poll_task = asyncio.create_task(self._poll_loop())
        try:
            async for tick in self.client.yield_ticks():
                start_ts = tick.ts
                fv = self.engine.update(tick, self.client)
                if not fv.ready:
                    continue
                if not is_candidate(fv, self.thresholds):
                    continue
                prob = self.model.predict_proba(fv)
                if prob >= self.config['scanner']['prob_threshold']:
                    logger.info(
                        "Signal %s prob %.2f", fv.symbol, prob
                    )
                    yield fv, prob, start_ts
        finally:
            if self._poll_task:
                self._poll_task.cancel()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await self._poll_task

    def reload_thresholds(self) -> None:
        config.reload_config()
        self.config = config.load_config()
        scout_cfg = self.config.get('scout', {})
        self.scout.cfg = scout_cfg
        sub_cfg = self.config.get('subscriptions', {})
        self.poll_interval = float(sub_cfg.get('poll_interval', 60))
