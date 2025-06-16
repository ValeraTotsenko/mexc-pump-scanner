import os
import re
import yaml
from typing import Dict, Any
from pathlib import Path

_CONFIG_PATH = Path(__file__).with_name('config.yaml')
_config: Dict[str, Any] = {}


def load_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Load configuration from YAML file using environment variables."""
    global _config
    cfg_path = Path(path) if path else _CONFIG_PATH
    text = cfg_path.read_text()
    text = os.path.expandvars(text)

    def replace_var(match: re.Match) -> str:
        name = match.group(1)
        val = os.getenv(name)
        if val is None:
            raise ValueError(f"Environment variable '{name}' is not set")
        return val

    text = re.sub(r"\$\{([^}]+)\}", replace_var, text)
    _config = yaml.safe_load(text)
    return _config


def get_thresholds() -> Dict[str, float]:
    """Return scanner metric thresholds."""
    if not _config:
        load_config()
    return _config.get('scanner', {}).get('metrics', {})


def reload_config(path: Path | str | None = None) -> Dict[str, Any]:
    """Reload configuration at runtime."""
    return load_config(path)
