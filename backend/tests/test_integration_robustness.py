"""Tests for PR3 integration robustness changes:
- Shared HTTP helper retries transient network errors
- OAuthRefresher coalesces concurrent refreshes under an in-flight lock
- Paperless tag id lookup is cached for the configured TTL
- Connector ping() captures the upstream_version and surfaces it in
  /integrations/{provider}
"""

import importlib
import os
import threading
import time
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient


def _reload_main(db_name: str):
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    os.environ["SECRET_KEY"] = "test-robustness-key-aaaaaaaaaaaaaaaa"
    if os.path.exists(db_name):
        os.remove(db_name)
    from app import main
    importlib.reload(main)
    return main


def _auth(client) -> dict:
    r = client.post(
        "/auth/login",
        json={"email": "admin@bricopro.local", "password": "admin1234"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Shared HTTP helper ───────────────────────────────────────────────────────

def test_shared_http_get_retries_on_connect_error_then_succeeds():
    from app.services import http

    call_count = {"n": 0}

    def fake_request(method, url, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.ConnectError("boom", request=httpx.Request(method, url))
        return httpx.Response(200, json={"ok": True}, request=httpx.Request(method, url))

    with patch("httpx.request", side_effect=fake_request):
        resp = http.get("https://example.com/ping", retries=2, backoff=0)

    assert resp.status_code == 200
    assert call_count["n"] == 2


def test_shared_http_does_not_retry_http_status_errors():
    """HTTPStatusError surfaces to the caller — we only retry transient network errors."""
    from app.services import http

    call_count = {"n": 0}

    def fake_request(method, url, **kwargs):
        call_count["n"] += 1
        return httpx.Response(500, request=httpx.Request(method, url))

    with patch("httpx.request", side_effect=fake_request):
        resp = http.get("https://example.com/foo", retries=3, backoff=0)

    # No retry happens because http.get does not raise on non-2xx; the
    # caller is responsible for raise_for_status(). The point of this test
    # is that we hit the server exactly once.
    assert resp.status_code == 500
    assert call_count["n"] == 1


def test_shared_http_gives_up_after_max_retries():
    from app.services import http

    call_count = {"n": 0}

    def fake_request(method, url, **kwargs):
        call_count["n"] += 1
        raise httpx.ConnectError("nope", request=httpx.Request(method, url))

    with patch("httpx.request", side_effect=fake_request):
        with pytest.raises(httpx.ConnectError):
            http.get("https://example.com/foo", retries=2, backoff=0)

    assert call_count["n"] == 3  # initial + 2 retries


# ── OAuthRefresher ───────────────────────────────────────────────────────────

def test_oauth_refresher_lock_coalesces_concurrent_callers():
    """If two threads both notice an expired token, only one refresh runs."""
    main = _reload_main("test_robustness_oauth_lock.db")

    with TestClient(main.app):
        pass  # trigger startup_seed

    from datetime import datetime, timedelta

    from app.db import SessionLocal
    from app.models import Integration
    from app.services.oauth import OAuthRefresher

    # Configure the jobber integration with expired tokens + client creds.
    with SessionLocal() as db:
        i = db.query(Integration).filter(Integration.provider == "jobber").first()
        i.oauth_access_token = "stale-access"
        i.oauth_refresh_token = "valid-refresh"
        i.oauth_token_expires_at = datetime.utcnow() - timedelta(seconds=10)
        # Setting config via the encrypted column.
        import json
        i.config_json = json.dumps({"client_id": "cid", "client_secret": "csec"})
        db.commit()

    call_count = {"n": 0}
    refresh_release = threading.Event()
    refresh_held = threading.Event()

    def slow_token_endpoint(url, **kwargs):
        call_count["n"] += 1
        refresh_held.set()
        # Hold the lock long enough for the second thread to try and skip.
        refresh_release.wait(timeout=2.0)
        return httpx.Response(
            200,
            json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600},
            request=httpx.Request("POST", url),
        )

    def refresh_in_thread(results, idx):
        try:
            with SessionLocal() as db:
                i = db.query(Integration).filter(Integration.provider == "jobber").first()
                from app.services.connectors import ConnectorError, ConnectorNotConfigured
                OAuthRefresher(
                    provider="jobber",
                    token_url="https://api.getjobber.com/api/oauth/token",
                    integration=i,
                    client_id="cid",
                    client_secret="csec",
                    not_configured_factory=ConnectorNotConfigured,
                    error_factory=ConnectorError,
                ).refresh()
                results[idx] = "ok"
        except Exception as exc:
            results[idx] = repr(exc)

    with patch("httpx.post", side_effect=slow_token_endpoint):
        results = {0: None, 1: None}
        t1 = threading.Thread(target=refresh_in_thread, args=(results, 0))
        t2 = threading.Thread(target=refresh_in_thread, args=(results, 1))
        t1.start()
        refresh_held.wait(timeout=2.0)
        t2.start()
        time.sleep(0.2)  # let t2 reach the lock
        refresh_release.set()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

    assert results == {0: "ok", 1: "ok"}
    # The second thread observed the freshly refreshed token and skipped the
    # network round-trip.
    assert call_count["n"] == 1


# ── Paperless tag cache ──────────────────────────────────────────────────────

def test_paperless_tag_id_cache_short_circuits_repeated_lookups():
    """A second fetch within the cache TTL should not re-query /api/tags/."""
    main = _reload_main("test_robustness_paperless_tag_cache.db")

    with TestClient(main.app) as client:
        h = _auth(client)
        client.put(
            "/integrations/paperless",
            headers=h,
            json={
                "base_url": "http://paperless.local:8000",
                "config_json": '{"api_key":"tok"}',
            },
        )

    from app.db import SessionLocal
    from app.models import Integration
    from app.services.connectors import PaperlessConnector

    # Clear the class-level cache between tests.
    PaperlessConnector._TAG_CACHE.clear()

    tag_response = httpx.Response(
        200,
        json={"results": [{"id": 42, "name": "ai-processed"}]},
        request=httpx.Request("GET", "http://paperless.local:8000/api/tags/"),
    )

    with SessionLocal() as db:
        i = db.query(Integration).filter(Integration.provider == "paperless").first()
        c = PaperlessConnector(i)
        with patch("httpx.get", return_value=tag_response) as mock_get:
            first = c._tag_id_for_name("ai-processed", {})
            second = c._tag_id_for_name("ai-processed", {})

    assert first == 42
    assert second == 42
    # /api/tags/ was only hit once.
    assert mock_get.call_count == 1


# ── ping() upstream_version capture ──────────────────────────────────────────

def test_integration_test_captures_immich_upstream_version():
    """Already covered indirectly in test_dashboard. Sanity check here too."""
    main = _reload_main("test_robustness_upstream_version.db")

    with TestClient(main.app) as client:
        h = _auth(client)
        client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )

        request = httpx.Request("GET", "http://immich.local:2283/api/server-info")
        response = httpx.Response(
            200,
            json={"version": "1.119.0", "diskUsageRaw": 0},
            request=request,
        )
        with patch("httpx.get", return_value=response):
            r = client.post("/integrations/immich/test", headers=h)

        assert r.status_code == 200
        integ = client.get("/integrations/immich", headers=h).json()
        assert integ["upstream_version"] == "1.119.0"
