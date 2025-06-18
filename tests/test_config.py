import os
from pathlib import Path
import config


def test_load_config_defaults(tmp_path, monkeypatch):
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(Path("config.yaml").read_text())

    env = {
        "MEXC_KEY": "k",
        "MEXC_SECRET": "s",
        "TG_TOKEN": "t",
        "ALLOWED_IDS": "1",
        "STAKE_USDT": "100",
        "PROB_THRESHOLD": "0.5",
        "THRESH_VSR": "1",
        "THRESH_PM": "0.1",
        "THRESH_OBI": "0.2",
        "THRESH_SPREAD": "0.01",
        "THRESH_LISTING_AGE": "100",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    cfg = config.load_config(cfg_path)
    assert cfg["scout"]["min_quote_vol_usd"] == 100000
    assert cfg["scout"]["top_n"] == 200
    assert cfg["ws"]["max_streams_per_conn"] == 30
    assert cfg["ws"]["max_msg_per_sec"] == 100
    assert cfg["scanner"]["prob_threshold"] == float(env["PROB_THRESHOLD"])
