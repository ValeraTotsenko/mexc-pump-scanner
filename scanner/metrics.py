from prometheus_client import Histogram, Counter, Gauge, start_http_server
import time
from collections import deque

LATENCY = Histogram(
    "latency_pipeline_ms",
    "Latency from tick to alert in milliseconds",
    buckets=(50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000),
)
WS_RECONNECTS = Counter("ws_reconnects_total", "Number of websocket reconnects")
SIGNALS_TOTAL = Counter("signals_total", "Total number of signals sent")
SIGNALS_PER_HOUR = Gauge("signals_per_hour", "Signals generated in the last hour")

_signal_ts: deque[float] = deque()

_started = False

def start_metrics_server(port: int = 8000) -> None:
    global _started
    if not _started:
        start_http_server(port)
        _started = True


def record_signal() -> None:
    """Update counters and hourly gauge for a new signal."""
    now = time.time()
    _signal_ts.append(now)
    while _signal_ts and now - _signal_ts[0] > 3600:
        _signal_ts.popleft()
    SIGNALS_TOTAL.inc()
    SIGNALS_PER_HOUR.set(len(_signal_ts))

