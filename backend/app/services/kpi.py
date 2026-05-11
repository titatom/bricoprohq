"""
KPI ingestion: pull engagement metrics for posted drafts from Meta's
Graph API insights endpoint and (best-effort) Google Business Profile
local-post insights, then upsert a ``PostMetric`` row.

The functions here only touch drafts that already have a ``post_id`` —
manual KPI rows (created via ``POST /kpi/records``) are untouched.
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from ..models import ContentDraft, Integration, PostMetric, utc_now
from .publishing import META_GRAPH_BASE

log = logging.getLogger("bricopro.kpi")


_META_PAGE_INSIGHTS = (
    "post_impressions,"
    "post_impressions_unique,"
    "post_clicks,"
    "post_reactions_by_type_total"
)


def _meta_token(db: Session) -> str | None:
    row = db.query(Integration).filter(Integration.provider == "meta").first()
    return row.oauth_access_token if row and row.oauth_access_token else None


def _upsert_metric(db: Session, *, draft: ContentDraft, fields: dict) -> PostMetric:
    """Create or update the PostMetric row keyed by draft_id."""
    metric = db.query(PostMetric).filter(PostMetric.draft_id == draft.id).first()
    if metric is None:
        metric = PostMetric(
            draft_id=draft.id,
            campaign_id=draft.campaign_id,
            title=draft.title,
            platform=draft.platform,
            post_id=draft.post_id,
            post_url=draft.post_url,
            posted_at=draft.published_at.date() if draft.published_at else None,
            created_at=utc_now(),
        )
        db.add(metric)
    for key, value in fields.items():
        setattr(metric, key, value)
    db.commit()
    db.refresh(metric)
    return metric


def refresh_meta_metrics(db: Session) -> list[PostMetric]:
    """
    Pull engagement metrics for every Facebook/Instagram draft with a
    stored ``post_id``. Best-effort: a failing draft is logged but does
    not abort the sweep.
    """
    token = _meta_token(db)
    if not token:
        log.info("KPI refresh skipped: Meta is not connected.")
        return []

    drafts = (
        db.query(ContentDraft)
        .filter(ContentDraft.platform.in_(["facebook", "instagram"]))
        .filter(ContentDraft.post_id != "")
        .all()
    )
    refreshed: list[PostMetric] = []
    for d in drafts:
        try:
            metric = _refresh_one_meta_metric(d, token, db)
            if metric is not None:
                refreshed.append(metric)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "KPI refresh failed for draft",
                extra={"draft_id": d.id, "platform": d.platform, "error": str(exc)},
            )
    return refreshed


def _refresh_one_meta_metric(draft: ContentDraft, token: str, db: Session) -> PostMetric | None:
    if draft.platform == "facebook":
        url = f"{META_GRAPH_BASE}/{draft.post_id}/insights"
        params = {"metric": _META_PAGE_INSIGHTS, "access_token": token}
    else:
        # Instagram media insights — a different metric set.
        url = f"{META_GRAPH_BASE}/{draft.post_id}/insights"
        params = {"metric": "impressions,reach,engagement,saved", "access_token": token}

    try:
        r = httpx.get(url, params=params, timeout=15)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.warning(
            "Meta insights HTTP error",
            extra={
                "draft_id": draft.id,
                "status": exc.response.status_code,
                "body": exc.response.text[:300],
            },
        )
        return None
    except httpx.RequestError as exc:
        log.warning("Meta insights request error", extra={"draft_id": draft.id, "error": str(exc)})
        return None

    payload = r.json()
    data = payload.get("data", []) if isinstance(payload, dict) else []
    fields: dict[str, int] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        values = item.get("values") or []
        if not values or not isinstance(values, list):
            continue
        last = values[-1]
        value = last.get("value") if isinstance(last, dict) else 0
        if isinstance(value, dict):
            # Some metrics (reactions_by_type_total) return a dict — sum it.
            value = sum(v for v in value.values() if isinstance(v, (int, float)))
        if not isinstance(value, (int, float)):
            continue
        if name in ("post_impressions", "impressions"):
            fields["impressions"] = int(value)
        elif name in ("post_impressions_unique", "reach"):
            fields["reach"] = int(value)
        elif name in ("post_clicks",):
            fields["clicks"] = int(value)
        elif name in ("post_reactions_by_type_total", "engagement"):
            fields["engagements"] = int(value)

    if fields.get("impressions"):
        fields["engagement_rate"] = round(
            (fields.get("engagements", 0) / fields["impressions"]) * 100, 2
        )

    if not fields:
        return None
    return _upsert_metric(db, draft=draft, fields=fields)
