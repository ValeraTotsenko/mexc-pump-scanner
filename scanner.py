from typing import AsyncIterator, Dict, Any
from collector import MexcWSClient
from features import FeatureEngine, FeatureVector
from rules import is_candidate
from model import load_model
from config import load_config, get_thresholds, reload_config


class Scanner:
    """Realtime pump scanner using config-driven thresholds."""

    def __init__(self, symbols: list[str]) -> None:
        self.config = load_config()
        self.client = MexcWSClient(symbols, self.config['mexc']['ws_url'])
        self.engine = FeatureEngine()
        self.model = load_model()

    @property
    def thresholds(self) -> Dict[str, Any]:
        return get_thresholds()

    async def run(self) -> AsyncIterator[tuple[FeatureVector, float, float]]:
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
                yield fv, prob, start_ts

    def reload_thresholds(self) -> None:
        reload_config()
        self.config = load_config()
