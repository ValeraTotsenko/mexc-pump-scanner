import json
import math
from pathlib import Path
from typing import Dict

from features import FeatureVector
from config import get_thresholds

_MODEL_PATH = Path(__file__).with_name('model.json')


class LogisticModel:
    def __init__(self, intercept: float, coefficients: Dict[str, float], thresholds: Dict[str, float]) -> None:
        self.intercept = intercept
        self.coef = coefficients
        self.thresholds = thresholds

    def predict_proba(self, fv: FeatureVector) -> float:
        vsr_norm = fv.vsr / self.thresholds.get('vsr', 1.0)
        pm_norm = fv.pm / self.thresholds.get('pm', 1.0)
        obi_norm = fv.obi / self.thresholds.get('obi', 1.0)

        x = self.intercept
        x += vsr_norm * self.coef.get('vsr', 0.0)
        x += pm_norm * self.coef.get('pm', 0.0)
        x += obi_norm * self.coef.get('obi', 0.0)
        return 1.0 / (1.0 + math.exp(-x))


def load_model(path: Path | str | None = None) -> LogisticModel:
    p = Path(path) if path else _MODEL_PATH
    with p.open('r') as f:
        data = json.load(f)
    thresholds = get_thresholds()
    return LogisticModel(data['intercept'], data['coefficients'], thresholds)
