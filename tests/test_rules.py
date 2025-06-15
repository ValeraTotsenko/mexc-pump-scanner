import rules
from features import FeatureVector


def test_is_candidate_pass():
    fv = FeatureVector(
        symbol="ABC",
        vsr=6.0,
        vc=1.0,
        pm=0.05,
        obi=0.3,
        cum_depth_delta=0.0,
        spread=0.01,
        listing_age=1000.0,
        ready=True,
    )
    cfg = {
        "vsr": 5,
        "pm": 0.02,
        "obi": 0.25,
        "spread": 0.015,
        "listing_age_min": 900,
    }
    assert rules.is_candidate(fv, cfg)


def test_is_candidate_fail():
    fv = FeatureVector(
        symbol="ABC",
        vsr=4.0,
        vc=1.0,
        pm=0.01,
        obi=0.1,
        cum_depth_delta=0.0,
        spread=0.02,
        listing_age=1000.0,
        ready=True,
    )
    cfg = {
        "vsr": 5,
        "pm": 0.02,
        "obi": 0.25,
        "spread": 0.015,
        "listing_age_min": 900,
    }
    assert not rules.is_candidate(fv, cfg)
