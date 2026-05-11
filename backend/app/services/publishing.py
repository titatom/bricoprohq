"""
Publishing service: posts a saved ``ContentDraft`` to the configured
platform and records the result in ``PublishAttempt``.

Supported targets:

- ``facebook`` → Facebook Page feed via Graph API ``/{page_id}/feed``
- ``instagram`` → Instagram Business container + publish two-step
- ``gbp`` → Google Business Profile ``localPosts.create``

Every other platform value raises ``PublishingError`` with a clear message
so the UI can show "platform X is not supported by the auto-publisher yet"
without crashing. The service never touches OAuth-less integrations — it
delegates to the existing Meta / Google Business connectors so token
refresh + storage stay in one place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from ..models import ContentDraft, Integration, PublishAttempt, utc_now
from .connectors import ConnectorError, ConnectorNotConfigured

log = logging.getLogger("bricopro.publishing")

META_GRAPH_BASE = "https://graph.facebook.com/v21.0"
GBP_POSTS_BASE = "https://mybusiness.googleapis.com/v4"


class PublishingError(Exception):
    pass


class PublishingNotConfigured(Exception):
    pass


@dataclass
class PublishResult:
    post_id: str
    post_url: str
    raw: dict


# ── Helpers ──────────────────────────────────────────────────────────────────

def _meta_account_id(db: Session) -> str:
    """Return the configured Facebook page id used for posting."""
    from ..models import Setting
    row = db.query(Setting).filter(Setting.key == "social_facebook_account").first()
    if row and row.value:
        return row.value.strip()
    row = db.query(Setting).filter(Setting.key == "social_meta_account_id").first()
    return row.value.strip() if row and row.value else ""


def _ig_account_id(db: Session) -> str:
    from ..models import Setting
    row = db.query(Setting).filter(Setting.key == "social_instagram_account").first()
    return row.value.strip() if row and row.value else ""


def _gbp_account_path(db: Session) -> str:
    """
    Return the Google Business Profile location path used for posting,
    e.g. ``accounts/123/locations/456``.
    """
    from ..models import Setting
    row = db.query(Setting).filter(Setting.key == "social_google_business_account").first()
    return row.value.strip() if row and row.value else ""


def _meta_integration_token(db: Session) -> str:
    row = db.query(Integration).filter(Integration.provider == "meta").first()
    if not row or not row.oauth_access_token:
        raise PublishingNotConfigured(
            "Meta is not connected. Click 'Connect with Meta' in Settings → Integrations."
        )
    return row.oauth_access_token


def _gbp_integration_token(db: Session) -> str:
    from .connectors import GoogleBusinessConnector
    row = db.query(Integration).filter(Integration.provider == "google_business").first()
    if not row:
        raise PublishingNotConfigured(
            "Google Business Profile is not connected. Configure it in Settings → Integrations."
        )
    try:
        return GoogleBusinessConnector(row)._get_access_token()
    except ConnectorNotConfigured as exc:
        raise PublishingNotConfigured(str(exc)) from exc
    except ConnectorError as exc:
        raise PublishingError(str(exc)) from exc


# ── Per-platform publishers ──────────────────────────────────────────────────

def publish_to_facebook(draft: ContentDraft, db: Session) -> PublishResult:
    """Post the draft body to the configured Facebook Page feed."""
    page_id = _meta_account_id(db)
    if not page_id:
        raise PublishingNotConfigured(
            "No Facebook Page configured. Set social.facebook_account in Settings → Social Studio."
        )
    token = _meta_integration_token(db)

    body = draft.body or draft.short_body or draft.title
    if not body.strip():
        raise PublishingError("Draft body is empty — refusing to post a blank message.")

    if draft.hashtags:
        body = f"{body}\n\n{draft.hashtags}".strip()

    try:
        resp = httpx.post(
            f"{META_GRAPH_BASE}/{page_id}/feed",
            data={"message": body, "access_token": token},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise PublishingError(
            f"Meta rejected the post: HTTP {exc.response.status_code} — {exc.response.text[:300]}"
        ) from exc
    except httpx.RequestError as exc:
        raise PublishingError(f"Meta request failed: {exc}") from exc

    payload = resp.json()
    post_id = payload.get("id", "")
    if not post_id:
        raise PublishingError(f"Meta did not return a post id: {payload!r}")
    return PublishResult(
        post_id=post_id,
        post_url=f"https://www.facebook.com/{post_id}",
        raw=payload,
    )


def publish_to_instagram(draft: ContentDraft, db: Session) -> PublishResult:
    """
    Instagram requires a two-step flow: create a media container, then
    publish it. The current implementation requires the draft to reference
    a publicly reachable image URL via the first entry in ``image_ids``
    (Instagram does not accept inline binary uploads).
    """
    ig_account = _ig_account_id(db)
    if not ig_account:
        raise PublishingNotConfigured(
            "No Instagram Business account configured. "
            "Set social.instagram_account in Settings → Social Studio."
        )
    token = _meta_integration_token(db)

    image_ids = [v.strip() for v in (draft.image_ids or "").split(",") if v.strip()]
    if not image_ids:
        raise PublishingError(
            "Instagram publishing requires at least one image_id (publicly reachable URL)."
        )
    image_url = image_ids[0]

    caption_parts = [draft.body or draft.short_body or draft.title, draft.hashtags or ""]
    caption = "\n\n".join(part for part in caption_parts if part).strip()

    try:
        container_resp = httpx.post(
            f"{META_GRAPH_BASE}/{ig_account}/media",
            data={"image_url": image_url, "caption": caption, "access_token": token},
            timeout=30,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json().get("id")
        if not container_id:
            raise PublishingError(f"Instagram container response missing id: {container_resp.text[:300]}")

        publish_resp = httpx.post(
            f"{META_GRAPH_BASE}/{ig_account}/media_publish",
            data={"creation_id": container_id, "access_token": token},
            timeout=30,
        )
        publish_resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise PublishingError(
            f"Instagram rejected the post: HTTP {exc.response.status_code} — {exc.response.text[:300]}"
        ) from exc
    except httpx.RequestError as exc:
        raise PublishingError(f"Instagram request failed: {exc}") from exc

    payload = publish_resp.json()
    media_id = payload.get("id", "")
    if not media_id:
        raise PublishingError(f"Instagram did not return a media id: {payload!r}")
    return PublishResult(
        post_id=media_id,
        post_url=f"https://www.instagram.com/p/{media_id}",
        raw={"container_id": container_id, "media": payload},
    )


def publish_to_gbp(draft: ContentDraft, db: Session) -> PublishResult:
    """Post a Google Business Profile local post."""
    location_path = _gbp_account_path(db)
    if not location_path:
        raise PublishingNotConfigured(
            "No Google Business Profile location configured. "
            "Set social.google_business_account to a value like 'accounts/123/locations/456'."
        )
    token = _gbp_integration_token(db)
    summary = draft.body or draft.short_body or draft.title
    if not summary.strip():
        raise PublishingError("Draft body is empty — refusing to post a blank GBP message.")

    body = {
        "languageCode": "fr" if (draft.language or "").lower() == "fr" else "en",
        "summary": summary,
        "topicType": "STANDARD",
    }
    if draft.cta and draft.cta != "request_quote":
        body["callToAction"] = {"actionType": "LEARN_MORE"}

    try:
        resp = httpx.post(
            f"{GBP_POSTS_BASE}/{location_path}/localPosts",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise PublishingError(
            f"GBP rejected the post: HTTP {exc.response.status_code} — {exc.response.text[:300]}"
        ) from exc
    except httpx.RequestError as exc:
        raise PublishingError(f"GBP request failed: {exc}") from exc

    payload = resp.json()
    name = payload.get("name", "")
    return PublishResult(
        post_id=name,
        post_url=payload.get("searchUrl", ""),
        raw=payload,
    )


# ── Entry point ──────────────────────────────────────────────────────────────

_PUBLISHERS = {
    "facebook": publish_to_facebook,
    "instagram": publish_to_instagram,
    "gbp": publish_to_gbp,
}


def publish_draft(draft: ContentDraft, db: Session) -> PublishAttempt:
    """
    Attempt to publish ``draft`` to the platform encoded in ``draft.platform``.
    Always creates a PublishAttempt row regardless of outcome so the audit
    trail is complete.

    On success the draft's ``status``, ``post_id``, ``post_url``, and
    ``published_at`` fields are updated.
    """
    publisher = _PUBLISHERS.get(draft.platform)
    if publisher is None:
        attempt = PublishAttempt(
            draft_id=draft.id,
            platform=draft.platform,
            status="error",
            error_message=f"Auto-publishing is not supported for platform '{draft.platform}'.",
            completed_at=utc_now(),
        )
        db.add(attempt)
        db.commit()
        return attempt

    attempt = PublishAttempt(
        draft_id=draft.id,
        platform=draft.platform,
        status="in_progress",
        requested_at=utc_now(),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    try:
        result = publisher(draft, db)
    except PublishingNotConfigured as exc:
        attempt.status = "not_configured"
        attempt.error_message = str(exc)
        attempt.completed_at = utc_now()
        db.commit()
        return attempt
    except PublishingError as exc:
        attempt.status = "error"
        attempt.error_message = str(exc)
        attempt.completed_at = utc_now()
        db.commit()
        log.warning(
            "Publish failed",
            extra={"draft_id": draft.id, "platform": draft.platform, "error": str(exc)},
        )
        return attempt
    except Exception as exc:  # pragma: no cover - defensive
        attempt.status = "error"
        attempt.error_message = f"Unexpected publish failure: {exc!r}"
        attempt.completed_at = utc_now()
        db.commit()
        log.exception(
            "Publish raised unexpected exception",
            extra={"draft_id": draft.id, "platform": draft.platform},
        )
        return attempt

    now = utc_now()
    attempt.status = "success"
    attempt.post_id = result.post_id
    attempt.post_url = result.post_url
    attempt.completed_at = now

    draft.status = "posted"
    draft.post_id = result.post_id
    draft.post_url = result.post_url
    draft.published_at = now
    draft.updated_at = now

    db.commit()
    log.info(
        "Draft published",
        extra={
            "draft_id": draft.id,
            "platform": draft.platform,
            "post_id": result.post_id,
        },
    )
    return attempt
