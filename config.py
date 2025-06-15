import yaml
from typing import Dict, Any
from pathlib import Path

_CONFIG_PATH = Path(__file__).with_name('config.yaml')
_config: Dict[str, Any] = {}


def load_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    global _config
    cfg_path = Path(path) if path else _CONFIG_PATH
    with cfg_path.open('r') as f:
        _config = yaml.safe_load(f)
    return _config


def get_thresholds() -> Dict[str, float]:
    """Return scanner metric thresholds."""
    if not _config:
        load_config()
    return _config.get('scanner', {}).get('metrics', {})


def reload_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Reload configuration at runtime."""
    return load_config(path)
