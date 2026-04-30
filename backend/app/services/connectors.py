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
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from ..models import Integration

log = logging.getLogger("bricopro.connectors")


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


# ── Google Calendar ───────────────────────────────────────────────────────────

class GoogleCalendarConnector(BaseConnector):
    provider = "google_calendar"

    def fetch(self) -> dict:
        self._require_config()
        # Minimal implementation: list next 5 events from Google Calendar API
        url = "https://www.googleapis.com/calendar/v3/calendars/{cal}/events".format(
            cal=self.config.get("calendar_id", "primary")
        )
        now = datetime.now(timezone.utc).isoformat()
        try:
            r = httpx.get(
                url,
                params={"key": self.api_key, "timeMin": now, "maxResults": 5, "orderBy": "startTime", "singleEvents": "true"},
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
            assets = r.json()
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
            data = r.json()
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


# ── Factory ───────────────────────────────────────────────────────────────────

_CONNECTORS = {
    "google_calendar": GoogleCalendarConnector,
    "jobber": JobberConnector,
    "immich": ImmichConnector,
    "immich-gpt": ImmichGptConnector,
    "paperless": PaperlessConnector,
}


def get_connector(provider: str, db: Session) -> BaseConnector:
    cls = _CONNECTORS.get(provider)
    if not cls:
        raise ConnectorNotConfigured(f"No connector registered for provider '{provider}'")
    integration = db.query(Integration).filter(Integration.provider == provider).first()
    if not integration:
        raise ConnectorNotConfigured(f"Integration row not found for provider '{provider}'")
    return cls(integration)
