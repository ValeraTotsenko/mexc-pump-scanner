from prometheus_client import Histogram, Counter, start_http_server

LATENCY = Histogram(
    "latency_pipeline_ms",
    "Latency from tick to alert in milliseconds",
    buckets=(50, 100, 250, 500, 750, 1000, 1500, 2000, 3000, 5000),
)
WS_RECONNECTS = Counter("ws_reconnects_total", "Number of websocket reconnects")
SIGNALS_TOTAL = Counter("signals_total", "Total number of signals sent")

_started = False

def start_metrics_server(port: int = 8000) -> None:
    global _started
    if not _started:
        start_http_server(port)
        _started = True
