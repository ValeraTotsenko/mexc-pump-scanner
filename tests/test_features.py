import pytest

import scanner.features as features
from scanner.collector import Tick


def test_rolling_window_basic():
    rw = features.RollingWindow(2)
    rw.append(0, 1)
    rw.append(1, 2)
    assert float(rw.sum()) == 3
    assert float(rw.median()) == 1.5
    assert float(rw.max()) == 2
    assert float(rw.oldest()) == 1
    # advance time to trigger trim
    rw.append(3, 3)
    assert float(rw.sum()) == 5
    assert len(rw) == 2


def test_feature_engine_update(monkeypatch):
    class NoTrimWindow(features.RollingWindow):
        def _trim(self, now):
            pass

    monkeypatch.setattr(features, "RollingWindow", NoTrimWindow)

    times = [0]
    monkeypatch.setattr(features.time, "time", lambda: times[0])

    class DummyClient:
        def get_cum_depth(self, symbol):
            return (100, 90)

        def get_best(self, symbol):
            return ((100, 1), (101, 1))

    engine = features.FeatureEngine()
    tick1 = Tick(symbol="ABC", kline={"c": "100", "quoteVol": "10"}, depth={}, ts=0)
    fv1 = engine.update(tick1, DummyClient())
    assert fv1.vsr == 1.0  # only one point -> median equals sum

    times[0] = 1
    tick2 = Tick(symbol="ABC", kline={"c": "110", "quoteVol": "20"}, depth={}, ts=1)
    fv2 = engine.update(tick2, DummyClient())
    assert pytest.approx(fv2.vsr, rel=1e-3) == 2.0
    assert pytest.approx(fv2.pm, rel=1e-3) == 0.03125
    assert fv2.ready is False
