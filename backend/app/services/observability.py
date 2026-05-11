"""
Observability primitives for Bricopro HQ:

- A JSON log formatter that surfaces extra fields (request_id, provider,
  upstream_status, latency_ms, …) so log aggregators can index them.
- A per-request ``contextvar`` that carries the ``request_id`` between the
  middleware that generates it and any log call made inside the handler.
- Prometheus metrics for HTTP traffic and connector calls.
- ``timed_connector_call(provider)`` context manager that records every
  connector call as a counter + latency histogram regardless of where the
  call site lives.

Everything here is safe to import without ``prometheus-client`` configured
to expose anything — the collectors are no-ops until ``/metrics`` is
mounted. Operators opt in via ``METRICS_ENABLED=true``.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

# ── Request ID context ───────────────────────────────────────────────────────

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


def set_request_id(value: str) -> None:
    request_id_var.set(value)


def current_request_id() -> str:
    return request_id_var.get()


def new_request_id() -> str:
    return uuid.uuid4().hex


# ── JSON log formatter ───────────────────────────────────────────────────────

_LOG_RECORD_KEYS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime",
}


class JsonFormatter(logging.Formatter):
    """
    Emit one JSON object per log record. ``extra={...}`` kwargs on log calls
    become top-level fields, which is the whole point — connectors already
    pass ``extra={"provider": …, "upstream_status": …}`` to
    ``log.warning(...)`` and that context is currently dropped by the
    default formatter.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%03d"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = current_request_id()
        if rid:
            payload["request_id"] = rid

        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_KEYS or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """
    Switch the root logger to JSON formatting when ``LOG_FORMAT=json`` is
    set, otherwise keep the existing readable line format. Idempotent so it
    can be called from FastAPI startup without piling up handlers.
    """
    log_format = (os.getenv("LOG_FORMAT") or "").strip().lower()
    if log_format != "json":
        return
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    # Replace existing handlers so the noisy uvicorn/access logger doesn't
    # double-format records once we're in JSON mode.
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


# ── Prometheus collectors ────────────────────────────────────────────────────

registry = CollectorRegistry()

http_requests_total = Counter(
    "bricoprohq_http_requests_total",
    "Total HTTP requests handled by the FastAPI app.",
    labelnames=("method", "path", "status"),
    registry=registry,
)
http_request_duration_seconds = Histogram(
    "bricoprohq_http_request_duration_seconds",
    "Wall-clock latency of HTTP requests.",
    labelnames=("method", "path"),
    registry=registry,
)
connector_calls_total = Counter(
    "bricoprohq_connector_calls_total",
    "Total connector calls by provider and outcome (success/error/not_configured).",
    labelnames=("provider", "outcome"),
    registry=registry,
)
connector_call_duration_seconds = Histogram(
    "bricoprohq_connector_call_duration_seconds",
    "Wall-clock latency of connector calls.",
    labelnames=("provider",),
    registry=registry,
)


def metrics_enabled() -> bool:
    return (os.getenv("METRICS_ENABLED") or "").strip().lower() in {"1", "true", "yes"}


def render_metrics() -> tuple[bytes, str]:
    """Return the Prometheus text exposition payload and content type."""
    return generate_latest(registry), CONTENT_TYPE_LATEST


@contextmanager
def timed_connector_call(provider: str) -> Iterator[None]:
    """
    Measure a connector call and increment the appropriate counter.

    Usage::

        with timed_connector_call("immich"):
            connector.fetch()

    The counter outcome is derived from whether the block raised. Importing
    the connector error types lazily lets us avoid an import cycle (this
    module is imported very early by `app.main`).
    """
    start = time.monotonic()
    outcome = "success"
    try:
        yield
    except Exception as exc:
        from .connectors import ConnectorNotConfigured

        outcome = "not_configured" if isinstance(exc, ConnectorNotConfigured) else "error"
        raise
    finally:
        elapsed = time.monotonic() - start
        connector_calls_total.labels(provider=provider, outcome=outcome).inc()
        connector_call_duration_seconds.labels(provider=provider).observe(elapsed)
