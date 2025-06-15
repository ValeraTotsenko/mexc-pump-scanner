import logging
import json
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


class JSONFormatter(logging.Formatter):
    """Simple JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - formatting
        log_record = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def setup_logging() -> None:
    """Configure root logger with rotation and JSON output."""
    logs_dir = Path("data/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        logs_dir / "app.log", when="D", interval=1, backupCount=7
    )
    handler.setFormatter(JSONFormatter())
    console = logging.StreamHandler()
    console.setFormatter(JSONFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler, console])
