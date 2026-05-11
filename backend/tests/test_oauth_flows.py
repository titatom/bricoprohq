"""Tests covering the OAuth callback success path and token-refresh-on-401."""

import importlib
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


def _reload_main(db_name: str):
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    os.environ["SECRET_KEY"] = "test-oauth-flows-key-aaaaaaaaaaa"
    os.environ.setdefault("APP_BASE_URL", "http://localhost:3000")
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


# ── OAuth callback ───────────────────────────────────────────────────────────

def test_oauth_callback_persists_tokens_on_jobber_success():
    main = _reload_main("test_oauth_callback_jobber.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        # Save client credentials for jobber.
        r = client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": '{"client_id":"cid","client_secret":"csec"}',
            },
        )
        assert r.status_code == 200

        # Begin the authorize flow to register a state in the DB.
        r = client.get(
            "/integrations/jobber/oauth/authorize?mode=json",
            headers=h,
        )
        assert r.status_code == 200
        url = r.json()["authorization_url"]
        state = url.split("state=")[1].split("&")[0]

        token_response = httpx.Response(
            200,
            json={
                "access_token": "fresh-jobber-access",
                "refresh_token": "fresh-jobber-refresh",
                "expires_in": 3600,
            },
            request=httpx.Request("POST", "https://api.getjobber.com/api/oauth/token"),
        )
        with patch("httpx.post", return_value=token_response):
            cb = client.get(
                f"/integrations/jobber/oauth/callback?code=jbr-code&state={state}",
                follow_redirects=False,
            )

        assert cb.status_code in (302, 307)
        loc = cb.headers.get("location", "")
        assert "oauth_connected=jobber" in loc

        # Integration shows up as connected and oauth_connected=True.
        integ = client.get("/integrations/jobber", headers=h).json()
        assert integ["oauth_connected"] is True
        assert integ["status"] == "ok"


def test_oauth_callback_rejects_reused_state():
    main = _reload_main("test_oauth_callback_reuse.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": '{"client_id":"cid","client_secret":"csec"}',
            },
        )
        r = client.get(
            "/integrations/jobber/oauth/authorize?mode=json",
            headers=h,
        )
        state = r.json()["authorization_url"].split("state=")[1].split("&")[0]

        token_response = httpx.Response(
            200,
            json={
                "access_token": "jbr-access",
                "refresh_token": "jbr-refresh",
                "expires_in": 3600,
            },
            request=httpx.Request("POST", "https://api.getjobber.com/api/oauth/token"),
        )

        with patch("httpx.post", return_value=token_response):
            first = client.get(
                f"/integrations/jobber/oauth/callback?code=c1&state={state}",
                follow_redirects=False,
            )
            second = client.get(
                f"/integrations/jobber/oauth/callback?code=c2&state={state}",
                follow_redirects=False,
            )

        assert first.status_code in (302, 307)
        # Second use of the same state must be rejected — single-use semantics.
        assert second.status_code == 400


# ── Token refresh on 401 ─────────────────────────────────────────────────────

def test_jobber_token_refresh_on_401_then_retry():
    """
    When Jobber returns 401, the connector should refresh and retry exactly once.
    Verifies the OAuthRefresher integration path end-to-end through fetch().
    """
    main = _reload_main("test_oauth_refresh_jobber.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        # Save credentials + simulate an existing OAuth grant.
        client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": '{"client_id":"cid","client_secret":"csec"}',
            },
        )

    from app.db import SessionLocal
    from app.models import Integration

    with SessionLocal() as db:
        i = db.query(Integration).filter(Integration.provider == "jobber").first()
        i.oauth_access_token = "stale-access"
        i.oauth_refresh_token = "valid-refresh"
        i.oauth_token_expires_at = datetime.utcnow() + timedelta(hours=1)
        db.commit()

    # Sequence of httpx.post calls during the connector.fetch():
    # 1. GraphQL jobs query -> 401 (stale token)
    # 2. OAuth token endpoint -> 200 with new tokens
    # 3. GraphQL jobs query retried -> 200
    # 4. GraphQL requests query -> 200
    # 5. GraphQL quotes query -> 200
    # 6. GraphQL invoices query -> 200
    calls = {"n": 0}
    token_response = httpx.Response(
        200,
        json={"access_token": "fresh-access", "refresh_token": "fresh-refresh", "expires_in": 3600},
        request=httpx.Request("POST", "https://api.getjobber.com/api/oauth/token"),
    )
    graphql_401 = httpx.Response(
        401,
        text="Unauthorized",
        request=httpx.Request("POST", "https://api.getjobber.com/api/graphql"),
    )
    graphql_jobs_ok = httpx.Response(
        200,
        json={"data": {"jobs": {"nodes": []}}},
        request=httpx.Request("POST", "https://api.getjobber.com/api/graphql"),
    )
    graphql_requests_ok = httpx.Response(
        200,
        json={"data": {"requests": {"nodes": []}}},
        request=httpx.Request("POST", "https://api.getjobber.com/api/graphql"),
    )
    graphql_quotes_ok = httpx.Response(
        200,
        json={"data": {"quotes": {"nodes": []}}},
        request=httpx.Request("POST", "https://api.getjobber.com/api/graphql"),
    )
    graphql_invoices_ok = httpx.Response(
        200,
        json={"data": {"invoices": {"nodes": []}}},
        request=httpx.Request("POST", "https://api.getjobber.com/api/graphql"),
    )

    def fake_post(url, *args, **kwargs):
        calls["n"] += 1
        url_s = str(url)
        if url_s.endswith("/oauth/token"):
            return token_response
        # Sequence of graphql calls. The first one fails with 401, triggering
        # a refresh + retry. Subsequent collection calls succeed.
        if calls["n"] == 1:
            return graphql_401
        if calls["n"] == 2:
            return token_response  # token endpoint, in case ordering shifts
        if calls["n"] == 3:
            return graphql_jobs_ok
        if calls["n"] == 4:
            return graphql_requests_ok
        if calls["n"] == 5:
            return graphql_quotes_ok
        return graphql_invoices_ok

    main = importlib.import_module("app.main")
    with TestClient(main.app) as client:
        h = _auth(client)
        with patch("httpx.post", side_effect=fake_post):
            r = client.post("/dashboard/refresh/jobber", headers=h)

    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # Verify the new access token was persisted.
    with SessionLocal() as db:
        i = db.query(Integration).filter(Integration.provider == "jobber").first()
        assert i.oauth_access_token == "fresh-access"
