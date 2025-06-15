import math
import scanner.model as model
from scanner.features import FeatureVector


def test_logistic_model_predict(monkeypatch):
    monkeypatch.setattr(model, "get_thresholds", lambda: {"vsr": 1, "pm": 1, "obi": 1})
    m = model.load_model("model.json")
    fv = FeatureVector(
        symbol="ABC",
        vsr=5.0,
        pm=0.1,
        obi=0.2,
        cum_depth_delta=0.0,
        spread=0.01,
        listing_age=0.0,
        ready=True,
    )
    p = m.predict_proba(fv)
    x = -1 + 5 * 0.4 + 0.1 * 0.35 + 0.2 * 0.25
    expected = 1 / (1 + math.exp(-x))
    assert abs(p - expected) < 1e-6
