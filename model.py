import json
import math
from pathlib import Path
from typing import Dict

from features import FeatureVector

_MODEL_PATH = Path(__file__).with_name('model.json')


class LogisticModel:
    def __init__(self, intercept: float, coefficients: Dict[str, float]) -> None:
        self.intercept = intercept
        self.coef = coefficients

    def predict_proba(self, fv: FeatureVector) -> float:
        x = self.intercept
        x += fv.vsr * self.coef.get('vsr', 0.0)
        x += fv.pm * self.coef.get('pm', 0.0)
        x += fv.obi * self.coef.get('obi', 0.0)
        return 1.0 / (1.0 + math.exp(-x))


def load_model(path: Path | str | None = None) -> LogisticModel:
    p = Path(path) if path else _MODEL_PATH
    with p.open('r') as f:
        data = json.load(f)
    return LogisticModel(data['intercept'], data['coefficients'])
