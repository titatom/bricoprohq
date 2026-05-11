"""
Centralized OAuth 2.0 token refresh logic for connectors.

Before this module, the Google Calendar, Google Business, and Jobber
connectors each carried near-identical ``_refresh_token`` implementations.
The duplication made any fix (timeout tweak, error message change, log
format update) touch three places and risked them drifting apart.

`OAuthRefresher` encapsulates:

- the common ``grant_type=refresh_token`` POST body
- ``ConnectorNotConfigured`` / ``ConnectorError`` mapping
- token persistence (with optional cross-provider sync, used by Google)
- a per-(provider, integration_id) in-flight lock so a burst of concurrent
  401s only triggers one refresh attempt
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import object_session

from ..models import Integration

log = logging.getLogger("bricopro.oauth")

# (provider, integration_id) → lock. Held for the duration of a single refresh.
_refresh_locks: dict[tuple[str, int | None], threading.Lock] = {}
_locks_mutex = threading.Lock()


def _lock_for(provider: str, integration_id: int | None) -> threading.Lock:
    key = (provider, integration_id)
    with _locks_mutex:
        lock = _refresh_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _refresh_locks[key] = lock
        return lock


@dataclass
class OAuthRefresher:
    """Refresh OAuth tokens for a given integration row.

    Parameters
    ----------
    provider:
        Logical provider name, used purely for log/error messages.
    token_url:
        OAuth 2 token endpoint (e.g. https://oauth2.googleapis.com/token).
    integration:
        The SQLAlchemy ``Integration`` row whose tokens are being refreshed.
    client_id, client_secret:
        OAuth client credentials, typically pulled from
        ``integration.config_json``.
    not_configured_factory:
        Callable that builds the ``ConnectorNotConfigured`` exception used
        when a refresh is impossible (missing refresh token / client creds).
        Each connector passes its own copy so the user-facing error keeps
        the provider-specific phrasing.
    error_factory:
        Same shape, used to raise ``ConnectorError`` when the refresh
        request itself fails.
    sync:
        Optional callable invoked after a successful refresh. Used by the
        Google connectors to mirror the new tokens across the shared
        ``google_calendar`` / ``google_business`` rows.
    timeout:
        Per-request HTTP timeout in seconds; matches the historical value.
    """

    provider: str
    token_url: str
    integration: Integration
    client_id: str
    client_secret: str
    not_configured_factory: Callable[[str], Exception]
    error_factory: Callable[[str], Exception]
    sync: Callable[[Integration, dict], None] | None = None
    timeout: float = 15.0

    def refresh(self) -> None:
        intg = self.integration
        if not intg.oauth_refresh_token:
            raise self.not_configured_factory(
                f"{self.provider}: access token expired and no refresh token stored. "
                "Reconnect via Settings."
            )
        if not self.client_id or not self.client_secret:
            raise self.not_configured_factory(
                f"{self.provider}: client_id/client_secret missing for token refresh."
            )

        # Capture the token we observed *before* acquiring the lock. If, by
        # the time we hold the lock, another caller has already replaced the
        # token, skip the network round-trip. Comparing the literal token
        # value avoids the "force-refresh on 401 with an unexpired
        # access_token" footgun — a caller that observed the bad token
        # before invoking refresh() still gets a real refresh.
        token_at_call_site = intg.oauth_access_token

        lock = _lock_for(self.provider, intg.id)
        with lock:
            session = object_session(intg)
            if session:
                session.refresh(intg, attribute_names=["oauth_access_token", "oauth_token_expires_at"])
            if intg.oauth_access_token and intg.oauth_access_token != token_at_call_site:
                log.debug("%s: token already refreshed by another caller", self.provider)
                return

            log.info("%s: refreshing OAuth access token", self.provider)
            try:
                resp = httpx.post(
                    self.token_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": intg.oauth_refresh_token,
                        "grant_type": "refresh_token",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                token_data = resp.json()
            except httpx.HTTPStatusError as exc:
                log.error(
                    "%s token refresh failed: %s %s",
                    self.provider,
                    exc.response.status_code,
                    exc.response.text,
                )
                raise self.error_factory(
                    f"{self.provider} token refresh failed: {exc.response.status_code}"
                ) from exc
            except httpx.RequestError as exc:
                raise self.error_factory(
                    f"{self.provider} token refresh request failed: {exc}"
                ) from exc

            if self.sync is not None:
                self.sync(intg, token_data)
                return

            # Default behaviour: write tokens straight onto the integration row.
            expires_in = int(token_data.get("expires_in", 3600))
            intg.oauth_access_token = token_data["access_token"]
            if token_data.get("refresh_token"):
                intg.oauth_refresh_token = token_data["refresh_token"]
            intg.oauth_token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
            if session:
                session.commit()
