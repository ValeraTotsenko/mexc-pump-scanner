from typing import Dict
from .features import FeatureVector
from config import get_thresholds


def is_candidate(fv: FeatureVector, cfg: Dict | None = None) -> bool:
    """Check if a feature vector passes metric thresholds."""
    cfg = cfg or get_thresholds()
    return (
        fv.vsr > cfg.get("vsr", 0)
        and fv.pm > cfg.get("pm", 0)
        and fv.obi > cfg.get("obi", 0)
        and fv.spread < cfg.get("spread", float("inf"))
        and fv.listing_age > cfg.get("listing_age_min", 0)
    )
