"""
Integration connectors for Bricopro HQ.

Each connector reads its configuration from the integrations table and
performs a lightweight read-only fetch from the external service.
All connectors return a plain dict suitable for JSON serialisation.
Raise ConnectorNotConfigured when the integration has no base_url / api_key.
Raise ConnectorError for connectivity / auth failures.
"""

import html as html_lib
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import object_session
from sqlalchemy.orm import Session

from ..models import Integration, Setting

log = logging.getLogger("bricopro.connectors")

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PROVIDERS = {"google_calendar", "google_business"}
GOOGLE_CANONICAL_PROVIDER = "google_calendar"
JOBBER_GRAPHQL_VERSION = "2025-04-16"


class ConnectorNotConfigured(Exception):
    pass


class ConnectorError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        error_type: str = "connector_error",
        target_url: str = "",
        upstream_status: int | None = None,
        configured_base_url: str = "",
        hint: str = "",
        response_summary: str = "",
        structured: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.target_url = target_url
        self.upstream_status = upstream_status
        self.configured_base_url = configured_base_url
        self.hint = hint
        self.response_summary = response_summary
        self.structured = structured

    def as_detail(self) -> dict:
        detail = {"message": self.message, "type": self.error_type}
        if self.target_url:
            detail["target_url"] = self.target_url
        if self.upstream_status is not None:
            detail["upstream_status"] = self.upstream_status
        if self.configured_base_url:
            detail["configured_base_url"] = self.configured_base_url
        if self.hint:
            detail["hint"] = self.hint
        if self.response_summary:
            detail["response_summary"] = self.response_summary
        return detail


def _normalized_origin(url: str) -> tuple[str, str, int | None, str] | None:
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return None
    if parsed.port is not None:
        port = parsed.port
    elif parsed.scheme.lower() == "https":
        port = 443
    elif parsed.scheme.lower() == "http":
        port = 80
    else:
        port = None
    return (
        parsed.scheme.lower(),
        parsed.hostname.lower(),
        port,
        parsed.path.rstrip("/"),
    )


def validate_paperless_gpt_base_url(base_url: str, app_base_url: str = "") -> None:
    raw_url = (base_url or "").strip()
    if not raw_url:
        return

    normalized = _normalized_origin(raw_url)
    if not normalized:
        raise ConnectorNotConfigured(
            "paperless-gpt: base_url must be a full http(s) URL, for example "
            "http://paperless-gpt.local:8080"
        )

    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ConnectorNotConfigured(
            "paperless-gpt: base_url must start with http:// or https://"
        )
    if parsed.query or parsed.fragment:
        raise ConnectorNotConfigured(
            "paperless-gpt: base_url must not include query strings or fragments."
        )

    _, _, _, path = normalized
    path_lower = path.lower()
    if path_lower == "/api" or path_lower.endswith("/api"):
        raise ConnectorNotConfigured(
            "paperless-gpt: base_url must be the Paperless-GPT service root without '/api'. "
            "Example: http://paperless-gpt.local:8080"
        )
    if "/api/bricoprohq/v1" in path_lower:
        raise ConnectorNotConfigured(
            "paperless-gpt: base_url must be the Paperless-GPT service root, not a "
            "BricoproHQ API endpoint. Remove '/api/bricoprohq/v1' and any endpoint "
            "suffix such as '/health', '/stats', or '/documents'."
        )

    app_base_urls = [value.strip() for value in str(app_base_url or "").split(",") if value.strip()]
    app_origins = [_normalized_origin(value) for value in app_base_urls]
    for app_origin in [origin for origin in app_origins if origin]:
        if normalized[:3] == app_origin[:3] and path in {"", app_origin[3]}:
            raise ConnectorNotConfigured(
                "paperless-gpt: base_url points to this Bricopro HQ app. Enter the Paperless-GPT "
                "service URL instead of APP_BASE_URL. If Paperless-GPT is reverse-proxied on the "
                "same host, use its dedicated path prefix instead of the HQ root URL."
            )


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
        self.base_url = (integration.base_url or "").strip().rstrip("/")
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


def _json_or_connector_error(response: httpx.Response, service_name: str, configured_base_url: str = ""):
    try:
        return response.json()
    except ValueError as exc:
        snippet = _response_snippet(response)
        if _response_is_html(response):
            target = _response_target(response)
            configured = (
                f" Configured base URL: {configured_base_url}."
                if configured_base_url
                else ""
            )
            raise ConnectorError(
                f"{service_name} returned HTML instead of JSON.{configured} "
                f"Target: {target}. This usually means the base URL points to a web app, "
                f"login page, or reverse-proxy error page instead of the {service_name} API. "
                f"Response summary: {snippet}"
            ) from exc
        raise ConnectorError(f"{service_name} returned a non-JSON response: {snippet}") from exc


def _response_is_html(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    body = response.text.lstrip().lower()
    if "html" in content_type:
        return True
    if body.startswith(("<!doctype html", "<html", "<head", "<body", "<title")):
        return True
    return bool(re.match(r"^<[a-z][\w:-]*(\s|>|/>)", body)) and any(
        tag in body[:500] for tag in ("</html", "</head", "</body", "<title")
    )


def _response_target(response: httpx.Response) -> str:
    try:
        return str(response.request.url)
    except RuntimeError:
        return "<unknown>"


def _response_snippet(response: httpx.Response, limit: int = 160) -> str:
    body = response.text.strip()
    if not body:
        return "<empty response>"
    if _response_is_html(response):
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
        if title_match:
            body = title_match.group(1)
        else:
            body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.IGNORECASE | re.DOTALL)
            body = re.sub(r"<[^>]+>", " ", body)
        body = html_lib.unescape(body)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:limit] if body else "<empty response>"


def _raise_http_status(exc: httpx.HTTPStatusError, service_name: str, configured_base_url: str = ""):
    status = exc.response.status_code
    path = exc.request.url.path
    if status == 401:
        hint = "authentication rejected; check credentials"
    elif status == 404:
        hint = "endpoint not found; check the base URL and service API version"
    else:
        hint = "request failed"
    detail = _response_snippet(exc.response)
    target = str(exc.request.url)
    configured = (
        f" Configured base URL: {configured_base_url}."
        if configured_base_url
        else ""
    )
    html_hint = (
        " The response was HTML, so the target is likely a web app, login page, "
        "or reverse-proxy error page instead of the service API."
        if _response_is_html(exc.response)
        else ""
    )
    raise ConnectorError(
        f"{service_name} HTTP error {status} at {path}: {hint}.{configured}{html_hint} "
        f"Target: {target}. Response: {detail}"
    ) from exc


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
        now = datetime.now(timezone.utc)
        # Fetch from start of current week (Monday) through end of next week so
        # the weekly calendar widget can render the full current and next week.
        days_since_monday = now.weekday()  # 0=Mon … 6=Sun
        week_start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week_end = week_start + timedelta(days=14)
        params = {
            "timeMin": week_start.isoformat(),
            "timeMax": week_end.isoformat(),
            "maxResults": 50,
            "orderBy": "startTime",
            "singleEvents": "true",
        }
        try:
            r = httpx.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if r.status_code == 401:
                # Token may have been revoked; try one refresh then retry
                self._refresh_token()
                r = httpx.get(
                    url,
                    params=params,
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
                    "location": e.get("location") or "",
                    "description": e.get("description") or "",
                    "all_day": "date" in e.get("start", {}) and "dateTime" not in e.get("start", {}),
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
        """Return OAuth access token, refreshing automatically if expired."""
        intg = self.integration
        if intg.oauth_access_token:
            now = datetime.now(timezone.utc)
            expires_at = intg.oauth_token_expires_at
            if expires_at and expires_at.replace(tzinfo=timezone.utc) <= now + timedelta(seconds=60):
                self._refresh_token()
            return intg.oauth_access_token
        if self.api_key:
            return self.api_key
        raise ConnectorNotConfigured(
            "jobber: not connected via OAuth. Click 'Connect with Jobber' in Settings."
        )

    def _refresh_token(self) -> None:
        intg = self.integration
        if not intg.oauth_refresh_token:
            raise ConnectorNotConfigured(
                "jobber: access token expired and no refresh token stored. "
                "Reconnect via Settings → Integrations."
            )
        config = self.config
        client_id = config.get("client_id", "")
        client_secret = config.get("client_secret", "")
        if not client_id or not client_secret:
            raise ConnectorNotConfigured(
                "jobber: client_id/client_secret missing for token refresh."
            )
        try:
            resp = httpx.post(
                "https://api.getjobber.com/api/oauth/token",
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
            log.error("Jobber token refresh failed: %s %s", exc.response.status_code, exc.response.text)
            raise ConnectorError(f"Jobber token refresh failed: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Jobber token refresh request failed: {exc}") from exc

        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        intg.oauth_access_token = token_data["access_token"]
        if token_data.get("refresh_token"):
            intg.oauth_refresh_token = token_data["refresh_token"]
        intg.oauth_token_expires_at = expires_at
        session = object_session(intg)
        if session:
            session.commit()
        log.info("Jobber OAuth token refreshed successfully")

    def _post_graphql(self, graphql_url: str, bearer: str, query: str) -> dict:
        try:
            r = httpx.post(
                graphql_url,
                json={"query": query},
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Content-Type": "application/json",
                    "X-JOBBER-GRAPHQL-VERSION": JOBBER_GRAPHQL_VERSION,
                },
                timeout=10,
            )
            if r.status_code == 401:
                log.info("Jobber returned 401, attempting token refresh")
                self._refresh_token()
                r = httpx.post(
                    graphql_url,
                    json={"query": query},
                    headers={
                        "Authorization": f"Bearer {self.integration.oauth_access_token}",
                        "Content-Type": "application/json",
                        "X-JOBBER-GRAPHQL-VERSION": JOBBER_GRAPHQL_VERSION,
                    },
                    timeout=10,
                )
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            _raise_http_status(exc, "Jobber")
        data = _json_or_connector_error(r, "Jobber")
        if data.get("errors"):
            messages = "; ".join(error.get("message", str(error)) for error in data["errors"])
            raise ConnectorError(f"Jobber GraphQL error: {messages}")
        return data.get("data", {})

    def _optional_collection(self, graphql_url: str, bearer: str, query: str, key: str) -> list:
        try:
            data = self._post_graphql(graphql_url, bearer, query)
            return data.get(key, {}).get("nodes", [])
        except Exception as exc:
            log.warning("Jobber optional collection %s failed: %s", key, exc)
            return []

    def _optional_collection_with_fallback(
        self, graphql_url: str, bearer: str, query: str, fallback_query: str, key: str
    ) -> list:
        try:
            data = self._post_graphql(graphql_url, bearer, query)
            return data.get(key, {}).get("nodes", [])
        except Exception as exc:
            log.warning("Jobber optional collection %s failed, retrying simpler query: %s", key, exc)
            return self._optional_collection(graphql_url, bearer, fallback_query, key)

    def _get_job_filter(self) -> str:
        """Read the job status filter setting. Defaults to unscheduled+active jobs."""
        raw = self._setting("dashboard.jobber.job_filter", "upcoming").strip()
        return raw or "upcoming"

    def _get_request_filter(self) -> str:
        raw = self._setting("dashboard.jobber.request_filter", "new").strip()
        return raw or "new"

    def _get_invoice_filter(self) -> str:
        raw = self._setting("dashboard.jobber.invoice_filter", "late,awaiting_payment").strip()
        return raw or "late,awaiting_payment"

    def fetch(self) -> dict:
        bearer = self._get_bearer_token()
        graphql_url = self.base_url or "https://api.getjobber.com/api/graphql"
        limit = self._int_setting("dashboard.jobber.limit", 5)

        job_filter = self._get_job_filter()
        request_filter = self._get_request_filter()
        invoice_filter = self._get_invoice_filter()

        job_status_filter = ""
        if job_filter == "upcoming":
            job_status_filter = ', filter: {status: active}'
        elif job_filter == "unscheduled":
            job_status_filter = ', filter: {status: active}'
        elif job_filter == "archived":
            job_status_filter = ', filter: {status: archived}'
        elif job_filter == "late":
            job_status_filter = ', filter: {status: late}'

        jobs_query = f"""
        query {{
          jobs(first: {limit}{job_status_filter}) {{
            nodes {{
              id
              title
              jobNumber
              jobStatus
              jobberWebUri
              startAt
              client {{ name }}
            }}
          }}
        }}
        """
        try:
            data = self._post_graphql(graphql_url, bearer, jobs_query)
            jobs = data.get("jobs", {}).get("nodes", [])

            requests_query = f"""
            query {{
              requests(first: {limit}) {{
                nodes {{
                  title
                  requestStatus
                  jobberWebUri
                  createdAt
                  client {{ name }}
                }}
              }}
            }}
            """
            quotes_query = f"""
            query {{
              quotes(first: {limit}) {{
                nodes {{
                  title
                  quoteStatus
                  jobberWebUri
                  createdAt
                  client {{ name }}
                }}
              }}
            }}
            """
            invoices_query = f"""
            query {{
              invoices(first: {limit}) {{
                nodes {{
                  invoiceNumber
                  subject
                  invoiceStatus
                  jobberWebUri
                  amounts {{
                    balance
                    total
                  }}
                  dueDate
                  client {{ name }}
                }}
              }}
            }}
            """
            fallback_invoices_query = f"""
            query {{
              invoices(first: {limit}) {{
                nodes {{
                  invoiceNumber
                  subject
                  invoiceStatus
                  jobberWebUri
                  dueDate
                  client {{ name }}
                }}
              }}
            }}
            """
            requests = self._optional_collection(graphql_url, bearer, requests_query, "requests")
            quotes = self._optional_collection(graphql_url, bearer, quotes_query, "quotes")
            invoices = self._optional_collection_with_fallback(
                graphql_url, bearer, invoices_query, fallback_invoices_query, "invoices"
            )

            return {
                "upcoming_jobs": jobs,
                "pending_requests": requests,
                "pending_quotes": quotes,
                "pending_invoices": invoices,
                "count": len(jobs),
                "requests_count": len(requests),
                "quotes_count": len(quotes),
                "invoices_count": len(invoices),
                "limit": limit,
                "job_filter": job_filter,
                "request_filter": request_filter,
                "invoice_filter": invoice_filter,
            }
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"Jobber HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise ConnectorError(f"Jobber request failed: {exc}") from exc

    def fetch_stats(self) -> dict:
        """Fetch summary stats for the dashboard header independently from card limits."""
        bearer = self._get_bearer_token()
        graphql_url = self.base_url or "https://api.getjobber.com/api/graphql"

        upcoming_jobs_query = """
        query {
          jobs(first: 50, filter: {status: active}) {
            nodes { id jobStatus startAt }
          }
        }
        """
        requests_query = """
        query {
          requests(first: 50) {
            nodes { id requestStatus }
          }
        }
        """
        invoices_query = """
        query {
          invoices(first: 50) {
            nodes { id invoiceStatus }
          }
        }
        """

        stats = {
            "upcoming_unscheduled_count": 0,
            "action_required_count": 0,
            "new_requests_count": 0,
            "pending_invoice_count": 0,
            "jobs_by_status": {"coming_up": 0, "action_required": 0, "requires_invoicing": 0},
            "requests_by_status": {"new": 0, "pending": 0},
            "invoices_by_status": {"late": 0, "awaiting_payment": 0, "sent": 0},
        }

        try:
            jobs_data = self._post_graphql(graphql_url, bearer, upcoming_jobs_query)
            all_jobs = jobs_data.get("jobs", {}).get("nodes", [])
            coming_up = [
                j for j in all_jobs
                if not j.get("startAt") or (j.get("jobStatus") or "").lower() in ("upcoming", "today", "active")
            ]
            action_required = [j for j in all_jobs if (j.get("jobStatus") or "").lower() == "action_required"]
            requires_invoicing = [j for j in all_jobs if (j.get("jobStatus") or "").lower() == "requires_invoicing"]
            stats["upcoming_unscheduled_count"] = len(coming_up)
            stats["action_required_count"] = len(action_required) + len(requires_invoicing)
            stats["jobs_by_status"] = {
                "coming_up": len(coming_up),
                "action_required": len(action_required),
                "requires_invoicing": len(requires_invoicing),
            }
        except Exception as exc:
            log.warning("Jobber stats jobs query failed: %s", exc)

        try:
            req_data = self._post_graphql(graphql_url, bearer, requests_query)
            all_requests = req_data.get("requests", {}).get("nodes", [])
            new_reqs = [r for r in all_requests if (r.get("requestStatus") or "").lower() == "new"]
            pending_reqs = [r for r in all_requests if (r.get("requestStatus") or "").lower() == "pending"]
            stats["new_requests_count"] = len(new_reqs) + len(pending_reqs)
            stats["requests_by_status"] = {
                "new": len(new_reqs),
                "pending": len(pending_reqs),
            }
        except Exception as exc:
            log.warning("Jobber stats requests query failed: %s", exc)

        try:
            inv_data = self._post_graphql(graphql_url, bearer, invoices_query)
            all_invoices = inv_data.get("invoices", {}).get("nodes", [])
            late_inv = [i for i in all_invoices if (i.get("invoiceStatus") or "").lower() in ("late", "overdue")]
            awaiting_inv = [i for i in all_invoices if (i.get("invoiceStatus") or "").lower() == "awaiting_payment"]
            sent_inv = [i for i in all_invoices if (i.get("invoiceStatus") or "").lower() == "sent"]
            stats["pending_invoice_count"] = len(late_inv) + len(awaiting_inv) + len(sent_inv)
            stats["invoices_by_status"] = {
                "late": len(late_inv),
                "awaiting_payment": len(awaiting_inv),
                "sent": len(sent_inv),
            }
        except Exception as exc:
            log.warning("Jobber stats invoices query failed: %s", exc)

        return stats


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
                    "preview_url": f"/integrations/immich/assets/{a.get('id')}/thumbnail" if a.get("id") else "",
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
    api_prefix = "/api/bricoprohq/v1"
    timeout = httpx.Timeout(10.0, connect=5.0)

    def _require_config(self):
        if not self.base_url:
            raise ConnectorNotConfigured("Enter your Paperless-GPT local URL.")
        if not self.api_key:
            raise ConnectorNotConfigured("Enter the API key generated in Paperless-GPT.")

    def _api_base(self) -> str:
        return f"{self.base_url}{self.api_prefix}"

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key}

    def _connector_error(
        self,
        message: str,
        *,
        status_code: int = 502,
        error_type: str = "paperless_gpt_error",
        target_url: str = "",
        upstream_status: int | None = None,
        hint: str = "",
        response_summary: str = "",
    ) -> ConnectorError:
        return ConnectorError(
            message,
            status_code=status_code,
            error_type=error_type,
            target_url=target_url,
            upstream_status=upstream_status,
            configured_base_url=self.base_url,
            hint=hint,
            response_summary=response_summary,
            structured=True,
        )

    def _handle_http_status(self, exc: httpx.HTTPStatusError) -> None:
        status = exc.response.status_code
        target = str(exc.request.url)
        path = exc.request.url.path
        summary = _response_snippet(exc.response)
        if status == 401:
            raise self._connector_error(
                "API key rejected. Generate/copy the key again from Paperless-GPT.",
                status_code=401,
                error_type="unauthorized",
                target_url=target,
                upstream_status=status,
                hint="Verify the BricoproHQ API key in Paperless-GPT and paste it again.",
                response_summary=summary,
            ) from exc
        if status == 403:
            raise self._connector_error(
                "Paperless-GPT rejected the API key.",
                status_code=403,
                error_type="forbidden",
                target_url=target,
                upstream_status=status,
                hint="Verify the key has access to the BricoproHQ API in Paperless-GPT.",
                response_summary=summary,
            ) from exc
        if status == 404:
            raise self._connector_error(
                f"Paperless-GPT endpoint was not found at {path}.",
                status_code=404,
                error_type="not_found",
                target_url=target,
                upstream_status=status,
                hint=(
                    "Enter the Paperless-GPT base URL only, not the full "
                    "/api/bricoprohq/v1 endpoint. Confirm this Paperless-GPT version exposes "
                    "the BricoproHQ API."
                ),
                response_summary=summary,
            ) from exc
        if status in {500, 502, 503, 504}:
            raise self._connector_error(
                f"Paperless-GPT returned HTTP {status} while testing {path}.",
                status_code=502,
                error_type="upstream_error",
                target_url=target,
                upstream_status=status,
                hint=(
                    "Paperless-GPT was reachable from the Bricopro HQ backend, but it returned "
                    "an upstream error. Check Paperless-GPT and reverse-proxy logs."
                ),
                response_summary=summary,
            ) from exc
        raise self._connector_error(
            f"Paperless-GPT returned HTTP {status} while testing {path}.",
            status_code=502,
            error_type="http_error",
            target_url=target,
            upstream_status=status,
            hint="Check the configured base URL and Paperless-GPT API compatibility.",
            response_summary=summary,
        ) from exc

    def _get_json(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._api_base()}{path}"
        try:
            response = httpx.get(
                url,
                params=params,
                headers=self._headers(),
                timeout=self.timeout,
                follow_redirects=False,
            )
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError as exc:
                raise self._connector_error(
                    "Paperless-GPT returned a non-JSON response.",
                    error_type="invalid_response",
                    target_url=str(response.request.url),
                    upstream_status=response.status_code,
                    hint="The base URL may point to a web page or reverse-proxy error page instead of Paperless-GPT.",
                    response_summary=_response_snippet(response),
                ) from exc
            if not isinstance(data, dict):
                raise self._connector_error(
                    "Paperless-GPT returned an unexpected JSON response.",
                    error_type="invalid_response",
                    target_url=str(response.request.url),
                    upstream_status=response.status_code,
                    hint="Confirm this Paperless-GPT version exposes the BricoproHQ API.",
                )
            return data
        except httpx.HTTPStatusError as exc:
            self._handle_http_status(exc)
        except ConnectorError:
            raise
        except httpx.InvalidURL as exc:
            raise self._connector_error(
                "Paperless-GPT URL is malformed.",
                status_code=400,
                error_type="malformed_url",
                target_url=url,
                hint="Enter a full Paperless-GPT base URL such as http://paperless-gpt.local:8080.",
            ) from exc
        except httpx.ConnectTimeout as exc:
            raise self._connector_error(
                "Timed out connecting to Paperless-GPT from the Bricopro HQ backend.",
                error_type="timeout",
                target_url=url,
                hint=(
                    "The connectivity test runs inside the Bricopro HQ backend runtime. "
                    "Docker/container installs may need a service hostname or container-reachable URL."
                ),
            ) from exc
        except httpx.TimeoutException as exc:
            raise self._connector_error(
                "Timed out waiting for Paperless-GPT to respond to the Bricopro HQ backend.",
                error_type="timeout",
                target_url=url,
                hint="Check Paperless-GPT load, reverse proxy timeouts, and backend-container network reachability.",
            ) from exc
        except httpx.ConnectError as exc:
            raise self._connector_error(
                "Could not connect to Paperless-GPT from the Bricopro HQ backend.",
                error_type="connection_failed",
                target_url=url,
                hint=(
                    "Manual curl from the host can succeed even when the backend container cannot reach "
                    "that address. For Docker, try the Paperless-GPT service name, container hostname, "
                    "or another URL reachable from the Bricopro HQ backend."
                ),
            ) from exc
        except httpx.RequestError as exc:
            raise self._connector_error(
                "Paperless-GPT request failed from the Bricopro HQ backend.",
                error_type="network_error",
                target_url=url,
                hint="Check DNS, routing, firewall rules, and whether the URL is reachable from the backend runtime.",
            ) from exc

    def _normalize_document(self, doc: dict) -> dict:
        doc_id = doc.get("id")
        return {
            "id": doc_id,
            "title": doc.get("title") or doc.get("name") or doc.get("original_file_name") or "Untitled document",
            "added": doc.get("added") or doc.get("created_at") or doc.get("created"),
            "document_url": f"{self._api_base()}/documents/{doc_id}" if doc_id else "",
        }

    def _documents_payload(self, data: dict) -> dict:
        raw_documents = data.get("documents", [])
        documents = [
            self._normalize_document(doc)
            for doc in raw_documents
            if isinstance(doc, dict)
        ] if isinstance(raw_documents, list) else []
        return {
            "count": data.get("count", len(documents)),
            "documents": documents,
        }

    def test_connection(self) -> dict:
        self._require_config()
        validate_paperless_gpt_base_url(self.base_url)
        health = self._get_json("/health")
        if health.get("ok") is not True or health.get("service") != "paperless-gpt":
            raise self._connector_error(
                "Paperless-GPT health response did not identify the Paperless-GPT BricoproHQ API.",
                error_type="invalid_health_response",
                target_url=f"{self._api_base()}/health",
                hint="Confirm the base URL points to Paperless-GPT and not Paperless-ngx or Bricopro HQ.",
            )
        stats = self._get_json("/stats")
        return {
            "health": health,
            "stats": stats,
        }

    def fetch(self) -> dict:
        self._require_config()
        validate_paperless_gpt_base_url(self.base_url)
        result = self._documents_payload(self._get_json("/documents", params={"limit": 25}))
        try:
            stats = self._get_json("/stats")
            result["stats"] = stats
            result["stats_error"] = None
        except Exception as exc:
            log.warning("Paperless-GPT stats fetch failed: %s", exc)
            result["stats"] = None
            result["stats_error"] = str(exc)
        try:
            health = self._get_json("/health")
            result["health"] = health
            result["health_error"] = None
        except Exception as exc:
            log.warning("Paperless-GPT health fetch failed: %s", exc)
            result["health"] = None
            result["health_error"] = str(exc)
        return result


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
