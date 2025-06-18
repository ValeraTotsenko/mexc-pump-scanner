from typing import AsyncIterator, Dict, Any
import logging
from .collector import MexcWSClient
from .features import FeatureEngine, FeatureVector
from .rules import is_candidate
from .model import load_model
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

    @property
    def thresholds(self) -> Dict[str, Any]:
        return config.get_thresholds()

    async def run(self) -> AsyncIterator[tuple[FeatureVector, float, float]]:
        logger.info("Scanner starting with %d symbols", len(self.symbols))
        await self.client.connect()
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

    def reload_thresholds(self) -> None:
        config.reload_config()
        self.config = config.load_config()
