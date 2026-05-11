"""
In-process background scheduler for Bricopro HQ.

Currently runs a single recurring job: every ``CACHE_TTL_MINUTES`` minutes
walk through all configured integrations and refresh their dashboard cache
row. Opt-in via ``SCHEDULER_ENABLED=true`` so tests don't accidentally fire
the job, and so single-shot CLI usage (``alembic upgrade head``,
``pytest``) doesn't spawn a scheduler thread.

Design notes:

- We use APScheduler's ``BackgroundScheduler``: one daemon thread, no
  Redis/RQ/Celery dependency, exactly matches the "Bricopro HQ runs as a
  single container" deployment.
- Jobs open their own short-lived SQLAlchemy session via ``SessionLocal``;
  they do not hold a session across iterations.
- Failure of one integration must not abort the whole sweep — each
  refresh runs inside a try/except boundary.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Iterable
from datetime import datetime
from datetime import time as time_cls

from apscheduler.schedulers.background import BackgroundScheduler

from .. import db as _db_module
from ..models import ContentDraft, Integration, utc_now
from ..services.refresh import CACHE_TTL_MINUTES, refresh_source


def _session():
    """
    Read SessionLocal dynamically. Tests reload ``app.main`` which calls
    ``_db_reinit()``; importing SessionLocal at module-import time would
    leave the scheduler bound to the previous engine.
    """
    return _db_module.SessionLocal()

log = logging.getLogger("bricopro.scheduler")

# Module-level reference so callers (FastAPI shutdown handler, tests) can
# stop the scheduler. None when not running.
_scheduler: BackgroundScheduler | None = None
_scheduler_lock = threading.Lock()

# Integration providers we treat as candidates for the periodic refresh.
# Matches the SOURCES list in main.py — kept in sync via the integration
# table itself, see refresh_all_integrations.
DEFAULT_SOURCES = (
    "google_calendar",
    "jobber",
    "immich",
    "immich-gpt",
    "paperless",
    "paperless-gpt",
    "meta",
    "google_business",
)


def scheduler_enabled() -> bool:
    return (os.getenv("SCHEDULER_ENABLED") or "").strip().lower() in {"1", "true", "yes"}


def _refresh_interval_minutes() -> int:
    try:
        return max(1, int(os.getenv("SCHEDULER_REFRESH_INTERVAL_MINUTES", str(CACHE_TTL_MINUTES))))
    except ValueError:
        return CACHE_TTL_MINUTES


def _integration_providers(sources: Iterable[str] | None = None) -> list[str]:
    """
    Return the set of providers worth polling: those that have credentials
    configured (``base_url`` set or an OAuth token stored). When the caller
    does not supply an explicit list we read the integrations table so the
    scheduler tracks whatever the user has actually set up.
    """
    if sources is not None:
        return list(sources)

    with _session() as db:
        rows = db.query(Integration).all()
        return [
            r.provider
            for r in rows
            if (r.base_url and r.base_url.strip()) or r.oauth_access_token
        ]


def refresh_all_integrations(sources: Iterable[str] | None = None) -> dict:
    """
    Refresh every configured integration sequentially. Returns a summary
    suitable for logging or surfacing in a manual /scheduler/run endpoint.
    """
    providers = _integration_providers(sources)
    results: dict[str, str] = {}
    for provider in providers:
        try:
            with _session() as db:
                outcome = refresh_source(provider, db)
                results[provider] = outcome["status"]
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Scheduled refresh raised for %s", provider, extra={"provider": provider})
            results[provider] = f"crashed: {exc.__class__.__name__}"
    log.info("Scheduler refresh sweep complete", extra={"results": results})
    return {"providers": providers, "results": results}


def _parse_planned_time(value: str) -> time_cls:
    """Parse "HH:MM" or "HH:MM:SS" planned_time strings; default to noon UTC."""
    if not value:
        return time_cls(12, 0)
    parts = value.split(":")
    try:
        hh = max(0, min(23, int(parts[0])))
        mm = max(0, min(59, int(parts[1]) if len(parts) > 1 else 0))
        return time_cls(hh, mm)
    except (ValueError, IndexError):
        return time_cls(12, 0)


def publish_due_drafts() -> dict:
    """
    Find drafts in status=scheduled whose planned_date/time is in the past
    and try to publish them. Drafts without a planned_date are skipped;
    operators set those manually via the /publish endpoint.
    """
    from ..services.publishing import publish_draft

    results: dict[int, str] = {}
    now = utc_now()

    with _session() as db:
        candidates = (
            db.query(ContentDraft)
            .filter(ContentDraft.status == "scheduled")
            .filter(ContentDraft.planned_date.is_not(None))
            .all()
        )
        due: list[ContentDraft] = []
        for d in candidates:
            planned_at = datetime.combine(d.planned_date, _parse_planned_time(d.planned_time))
            if planned_at <= now:
                due.append(d)

        if not due:
            return {"due_count": 0, "results": {}}

        for d in due:
            try:
                attempt = publish_draft(d, db)
                results[d.id] = attempt.status
            except Exception as exc:  # pragma: no cover - defensive
                log.exception(
                    "Scheduled publish raised",
                    extra={"draft_id": d.id, "platform": d.platform, "error": str(exc)},
                )
                results[d.id] = "crashed"

    log.info("Scheduler publish sweep complete", extra={"results": results})
    return {"due_count": len(results), "results": results}


def refresh_post_metrics() -> dict:
    """Pull insights for every published Meta draft and upsert PostMetric rows."""
    from ..services.kpi import refresh_meta_metrics

    with _session() as db:
        refreshed = refresh_meta_metrics(db)
    return {"refreshed_count": len(refreshed)}


def start_scheduler(*, sources: Iterable[str] | None = None) -> BackgroundScheduler | None:
    """Start the background scheduler if SCHEDULER_ENABLED is set. Idempotent."""
    global _scheduler

    if not scheduler_enabled():
        log.info("Scheduler disabled (set SCHEDULER_ENABLED=true to enable).")
        return None

    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return _scheduler

        interval = _refresh_interval_minutes()
        scheduler = BackgroundScheduler(
            daemon=True,
            timezone="UTC",
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 60},
        )
        scheduler.add_job(
            lambda: refresh_all_integrations(sources=sources),
            "interval",
            minutes=interval,
            id="refresh_all_integrations",
            replace_existing=True,
            next_run_time=None,
        )
        scheduler.add_job(
            publish_due_drafts,
            "interval",
            minutes=1,
            id="publish_due_drafts",
            replace_existing=True,
            next_run_time=None,
        )
        # Pull KPI metrics less frequently — Meta insights are eventually
        # consistent and the API has tight rate limits.
        scheduler.add_job(
            refresh_post_metrics,
            "interval",
            minutes=60,
            id="refresh_post_metrics",
            replace_existing=True,
            next_run_time=None,
        )
        scheduler.start()
        log.info(
            "Background scheduler started",
            extra={"refresh_interval_minutes": interval},
        )
        _scheduler = scheduler
        return scheduler


def stop_scheduler() -> None:
    """Stop the background scheduler if it is running. Idempotent."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            return
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover
            log.exception("Scheduler shutdown raised")
        _scheduler = None


def current_scheduler() -> BackgroundScheduler | None:
    return _scheduler
