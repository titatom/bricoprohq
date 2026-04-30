"""
Integration connectors for Bricopro HQ.

Each connector reads its configuration from the integrations table and
performs a lightweight read-only fetch from the external service.
All connectors return a plain dict suitable for JSON serialisation.
Raise ConnectorNotConfigured when the integration has no base_url / api_key.
Raise ConnectorError for connectivity / auth failures.
"""

import json
import logging
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy.orm import object_session
from sqlalchemy.orm import Session

from ..models import Integration, Setting

log = logging.getLogger("bricopro.connectors")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PROVIDERS = {"google_calendar", "google_business"}
GOOGLE_CANONICAL_PROVIDER = "google_calendar"


class ConnectorNotConfigured(Exception):
    pass


class ConnectorError(Exception):
    pass


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseConnector:
    provider: str

    def __init__(self, integration: Integration):
        self.integration = integration
        self.session = object_session(integration)
        try:
            self.config = json.loads(integration.config_json or "{}")
        except Exception:
            self.config = {}
        self.base_url = (integration.base_url or "").rstrip("/")
        self.api_key = self.config.get("api_key", "")

    def _setting(self, key: str, default: str = "") -> str:
        if not self.session:
            return default
        setting = self.session.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting and setting.value != "" else default

    def _int_setting(self, key: str, default: int) -> int:
        try:
            return max(1, min(50, int(self._setting(key, str(default)))))
        except (TypeError, ValueError):
            return default

    def _require_config(self):
        if not self.base_url:
            raise ConnectorNotConfigured(
                f"{self.provider}: base_url not configured. Set it in Settings."
            )
        if not self.api_key:
            raise ConnectorNotConfigured(
                f"{self.provider}: api_key not configured. Set it in Settings."
            )

    def _require_base_url(self):
        if not self.base_url:
            raise ConnectorNotConfigured(
                f"{self.provider}: base_url not configured. Set it in Settings."
            )

    def fetch(self) -> dict:
        raise NotImplementedError


def _json_or_connector_error(response: httpx.Response, service_name: str):
    try:
        return response.json()
    except ValueError as exc:
        body = response.text.strip()
        snippet = body[:120] if body else "<empty response>"
        raise ConnectorError(f"{service_name} returned a non-JSON response: {snippet}") from exc


def _raise_http_status(exc: httpx.HTTPStatusError, service_name: str):
    status = exc.response.status_code
    path = exc.request.url.path
    if status == 401:
        hint = "authentication rejected; check the API key/auth mode"
    elif status == 404:
        hint = "endpoint not found; check the base URL and service API version"
    else:
        hint = "request failed"
    raise ConnectorError(f"{service_name} HTTP error {status} at {path}: {hint}") from exc


def _google_oauth_config(integration: Integration) -> dict:
    try:
        config = json.loads(integration.config_json or "{}")
    except Exception:
        config = {}
    if config.get("client_id") and config.get("client_secret"):
        return config

    from sqlalchemy.orm import object_session
    session = object_session(integration)
    if not session:
        return config
    canonical = session.query(Integration).filter(
        Integration.provider == GOOGLE_CANONICAL_PROVIDER
    ).first()
    if not canonical:
        return config
    try:
        canonical_config = json.loads(canonical.config_json or "{}")
    except Exception:
        return config
    return {**canonical_config, **config}


def _sync_google_tokens(integration: Integration, token_data: dict) -> None:
    from sqlalchemy.orm import object_session
    session = object_session(integration)
    integrations = [integration]
    if session:
        integrations = session.query(Integration).filter(
            Integration.provider.in_(GOOGLE_PROVIDERS)
        ).all()

    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    for intg in integrations:
        intg.oauth_access_token = token_data["access_token"]
        intg.oauth_token_expires_at = expires_at
        if "refresh_token" in token_data:
            intg.oauth_refresh_token = token_data["refresh_token"]
    if session:
        session.commit()


# ── Google Calendar ───────────────────────────────────────────────────────────

class GoogleCalendarConnector(BaseConnector):
    provider = "google_calendar"

    def _get_access_token(self) -> str:
        """
        Return a valid OAuth access token, refreshing automatically when expired.
        Falls back to a legacy API key for backward compatibility.
        """
        intg = self.integration
        if not intg.oauth_access_token:
            raise ConnectorNotConfigured(
                "google_calendar: not connected via OAuth. "
                "Click 'Connect with Google' in Settings."
            )

        # Refresh if expired (or within 60 s of expiry)
        now = datetime.now(timezone.utc)
        expires_at = intg.oauth_token_expires_at
        if expires_at and expires_at.replace(tzinfo=timezone.utc) <= now + timedelta(seconds=60):
            self._refresh_token()

        return intg.oauth_access_token

    def _refresh_token(self) -> None:
        intg = self.integration
        if not intg.oauth_refresh_token:
            raise ConnectorNotConfigured(
                "google_calendar: access token expired and no refresh token stored. "
                "Reconnect via Settings."
            )
        config = _google_oauth_config(intg)
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        if not client_id or not client_secret:
            raise ConnectorNotConfigured(
                "google_calendar: client_id/client_secret missing for token refresh."
            )
        try:
            resp = httpx.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": intg.oauth_refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            token_data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Google token refresh failed: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Google token refresh request failed: {exc}") from exc

        _sync_google_tokens(intg, token_data)

    def fetch(self) -> dict:
        access_token = self._get_access_token()
        calendar_id = self.config.get("calendar_id", "primary")
        url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
        now = datetime.now(timezone.utc).isoformat()
        try:
            r = httpx.get(
                url,
                params={
                    "timeMin": now,
                    "maxResults": 10,
                    "orderBy": "startTime",
                    "singleEvents": "true",
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if r.status_code == 401:
                # Token may have been revoked; try one refresh then retry
                self._refresh_token()
                r = httpx.get(
                    url,
                    params={
                        "timeMin": now,
                        "maxResults": 10,
                        "orderBy": "startTime",
                        "singleEvents": "true",
                    },
                    headers={"Authorization": f"Bearer {self.integration.oauth_access_token}"},
                    timeout=10,
                )
            r.raise_for_status()
            items = r.json().get("items", [])
            events = [
                {
                    "summary": e.get("summary", "(No title)"),
                    "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                    "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                }
                for e in items
            ]
            return {"upcoming_events": events, "count": len(events)}
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Google Calendar HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Google Calendar request failed: {exc}") from exc


# ── Jobber ────────────────────────────────────────────────────────────────────

class JobberConnector(BaseConnector):
    provider = "jobber"

    def _get_bearer_token(self) -> str:
        """Return OAuth access token if available, otherwise fall back to legacy api_key."""
        if self.integration.oauth_access_token:
            return self.integration.oauth_access_token
        if self.api_key:
            return self.api_key
        raise ConnectorNotConfigured(
            "jobber: not connected via OAuth. Click 'Connect with Jobber' in Settings."
        )

    def fetch(self) -> dict:
        bearer = self._get_bearer_token()
        graphql_url = self.base_url or "https://api.getjobber.com/api/graphql"
        query = """
        query {
          jobs(filter: {status: [ACTIVE, UPCOMING]}, first: 10) {
            nodes {
              title
              jobStatus
              startAt
              client { name }
            }
          }
        }
        """
        try:
            r = httpx.post(
                graphql_url,
                json={"query": query},
                headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            jobs = data.get("data", {}).get("jobs", {}).get("nodes", [])
            return {"upcoming_jobs": jobs, "count": len(jobs)}
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Jobber HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Jobber request failed: {exc}") from exc


# ── Immich ────────────────────────────────────────────────────────────────────

class ImmichConnector(BaseConnector):
    provider = "immich"

    def _fetch_album_assets(self, album_id: str, headers: dict) -> list:
        r = httpx.get(
            f"{self.base_url}/api/albums/{album_id}",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        album = _json_or_connector_error(r, "Immich")
        if isinstance(album, dict):
            return album.get("assets", [])
        return []

    def _fetch_recent_assets(self, limit: int, headers: dict) -> list:
        r = httpx.post(
            f"{self.base_url}/api/search/metadata",
            json={"page": 1, "size": limit},
            headers={**headers, "Content-Type": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        data = _json_or_connector_error(r, "Immich")
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []
        assets = data.get("assets", data)
        if isinstance(assets, list):
            return assets
        if isinstance(assets, dict):
            for key in ("items", "results", "assets"):
                value = assets.get(key)
                if isinstance(value, list):
                    return value
        for key in ("items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return []

    def fetch(self) -> dict:
        self._require_config()
        try:
            headers = {"x-api-key": self.api_key}
            album_id = self._setting("dashboard.immich.album_id", self.config.get("dashboard_album_id", "")).strip()
            limit = self._int_setting("dashboard.immich.limit", 6)
            if album_id:
                assets = self._fetch_album_assets(album_id, headers)
            else:
                assets = self._fetch_recent_assets(limit, headers)
            if not isinstance(assets, list):
                return {"recent_assets": [], "returned": 0, "album_id": album_id}
            recent = [
                {
                    "id": a.get("id"),
                    "filename": a.get("originalFileName") or a.get("originalPath") or "Untitled photo",
                    "type": a.get("type"),
                    "preview_url": f"{self.base_url}/api/assets/{a.get('id')}/thumbnail?size=preview" if a.get("id") else "",
                    "asset_url": f"{self.base_url}/photos/{a.get('id')}" if a.get("id") else self.base_url,
                }
                for a in assets[:limit]
            ]
            return {"recent_assets": recent, "returned": len(assets), "album_id": album_id}
        except httpx.HTTPStatusError as exc:
            _raise_http_status(exc, "Immich")
        except httpx.RequestError as exc:
            raise ConnectorError(f"Immich request failed: {exc}") from exc


class ImmichGptConnector(BaseConnector):
    provider = "immich-gpt"

    def fetch(self) -> dict:
        self._require_config()
        try:
            r = httpx.get(
                f"{self.base_url}/api/queue/summary",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            r.raise_for_status()
            data = _json_or_connector_error(r, "Immich-GPT")
            return {
                "pending_images": data.get("pending_images", data.get("pending", 0)),
                "needs_review": data.get("needs_review", 0),
                "business_photos": data.get("business_photos", 0),
                "personal_photos": data.get("personal_photos", 0),
            }
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Immich-GPT HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Immich-GPT request failed: {exc}") from exc


# ── Paperless ─────────────────────────────────────────────────────────────────

class PaperlessConnector(BaseConnector):
    provider = "paperless"

    def _tag_id_for_name(self, tag_name: str, headers: dict) -> int | None:
        if not tag_name:
            return None
        r = httpx.get(
            f"{self.base_url}/api/tags/",
            params={"page_size": 100, "query": tag_name},
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        data = _json_or_connector_error(r, "Paperless-ngx")
        tags = data if isinstance(data, list) else data.get("results", [])
        if not tags:
            return None
        normalized = tag_name.casefold()
        for tag in tags:
            if str(tag.get("name", "")).casefold() == normalized:
                return tag.get("id")
        return tags[0].get("id")

    def fetch(self) -> dict:
        self._require_config()
        try:
            headers = {"Authorization": f"Token {self.api_key}"}
            tag_name = self._setting("dashboard.paperless.tag", self.config.get("dashboard_tag", "ai-processed")).strip()
            limit = self._int_setting("dashboard.paperless.limit", 5)
            params = {"page_size": limit, "ordering": "-added"}
            if tag_name:
                tag_id = self._tag_id_for_name(tag_name, headers)
                if tag_id is None:
                    return {"recent_documents": [], "count": 0, "tag": tag_name}
                params["tags__id__all"] = tag_id
            r = httpx.get(
                f"{self.base_url}/api/documents/",
                params=params,
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            data = _json_or_connector_error(r, "Paperless-ngx")
            docs = data.get("results", [])
            return {
                "recent_documents": [
                    {
                        "id": d.get("id"),
                        "title": d.get("title") or d.get("original_file_name") or "Untitled document",
                        "added": d.get("added"),
                        "document_url": f"{self.base_url}/documents/{d.get('id')}/details" if d.get("id") else self.base_url,
                    }
                    for d in docs[:limit]
                ],
                "count": data.get("count", 0),
                "tag": tag_name,
            }
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Paperless HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Paperless request failed: {exc}") from exc


class PaperlessGptConnector(BaseConnector):
    provider = "paperless-gpt"

    def _headers(self) -> dict:
        auth_mode = self.config.get("auth_mode", "none").strip().lower()
        if auth_mode in ("", "none"):
            return {"Content-Type": "application/json"}
        if not self.api_key:
            raise ConnectorNotConfigured(
                "paperless-gpt: api_key not configured for selected auth mode. Set it in Settings."
            )
        if auth_mode == "bearer":
            return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if auth_mode == "token":
            return {"Authorization": f"Token {self.api_key}", "Content-Type": "application/json"}
        if auth_mode == "x-api-key":
            return {"x-api-key": self.api_key, "Content-Type": "application/json"}
        raise ConnectorNotConfigured(
            "paperless-gpt: unsupported auth_mode. Use none, bearer, token, or x-api-key."
        )

    def _summarize_documents(self, data) -> dict:
        documents = []
        if isinstance(data, list):
            documents = data
        elif isinstance(data, dict):
            value = data.get("documents", data.get("results", data.get("items", [])))
            if isinstance(value, list):
                documents = value
        pending = len(documents)
        needs_review = 0
        processed = 0
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            status = str(doc.get("status", "")).lower()
            tags = [str(t).lower() for t in doc.get("tags", []) if t]
            if "needs_review" in status or "review" in tags or "paperless-gpt" in tags:
                needs_review += 1
            if status in {"processed", "done", "ready"} or "paperless-gpt-auto" in tags:
                processed += 1
        return {
            "pending_documents": pending,
            "needs_review": needs_review,
            "processed_documents": processed,
        }

    def fetch(self) -> dict:
        self._require_base_url()
        try:
            r = httpx.get(
                f"{self.base_url}/api/documents",
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = _json_or_connector_error(r, "Paperless-GPT")
            if isinstance(data, dict) and any(
                key in data for key in ("pending_documents", "pending", "needs_review", "processed_documents", "processed")
            ):
                return {
                    "pending_documents": data.get("pending_documents", data.get("pending", 0)),
                    "needs_review": data.get("needs_review", 0),
                    "processed_documents": data.get("processed_documents", data.get("processed", 0)),
                }
            return self._summarize_documents(data)
        except httpx.HTTPStatusError as exc:
            _raise_http_status(exc, "Paperless-GPT")
        except httpx.RequestError as exc:
            raise ConnectorError(f"Paperless-GPT request failed: {exc}") from exc


# ── Meta (Facebook + Instagram) ───────────────────────────────────────────────

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class MetaConnector(BaseConnector):
    provider = "meta"

    def _get_access_token(self) -> str:
        if not self.integration.oauth_access_token:
            raise ConnectorNotConfigured(
                "meta: not connected via OAuth. Click 'Connect with Meta' in Settings."
            )
        return self.integration.oauth_access_token

    def fetch(self) -> dict:
        token = self._get_access_token()
        try:
            # Fetch connected pages the user manages
            r = httpx.get(
                f"{GRAPH_API_BASE}/me/accounts",
                params={"access_token": token, "fields": "id,name,fan_count,instagram_business_account"},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            pages = data.get("data", [])
            result: dict = {
                "pages": [
                    {
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "fans": p.get("fan_count", 0),
                        "has_instagram": bool(p.get("instagram_business_account")),
                    }
                    for p in pages
                ],
                "page_count": len(pages),
            }
            # Optionally surface the first Instagram account
            for p in pages:
                ig = p.get("instagram_business_account")
                if ig:
                    ig_id = ig.get("id") if isinstance(ig, dict) else ig
                    ig_r = httpx.get(
                        f"{GRAPH_API_BASE}/{ig_id}",
                        params={"access_token": token, "fields": "id,username,followers_count,media_count"},
                        timeout=10,
                    )
                    if ig_r.is_success:
                        ig_data = ig_r.json()
                        result["instagram"] = {
                            "id": ig_data.get("id"),
                            "username": ig_data.get("username"),
                            "followers": ig_data.get("followers_count", 0),
                            "media_count": ig_data.get("media_count", 0),
                        }
                    break
            return result
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Meta Graph API error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Meta request failed: {exc}") from exc


# ── Google Business Profile ────────────────────────────────────────────────────

GOOGLE_MYBUSINESS_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"
GOOGLE_MYBUSINESS_INFO_BASE = "https://mybusinessinformation.googleapis.com/v1"

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleBusinessConnector(BaseConnector):
    provider = "google_business"

    def _get_access_token(self) -> str:
        intg = self.integration
        if not intg.oauth_access_token:
            raise ConnectorNotConfigured(
                "google_business: not connected via OAuth. Click 'Connect with Google' in Settings."
            )
        now = datetime.now(timezone.utc)
        expires_at = intg.oauth_token_expires_at
        if expires_at and expires_at.replace(tzinfo=timezone.utc) <= now + timedelta(seconds=60):
            self._refresh_token()
        return intg.oauth_access_token

    def _refresh_token(self) -> None:
        intg = self.integration
        if not intg.oauth_refresh_token:
            raise ConnectorNotConfigured(
                "google_business: access token expired and no refresh token. Reconnect via Settings."
            )
        config = _google_oauth_config(intg)
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        if not client_id or not client_secret:
            raise ConnectorNotConfigured(
                "google_business: client_id/client_secret missing for token refresh."
            )
        try:
            resp = httpx.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": intg.oauth_refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            resp.raise_for_status()
            td = resp.json()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Google Business token refresh failed: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Google Business token refresh request failed: {exc}") from exc

        _sync_google_tokens(intg, td)

    def fetch(self) -> dict:
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            # List accounts the user manages
            r = httpx.get(
                f"{GOOGLE_MYBUSINESS_BASE}/accounts",
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            accounts = r.json().get("accounts", [])
            result: dict = {
                "accounts": [
                    {"name": a.get("name"), "accountName": a.get("accountName"), "type": a.get("type")}
                    for a in accounts[:5]
                ],
                "account_count": len(accounts),
            }
            # Fetch locations for the first account
            if accounts:
                acct_name = accounts[0].get("name", "")
                loc_r = httpx.get(
                    f"{GOOGLE_MYBUSINESS_INFO_BASE}/{acct_name}/locations",
                    params={"readMask": "name,title,storefrontAddress,websiteUri"},
                    headers=headers,
                    timeout=10,
                )
                if loc_r.is_success:
                    locs = loc_r.json().get("locations", [])
                    result["locations"] = [
                        {"name": l.get("name"), "title": l.get("title"), "website": l.get("websiteUri", "")}
                        for l in locs[:5]
                    ]
            return result
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Google Business API error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Google Business request failed: {exc}") from exc


# ── Factory ───────────────────────────────────────────────────────────────────

_CONNECTORS = {
    "google_calendar": GoogleCalendarConnector,
    "jobber": JobberConnector,
    "immich": ImmichConnector,
    "immich-gpt": ImmichGptConnector,
    "paperless": PaperlessConnector,
    "paperless-gpt": PaperlessGptConnector,
    "meta": MetaConnector,
    "google_business": GoogleBusinessConnector,
}


def get_connector(provider: str, db: Session) -> BaseConnector:
    cls = _CONNECTORS.get(provider)
    if not cls:
        raise ConnectorNotConfigured(f"No connector registered for provider '{provider}'")
    integration = db.query(Integration).filter(Integration.provider == provider).first()
    if not integration:
        raise ConnectorNotConfigured(f"Integration row not found for provider '{provider}'")
    return cls(integration)
