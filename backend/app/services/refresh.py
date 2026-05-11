"""
Shared dashboard refresh logic, callable from both the HTTP endpoint and the
background scheduler.

This module deliberately depends only on the database session, the models,
and the connectors — never on the FastAPI request/response cycle — so the
scheduler can reuse it without spinning up an HTTP client just to refresh
its own data.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import DashboardCache, Integration, utc_now
from .connectors import ConnectorError, ConnectorNotConfigured
from .observability import timed_connector_call

log = logging.getLogger("bricopro.refresh")

CACHE_TTL_MINUTES = 15


def fetch_source(source: str, db: Session) -> tuple[bool, dict]:
    """
    Run a connector and return ``(success, payload)``. Wraps the call in the
    Prometheus connector-call instrumentation so background refreshes stay
    visible on the metrics dashboard.
    """
    try:
        from .connectors import get_connector
        connector = get_connector(source, db)
        with timed_connector_call(source):
            return True, connector.fetch()
    except (ConnectorNotConfigured, ConnectorError) as exc:
        log.warning(
            "Connector failed during refresh",
            extra={
                "provider": source,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return False, {
            "source": source,
            "timestamp": utc_now().isoformat(),
            "error": str(exc),
            "error_type": type(exc).__name__,
        }
    except Exception as exc:  # pragma: no cover - defensive catch-all
        log.exception(
            "Connector raised unexpected exception during refresh",
            extra={"provider": source, "error_type": type(exc).__name__},
        )
        return False, {
            "source": source,
            "timestamp": utc_now().isoformat(),
            "error": str(exc),
            "error_type": type(exc).__name__,
        }


def refresh_source(source: str, db: Session, *, ttl_minutes: int = CACHE_TTL_MINUTES) -> dict:
    """
    Run the connector for ``source``, persist the cache row, and update the
    integration's status / last_sync_at / last_error fields. Returns a small
    summary dict suitable for HTTP and scheduler responses.
    """
    now = utc_now()
    success, data = fetch_source(source, db)
    integration = db.query(Integration).filter(Integration.provider == source).first()

    cache = db.query(DashboardCache).filter(DashboardCache.source == source).first() or DashboardCache(
        source=source, data_json="{}", expires_at=now
    )
    cache.data_json = json.dumps(data)
    cache.synced_at = now
    cache.expires_at = now + timedelta(minutes=ttl_minutes) if success else now
    db.add(cache)

    if integration:
        if success:
            integration.status = "ok"
            integration.last_sync_at = now
            integration.last_error = ""
            integration.last_error_at = None
        else:
            integration.status = "error"
            integration.last_error = (data.get("error") or "")[:1000]
            integration.last_error_at = now

    db.commit()
    return {
        "status": "ok" if success else "error",
        "source": source,
        "error": None if success else data.get("error"),
    }
