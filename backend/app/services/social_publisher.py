"""
Social publishing service.

Handles direct posting to Facebook, Instagram, and Google Business Profile,
image asset management for uploads, and post-insight syncing back into the
PostMetric / PostMetricSnapshot tables.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from ..secret_key import current_secret_key

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger("bricopro.publisher")

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# mybusiness.googleapis.com/v4 was deprecated in 2023; use the new posting API.
GBP_POSTING_BASE = "https://mybusinesspostingapi.googleapis.com/v1"
GBP_MYBUSINESS_BASE = "https://mybusiness.googleapis.com/v4"  # kept for legacy reference
GBP_ACCOUNTS_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"

PUBLISH_ASSETS_DIR = Path(os.getenv("PUBLISH_ASSETS_DIR", "/data/publish_assets"))
PUBLISH_ASSET_URL_TTL_SECONDS = int(os.getenv("PUBLISH_ASSET_URL_TTL_SECONDS", str(6 * 60 * 60)))

# ── Asset helpers ─────────────────────────────────────────────────────────────

def _ensure_assets_dir() -> Path:
    PUBLISH_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    return PUBLISH_ASSETS_DIR


def _get_immich_connection(db: "Session") -> tuple[str, str]:
    from ..models import Integration
    i = db.query(Integration).filter(Integration.provider == "immich").first()
    if not i or not i.base_url:
        raise ValueError("Immich not configured")
    try:
        config = json.loads(i.config_json or "{}")
    except Exception:
        config = {}
    api_key = config.get("api_key", "")
    if not api_key:
        raise ValueError("Immich api_key not configured")
    return i.base_url.rstrip("/"), api_key


def fetch_immich_original(asset_id: str, db: "Session") -> tuple[bytes, str]:
    """Download the full-size original of an Immich asset. Returns (bytes, content_type)."""
    base_url, api_key = _get_immich_connection(db)
    r = httpx.get(
        f"{base_url}/api/assets/{asset_id}/original",
        headers={"x-api-key": api_key},
        timeout=60,
        follow_redirects=True,
    )
    r.raise_for_status()
    content_type = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return r.content, content_type


def fetch_immich_preview_jpeg(asset_id: str, db: "Session") -> tuple[bytes, str]:
    """Download an Immich-generated JPEG preview for APIs that require JPEG media."""
    base_url, api_key = _get_immich_connection(db)
    r = httpx.get(
        f"{base_url}/api/assets/{asset_id}/thumbnail",
        params={"size": "preview", "format": "JPEG"},
        headers={"x-api-key": api_key},
        timeout=60,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.content, "image/jpeg"


def _is_jpeg_content_type(content_type: str) -> bool:
    return content_type.split(";")[0].strip().lower() in {"image/jpeg", "image/jpg"}


def save_asset_for_public_serving(asset_bytes: bytes, content_type: str = "image/jpeg") -> tuple[str, Path]:
    """
    Save image bytes to PUBLISH_ASSETS_DIR and return (filename, path).
    The file is served publicly at /media/publish-assets/{filename}.
    """
    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "webp" in content_type:
        ext = "webp"
    filename = f"{uuid.uuid4().hex}.{ext}"
    dest = _ensure_assets_dir() / filename
    dest.write_bytes(asset_bytes)
    return filename, dest


def _signed_publish_asset_path(filename: str) -> str:
    expires = str(int(time.time()) + PUBLISH_ASSET_URL_TTL_SECONDS)
    message = f"{filename}:{expires}".encode("utf-8")
    sig = hmac.new(current_secret_key().encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"/media/publish-assets/{filename}?expires={expires}&sig={sig}"


def cleanup_old_publish_assets(max_age_hours: int = 24) -> None:
    """Delete temp publish assets older than max_age_hours."""
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_hours * 3600
    try:
        for f in _ensure_assets_dir().iterdir():
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception as exc:
        log.warning("cleanup_old_publish_assets error: %s", exc)


# ── Meta helpers ──────────────────────────────────────────────────────────────

def _get_meta_token(db: "Session") -> str:
    from ..models import Integration
    intg = db.query(Integration).filter(Integration.provider == "meta").first()
    if not intg or not intg.oauth_access_token:
        raise ValueError("Meta not connected. Connect via Settings → Integrations.")
    return intg.oauth_access_token


def _get_pages(user_token: str) -> list[dict]:
    """Return list of {id, name, access_token, ig_user_id} for all managed pages."""
    r = httpx.get(
        f"{GRAPH_API_BASE}/me/accounts",
        params={"access_token": user_token, "fields": "id,name,access_token,instagram_business_account"},
        timeout=15,
    )
    r.raise_for_status()
    pages = []
    for p in r.json().get("data", []):
        ig = p.get("instagram_business_account")
        ig_id = (ig.get("id") if isinstance(ig, dict) else ig) if ig else None
        pages.append({
            "id": p["id"],
            "name": p.get("name", ""),
            "access_token": p.get("access_token", ""),
            "ig_user_id": ig_id,
            "type": "facebook_page",
        })
    return pages


def _page_token_for(user_token: str, page_id: str) -> str:
    pages = _get_pages(user_token)
    for p in pages:
        if p["id"] == page_id:
            return p["access_token"]
    raise ValueError(f"Page {page_id} not found in connected accounts")


# ── Facebook posting ──────────────────────────────────────────────────────────

def post_to_facebook(
    page_id: str,
    message: str,
    image_ids: list[str],
    db: "Session",
    user_token: str,
) -> str:
    """
    Publish a post to a Facebook Page. Returns the platform post ID.
    If image_ids is non-empty, images are uploaded first as unpublished photos
    then attached to the feed post.
    """
    page_token = _page_token_for(user_token, page_id)

    if not image_ids:
        r = httpx.post(
            f"{GRAPH_API_BASE}/{page_id}/feed",
            params={"access_token": page_token},
            json={"message": message},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["id"]

    # Upload each image as an unpublished photo via multipart form (source field).
    # httpx requires files= for the binary part and data= for the form fields;
    # using content= and data= together silently drops the image bytes.
    photo_ids: list[str] = []
    for asset_id in image_ids:
        try:
            img_bytes, img_content_type = fetch_immich_original(asset_id, db)
        except Exception as exc:
            log.warning("Could not fetch Immich asset %s: %s", asset_id, exc)
            continue
        try:
            upload_r = httpx.post(
                f"{GRAPH_API_BASE}/{page_id}/photos",
                params={"access_token": page_token},
                files={"source": ("photo.jpg", img_bytes, img_content_type)},
                data={"published": "false"},
                timeout=60,
            )
        except Exception as exc:
            log.warning("FB photo upload request error for asset %s: %s", asset_id, exc)
            continue
        if upload_r.is_success:
            photo_ids.append(upload_r.json()["id"])
        else:
            log.warning(
                "FB photo upload failed for asset %s: status=%s body=%s",
                asset_id, upload_r.status_code, upload_r.text[:300],
            )

    attached = [{"media_fbid": pid} for pid in photo_ids]
    body: dict = {"message": message}
    if attached:
        body["attached_media"] = json.dumps(attached)

    r = httpx.post(
        f"{GRAPH_API_BASE}/{page_id}/feed",
        params={"access_token": page_token},
        data=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


# ── Instagram posting ─────────────────────────────────────────────────────────

def _get_instagram_token(db: "Session") -> str | None:
    """Return the Instagram User Access Token if connected, else None."""
    from ..models import Integration
    intg = db.query(Integration).filter(Integration.provider == "instagram").first()
    if intg and intg.oauth_access_token:
        return intg.oauth_access_token
    return None


def _instagram_post(base: str, ig_user_id: str, edge: str, token: str, body: dict, timeout: int = 30) -> httpx.Response:
    """
    POST to the Instagram publishing API using the request shape expected by each auth path.

    Instagram Login uses graph.instagram.com with JSON bodies and Bearer auth.
    The legacy Facebook Page token path is kept form-encoded because that is what
    the Graph API reliably accepts for content publishing.
    """
    url = f"{base}/{ig_user_id}/{edge}"
    if "graph.instagram.com" in base:
        return httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=timeout,
        )

    form_body = {
        key: ("true" if value is True else "false" if value is False else value)
        for key, value in body.items()
    }
    return httpx.post(
        url,
        params={"access_token": token},
        data=form_body,
        timeout=timeout,
    )


def post_to_instagram(
    ig_user_id: str,
    caption: str,
    image_ids: list[str],
    db: "Session",
    page_token: str,
    app_base_url: str,
) -> str:
    """
    Publish a post to an Instagram Business account. Returns the media ID.
    Requires at least one image (Instagram does not support text-only posts).
    For multiple images a carousel is created.

    Token priority:
      1. instagram.oauth_access_token (Instagram User Access Token via graph.instagram.com)
      2. page_token (Facebook Page Access Token via graph.facebook.com) — legacy fallback
    """
    if not image_ids:
        raise ValueError("Instagram requires at least one image.")

    ig_token = _get_instagram_token(db)
    if ig_token:
        base = "https://graph.instagram.com/v21.0"
        token = ig_token
        log.debug("Instagram: using Instagram API token (graph.instagram.com)")
    else:
        base = GRAPH_API_BASE
        token = page_token
        log.debug("Instagram: no Instagram token found, falling back to Meta page token")

    if len(image_ids) == 1:
        public_url = _prepare_public_image(
            image_ids[0], db, app_base_url, instagram_compatible=True
        )
        container_r = _instagram_post(
            base,
            ig_user_id,
            "media",
            token,
            {"image_url": public_url, "caption": caption},
        )
        if not container_r.is_success:
            raise ValueError(
                f"Instagram media container creation failed: {container_r.status_code} {container_r.text[:300]}"
            )
        creation_id = container_r.json()["id"]
    else:
        # Carousel: max 10 items. Instagram Graph API expects form-encoded parameters.
        item_ids: list[str] = []
        last_item_error: str = ""
        for asset_id in image_ids[:10]:
            public_url = _prepare_public_image(
                asset_id, db, app_base_url, instagram_compatible=True
            )
            item_r = _instagram_post(
                base,
                ig_user_id,
                "media",
                token,
                {"image_url": public_url, "is_carousel_item": True},
            )
            if item_r.is_success:
                item_ids.append(item_r.json()["id"])
            else:
                last_item_error = f"HTTP {item_r.status_code}: {item_r.text[:300]}"
                log.warning(
                    "IG carousel item failed for %s: %s",
                    asset_id, last_item_error,
                )
        if not item_ids:
            raise ValueError(
                f"No Instagram carousel items could be uploaded. "
                f"Instagram API error — {last_item_error}"
            )
        carousel_r = _instagram_post(
            base,
            ig_user_id,
            "media",
            token,
            {"media_type": "CAROUSEL", "children": ",".join(item_ids), "caption": caption},
        )
        if not carousel_r.is_success:
            raise ValueError(
                f"Instagram carousel container failed: {carousel_r.status_code} {carousel_r.text[:300]}"
            )
        creation_id = carousel_r.json()["id"]

    # Publish the container
    pub_r = _instagram_post(
        base,
        ig_user_id,
        "media_publish",
        token,
        {"creation_id": creation_id},
    )
    if not pub_r.is_success:
        raise ValueError(
            f"Instagram media_publish failed: {pub_r.status_code} {pub_r.text[:300]}"
        )
    return pub_r.json()["id"]


def _prepare_public_image(
    asset_id: str,
    db: "Session",
    app_base_url: str,
    *,
    instagram_compatible: bool = False,
) -> str:
    """Download Immich asset, save to publish-assets dir, return public URL."""
    img_bytes, content_type = fetch_immich_original(asset_id, db)
    if instagram_compatible and not _is_jpeg_content_type(content_type):
        log.info(
            "Instagram requires JPEG media; using Immich JPEG preview for asset %s (%s)",
            asset_id, content_type,
        )
        img_bytes, content_type = fetch_immich_preview_jpeg(asset_id, db)
    filename, _ = save_asset_for_public_serving(img_bytes, content_type)
    return f"{app_base_url.rstrip('/')}{_signed_publish_asset_path(filename)}"


# ── Google Business Profile posting ──────────────────────────────────────────

def _get_gbp_token(db: "Session") -> str:
    """Return a valid GBP access token, refreshing if needed."""
    from ..models import Integration
    from .connectors import GoogleBusinessConnector
    intg = db.query(Integration).filter(Integration.provider == "google_business").first()
    if not intg or not intg.oauth_access_token:
        raise ValueError("Google Business not connected. Connect via Settings → Integrations.")
    connector = GoogleBusinessConnector(intg)
    return connector._get_access_token()


def _gbp_api_error(r: "httpx.Response", context: str) -> str:
    """Extract a human-readable error from a failed GBP API response."""
    try:
        body = r.json()
        err = body.get("error", {})
        msg = err.get("message") or err.get("status") or str(body)
    except Exception:
        msg = r.text[:300] or f"HTTP {r.status_code}"
    return f"{context}: {r.status_code} — {msg}"


def _get_gbp_locations(token: str, db: "Session") -> list[dict]:
    """Return list of {name, title, account} for all GBP locations."""
    headers = {"Authorization": f"Bearer {token}"}

    accounts_r = httpx.get(f"{GBP_ACCOUNTS_BASE}/accounts", headers=headers, timeout=15)
    if not accounts_r.is_success:
        raise ValueError(_gbp_api_error(accounts_r, "GBP accounts list failed"))

    accounts = accounts_r.json().get("accounts", [])
    if not accounts:
        raise ValueError(
            "No Google Business accounts found. Ensure your Google account manages at least "
            "one Business Profile location and that your location is verified."
        )

    locations = []
    for acct in accounts:
        acct_name = acct.get("name", "")
        if not acct_name:
            continue
        loc_r = httpx.get(
            f"https://mybusinessinformation.googleapis.com/v1/{acct_name}/locations",
            params={"readMask": "name,title"},
            headers=headers,
            timeout=15,
        )
        if loc_r.is_success:
            for loc in loc_r.json().get("locations", []):
                locations.append({
                    "name": loc.get("name", ""),
                    "title": loc.get("title", ""),
                    "account": acct_name,
                    "type": "gbp_location",
                })
        else:
            log.warning(
                "GBP locations fetch failed for account %s: %s",
                acct_name,
                _gbp_api_error(loc_r, "locations"),
            )

    if not locations:
        raise ValueError(
            "No GBP locations found under your Google Business account(s). "
            "The account may be pending verification or Business Profile access may not yet be granted."
        )

    return locations


def post_to_gbp(
    location_name: str,
    summary: str,
    cta: str,
    image_ids: list[str],
    db: "Session",
    app_base_url: str,
) -> str:
    """
    Publish a Local Post to Google Business Profile. Returns the post resource name.
    Uses mybusinesspostingapi.googleapis.com/v1 (replacement for deprecated v4 endpoint).
    """
    if not location_name or not location_name.startswith("locations/"):
        raise ValueError(
            f"Invalid GBP location name '{location_name}'. Expected format: 'locations/<id>'. "
            "Re-select the account in the publish panel."
        )

    token = _get_gbp_token(db)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    body: dict = {
        "languageCode": "fr",
        "summary": summary,
        "topicType": "STANDARD",
    }

    if cta and cta not in ("", "none"):
        action_type = _cta_to_gbp_action(cta)
        if action_type:
            body["callToAction"] = {"actionType": action_type}

    if image_ids:
        public_url = _prepare_public_image(image_ids[0], db, app_base_url)
        body["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": public_url}]

    r = httpx.post(
        f"{GBP_POSTING_BASE}/{location_name}/localPosts",
        headers=headers,
        json=body,
        timeout=30,
    )
    if not r.is_success:
        raise ValueError(_gbp_api_error(r, "GBP localPost creation failed"))
    return r.json().get("name", "")


def _cta_to_gbp_action(cta: str) -> str:
    mapping = {
        "request_quote": "GET_OFFER",
        "book_spring": "BOOK",
        "book_winter": "BOOK",
        "visit_website": "LEARN_MORE",
        "call_message": "CALL",
        "ask_availability": "GET_OFFER",
        "leave_review": "LEARN_MORE",
        "see_projects": "LEARN_MORE",
    }
    return mapping.get(cta, "LEARN_MORE")


# ── Account discovery ─────────────────────────────────────────────────────────

def _get_instagram_account_from_api(db: "Session") -> dict | None:
    """
    Fetch the user's own Instagram account details via the Instagram API token.
    Returns a publishable account dict or None if not available.
    """
    ig_token = _get_instagram_token(db)
    if not ig_token:
        return None
    try:
        r = httpx.get(
            "https://graph.instagram.com/v21.0/me",
            params={"fields": "id,username,account_type", "access_token": ig_token},
            timeout=10,
        )
        if not r.is_success:
            log.info("Instagram API /me returned %s: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        ig_id = data.get("id")
        username = data.get("username", ig_id)
        if not ig_id:
            return None
        return {
            "provider": "instagram",
            "account_id": ig_id,
            "account_name": f"@{username}" if username else ig_id,
            "type": "instagram",
        }
    except Exception as exc:
        log.info("Instagram API account fetch failed: %s", exc)
        return None


def get_publishable_accounts(db: "Session") -> list[dict]:
    """
    Return all accounts available for publishing:
    - Facebook Pages (from Meta OAuth)
    - Instagram Business accounts (linked to FB pages via Meta, or directly via Instagram API)
    - GBP locations (from Google Business OAuth)

    Instagram account precedence:
      1. If instagram.oauth_access_token is set, expose that account directly.
         The publisher will use graph.instagram.com for posting.
      2. Otherwise fall back to IG accounts discovered through linked Facebook Pages.
    """
    accounts: list[dict] = []

    try:
        user_token = _get_meta_token(db)
        pages = _get_pages(user_token)
        for p in pages:
            accounts.append({
                "provider": "meta",
                "account_id": p["id"],
                "account_name": p["name"],
                "type": "facebook_page",
            })
            if p.get("ig_user_id"):
                accounts.append({
                    "provider": "meta",
                    "account_id": p["ig_user_id"],
                    "account_name": f"{p['name']} (Instagram)",
                    "type": "instagram",
                    "page_id": p["id"],
                })
    except Exception as exc:
        log.info("Meta accounts unavailable: %s", exc)

    # If the Instagram integration has its own OAuth token, prefer that account.
    # Deduplicate by IG user ID so we don't list the same account twice.
    ig_api_account = _get_instagram_account_from_api(db)
    if ig_api_account:
        existing_ig_ids = {a["account_id"] for a in accounts if a.get("type") == "instagram"}
        if ig_api_account["account_id"] not in existing_ig_ids:
            accounts.append(ig_api_account)
        else:
            # Replace the Meta-discovered entry with the direct API one so the
            # publisher uses the Instagram token path instead of the page token.
            accounts = [
                ig_api_account if (a.get("type") == "instagram" and a["account_id"] == ig_api_account["account_id"]) else a
                for a in accounts
            ]

    try:
        token = _get_gbp_token(db)
        locations = _get_gbp_locations(token, db)
        for loc in locations:
            accounts.append({
                "provider": "google_business",
                "account_id": loc["name"],
                "account_name": loc.get("title") or loc["name"],
                "type": "gbp_location",
            })
    except Exception as exc:
        log.info("GBP accounts unavailable: %s", exc)

    return accounts


# ── Insights fetching ─────────────────────────────────────────────────────────

def fetch_facebook_post_insights(post_id: str, page_id: str, db: "Session") -> dict:
    """Fetch engagement metrics for a Facebook Page post."""
    user_token = _get_meta_token(db)
    page_token = _page_token_for(user_token, page_id)
    metrics = "post_impressions,post_impressions_unique,post_clicks,post_engaged_users,post_reactions_by_type_total,post_activity_by_action_type"
    r = httpx.get(
        f"{GRAPH_API_BASE}/{post_id}/insights",
        params={"metric": metrics, "access_token": page_token},
        timeout=15,
    )
    r.raise_for_status()
    data = {item["name"]: (item.get("values") or [{}])[0].get("value", 0) for item in r.json().get("data", [])}

    reactions = data.get("post_reactions_by_type_total", {})
    total_reactions = sum(reactions.values()) if isinstance(reactions, dict) else 0
    activity = data.get("post_activity_by_action_type", {})
    shares = activity.get("share", 0) if isinstance(activity, dict) else 0

    return {
        "impressions": data.get("post_impressions", 0),
        "reach": data.get("post_impressions_unique", 0),
        "clicks": data.get("post_clicks", 0),
        "engagements": data.get("post_engaged_users", 0),
        "reactions": total_reactions,
        "shares": shares,
        "saves": 0,
    }


def fetch_instagram_media_insights(media_id: str, page_id: str, db: "Session") -> dict:
    """Fetch engagement metrics for an Instagram Business media post."""
    ig_token = _get_instagram_token(db)
    if ig_token:
        r = httpx.get(
            f"https://graph.instagram.com/v21.0/{media_id}/insights",
            params={"metric": "impressions,reach,likes,comments,shares,saved,total_interactions", "access_token": ig_token},
            timeout=15,
        )
        r.raise_for_status()
        data = {item["name"]: item.get("values", [{"value": 0}])[0].get("value", 0) for item in r.json().get("data", [])}
        return {
            "impressions": data.get("impressions", 0),
            "reach": data.get("reach", 0),
            "clicks": 0,
            "engagements": data.get("total_interactions", 0),
            "reactions": data.get("likes", 0),
            "shares": data.get("shares", 0),
            "saves": data.get("saved", 0),
        }

    user_token = _get_meta_token(db)
    page_token = _page_token_for(user_token, page_id)
    metrics = "impressions,reach,likes,comments,shares,saved,total_interactions"
    r = httpx.get(
        f"{GRAPH_API_BASE}/{media_id}/insights",
        params={"metric": metrics, "access_token": page_token},
        timeout=15,
    )
    r.raise_for_status()
    data = {item["name"]: item.get("values", [{"value": 0}])[0].get("value", 0) for item in r.json().get("data", [])}
    return {
        "impressions": data.get("impressions", 0),
        "reach": data.get("reach", 0),
        "clicks": 0,
        "engagements": data.get("total_interactions", 0),
        "reactions": data.get("likes", 0),
        "shares": data.get("shares", 0),
        "saves": data.get("saved", 0),
    }


def fetch_gbp_post_insights(local_post_name: str, db: "Session") -> dict:
    """Fetch view/action metrics for a GBP Local Post."""
    token = _get_gbp_token(db)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = httpx.post(
        f"{GBP_POSTING_BASE}/{local_post_name}:reportInsights",
        headers=headers,
        json={"basicRequest": {}},
        timeout=15,
    )
    if not r.is_success:
        log.warning(
            "GBP insights request failed: %s",
            _gbp_api_error(r, "reportInsights"),
        )
        return {"impressions": 0, "reach": 0, "clicks": 0, "engagements": 0, "reactions": 0, "shares": 0, "saves": 0}

    result = r.json()
    metrics = {}
    for item in result.get("localPostMetrics", [{}])[0].get("metricValues", []):
        metrics[item.get("metric", "")] = item.get("totalValue", {}).get("value", 0)

    return {
        "impressions": metrics.get("LOCAL_POST_VIEWS_SEARCH", 0),
        "reach": metrics.get("LOCAL_POST_VIEWS_SEARCH", 0),
        "clicks": metrics.get("LOCAL_POST_ACTIONS_CALL_TO_ACTION", 0),
        "engagements": metrics.get("LOCAL_POST_ACTIONS_CALL_TO_ACTION", 0),
        "reactions": 0,
        "shares": 0,
        "saves": 0,
    }


# ── Core sync function ────────────────────────────────────────────────────────

def sync_post_insights(draft_id: int, db: "Session") -> dict:
    """
    Fetch current platform metrics for a published draft and upsert into
    PostMetric + append a PostMetricSnapshot row.
    Returns the normalized metrics dict.
    """
    from ..models import ContentDraft, PostMetric, PostMetricSnapshot

    draft = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if not draft:
        raise ValueError(f"Draft {draft_id} not found")
    if not draft.platform_post_id:
        raise ValueError(f"Draft {draft_id} has no platform_post_id; publish it first.")

    platform = (draft.platform or "").lower()
    account_id = draft.platform_account_id or ""

    try:
        if platform == "facebook":
            page_id = account_id.split("_")[0] if "_" in account_id else account_id
            metrics = fetch_facebook_post_insights(draft.platform_post_id, page_id, db)
        elif platform == "instagram":
            # account_id for instagram is stored as page_id:ig_user_id
            page_id = account_id.split(":")[0] if ":" in account_id else account_id
            metrics = fetch_instagram_media_insights(draft.platform_post_id, page_id, db)
        elif platform == "gbp":
            metrics = fetch_gbp_post_insights(draft.platform_post_id, db)
        else:
            raise ValueError(f"Insights not supported for platform '{platform}'")
    except Exception as exc:
        log.error("Insights fetch failed for draft %s: %s", draft_id, exc)
        raise

    now = datetime.utcnow()

    # Upsert PostMetric (latest snapshot summary)
    metric = db.query(PostMetric).filter(PostMetric.draft_id == draft_id).first()
    if not metric:
        metric = PostMetric(
            draft_id=draft_id,
            title=draft.title,
            platform=draft.platform,
            post_id=draft.platform_post_id,
            posted_at=draft.published_at.date() if draft.published_at else None,
        )
        db.add(metric)
    metric.impressions = metrics["impressions"]
    metric.reach = metrics["reach"]
    metric.clicks = metrics["clicks"]
    metric.engagements = metrics["engagements"]
    if metric.reach:
        metric.engagement_rate = round(metrics["engagements"] / metric.reach * 100, 2)

    # Append time-series snapshot
    snapshot = PostMetricSnapshot(
        draft_id=draft_id,
        captured_at=now,
        impressions=metrics["impressions"],
        reach=metrics["reach"],
        clicks=metrics["clicks"],
        engagements=metrics["engagements"],
        reactions=metrics["reactions"],
        shares=metrics["shares"],
        saves=metrics["saves"],
    )
    db.add(snapshot)
    db.commit()

    return metrics
