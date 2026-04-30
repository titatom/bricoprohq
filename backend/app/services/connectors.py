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
from sqlalchemy.orm import Session

from ..models import Integration

log = logging.getLogger("bricopro.connectors")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class ConnectorNotConfigured(Exception):
    pass


class ConnectorError(Exception):
    pass


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseConnector:
    provider: str

    def __init__(self, integration: Integration):
        self.integration = integration
        try:
            self.config = json.loads(integration.config_json or "{}")
        except Exception:
            self.config = {}
        self.base_url = (integration.base_url or "").rstrip("/")
        self.api_key = self.config.get("api_key", "")

    def _require_config(self):
        if not self.base_url:
            raise ConnectorNotConfigured(
                f"{self.provider}: base_url not configured. Set it in Settings."
            )
        if not self.api_key:
            raise ConnectorNotConfigured(
                f"{self.provider}: api_key not configured. Set it in Settings."
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
        config = self.config
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

        intg.oauth_access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        intg.oauth_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        # Google may return a new refresh_token in some configurations
        if "refresh_token" in token_data:
            intg.oauth_refresh_token = token_data["refresh_token"]
        # Persist without needing a full db session here — caller must commit if using ORM session
        # The integration object is already bound to a session managed by FastAPI's get_db().
        from sqlalchemy.orm import object_session
        session = object_session(intg)
        if session:
            session.commit()

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

    def fetch(self) -> dict:
        self._require_config()
        try:
            headers = {"x-api-key": self.api_key}
            # Get recent assets count
            r = httpx.get(
                f"{self.base_url}/api/asset",
                params={"take": 10, "skip": 0},
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            assets = _json_or_connector_error(r, "Immich")
            if isinstance(assets, list):
                recent = [{"id": a.get("id"), "filename": a.get("originalFileName"), "type": a.get("type")} for a in assets[:5]]
                return {"recent_assets": recent, "returned": len(assets)}
            return {"recent_assets": [], "returned": 0}
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Immich HTTP error: {exc.response.status_code}") from exc
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

    def fetch(self) -> dict:
        self._require_config()
        try:
            headers = {"Authorization": f"Token {self.api_key}"}
            r = httpx.get(
                f"{self.base_url}/api/documents/",
                params={"page_size": 10, "ordering": "-added"},
                headers=headers,
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            docs = data.get("results", [])
            return {
                "recent_documents": [
                    {"id": d.get("id"), "title": d.get("title"), "added": d.get("added")}
                    for d in docs[:5]
                ],
                "count": data.get("count", 0),
            }
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Paperless HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Paperless request failed: {exc}") from exc


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
        config = self.config
        try:
            resp = httpx.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": config.get("client_id", ""),
                    "client_secret": config.get("client_secret", ""),
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

        intg.oauth_access_token = td["access_token"]
        intg.oauth_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(td.get("expires_in", 3600)))
        if "refresh_token" in td:
            intg.oauth_refresh_token = td["refresh_token"]
        from sqlalchemy.orm import object_session
        session = object_session(intg)
        if session:
            session.commit()

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
