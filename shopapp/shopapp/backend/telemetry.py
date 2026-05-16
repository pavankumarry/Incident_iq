import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

# ---------------------------------------------------------------------------
# File-based metric sink
# ---------------------------------------------------------------------------
METRICS_FILE = Path("./telemetry_metrics.jsonl")
_metrics_lock = threading.Lock()


def _write_metric(entry: dict):
    """Append a single metric entry to the JSONL file."""
    entry["timestamp"] = datetime.utcnow().isoformat() + "Z"
    with _metrics_lock:
        with METRICS_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


def read_recent_metrics(n: int = 100) -> list[dict]:
    """Return the last *n* metric entries from the JSONL file."""
    if not METRICS_FILE.exists():
        return []
    with _metrics_lock:
        lines = METRICS_FILE.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries[-n:]


# ---------------------------------------------------------------------------
# OpenTelemetry setup
# ---------------------------------------------------------------------------
resource = Resource.create({"service.name": "shopapp", "service.version": "1.0.0"})

# Tracer
_tracer_provider = TracerProvider(resource=resource)
_tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(_tracer_provider)
tracer = trace.get_tracer("shopapp")

# Meter
_metric_reader = PeriodicExportingMetricReader(
    ConsoleMetricExporter(), export_interval_millis=30_000
)
_meter_provider = MeterProvider(resource=resource, metric_readers=[_metric_reader])
metrics.set_meter_provider(_meter_provider)
meter = metrics.get_meter("shopapp")

# Instruments
request_counter = meter.create_counter(
    "http.server.request_count",
    description="Total number of HTTP requests",
)
latency_histogram = meter.create_histogram(
    "http.server.duration",
    description="HTTP request latency in milliseconds",
    unit="ms",
)
error_counter = meter.create_counter(
    "http.server.error_count",
    description="Total number of HTTP errors (5xx)",
)
active_connections = meter.create_up_down_counter(
    "http.server.active_connections",
    description="Number of active HTTP connections",
)


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------
class TelemetryMiddleware:
    """Lightweight ASGI middleware that records per-request metrics."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        start = time.perf_counter()
        status_code = 500

        active_connections.add(1, {"http.method": method, "http.route": path})

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            labels = {
                "http.method": method,
                "http.route": path,
                "http.status_code": str(status_code),
            }
            request_counter.add(1, labels)
            latency_histogram.record(elapsed_ms, labels)
            if status_code >= 500:
                error_counter.add(1, labels)
            active_connections.add(-1, {"http.method": method, "http.route": path})

            # Write to file for IncidentIQ
            _write_metric(
                {
                    "type": "request",
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": round(elapsed_ms, 2),
                    "is_error": status_code >= 500,
                }
            )
