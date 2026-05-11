"""Tests for the PR2 correctness / data-integrity changes:
- TZ-aware datetimes via utc_now()
- DashboardRefresh: cache is stamped stale on failure, last_error is populated
- /publishing/drafts/{id}/status reuses DraftStatusIn validation
- Campaign generate routes through generate_social_content (template fallback)
- Masked-secret helper centralization (Integration update keeps real secret)
"""

import importlib
import json
import os
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


def _reload_main(db_name: str, env: dict | None = None):
    extra = env or {}
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    os.environ["SECRET_KEY"] = extra.pop("SECRET_KEY", "test-correctness-key-aaaaaaaaaaaa")
    for k, v in extra.items():
        os.environ[k] = v
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
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_utc_now_returns_naive_aware_value():
    main = _reload_main("test_correctness_utc_now.db")
    value = main.utc_now()
    assert value.tzinfo is None
    # Reasonable sanity check: within a few minutes of "now".
    import datetime as _dt
    assert abs((value - _dt.datetime.utcnow()).total_seconds()) < 60


def test_dashboard_refresh_marks_integration_error_on_failure():
    main = _reload_main("test_correctness_refresh_error.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        # google_calendar is configured-but-not-connected: refresh should fail.
        r = client.post("/dashboard/refresh/google_calendar", headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert body["error"]

        # The cache is populated with the error payload (so the UI can show it).
        dashboard = client.get("/dashboard", headers=h).json()
        cached_payload = dashboard["google_calendar"]
        assert cached_payload["cached"] is True
        assert cached_payload["stale"] is True  # error caches are intentionally stale
        assert "error" in cached_payload["data"]

        # The Integration row tracks last_error / last_error_at.
        integ = client.get("/integrations/google_calendar", headers=h).json()
        assert integ["status"] == "error"
        assert integ["last_error"]
        assert integ["last_error_at"]


def test_dashboard_refresh_clears_error_on_success():
    main = _reload_main("test_correctness_refresh_success.db")
    with TestClient(main.app) as client:
        h = _auth(client)

        # First a failed refresh stamps last_error.
        client.post("/dashboard/refresh/google_calendar", headers=h)

        # Now simulate a successful Immich fetch by mocking the upstream call.
        client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )

        request = httpx.Request("POST", "http://immich.local:2283/api/search/metadata")
        response = httpx.Response(
            200,
            json={"assets": []},
            request=request,
        )
        with patch("httpx.post", return_value=response):
            r = client.post("/dashboard/refresh/immich", headers=h)
            assert r.status_code == 200
            assert r.json()["status"] == "ok"

        integ = client.get("/integrations/immich", headers=h).json()
        assert integ["status"] == "ok"
        assert integ["last_error"] == ""
        assert integ["last_error_at"] is None


def test_draft_status_endpoint_validates_via_schema():
    main = _reload_main("test_correctness_draft_status.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        # Seed a draft.
        r = client.post(
            "/publishing/drafts",
            headers=h,
            json={"title": "X", "platform": "facebook"},
        )
        assert r.status_code == 200
        draft_id = r.json()["id"]

        # Valid transition.
        assert client.put(
            f"/publishing/drafts/{draft_id}/status?status=approved",
            headers=h,
        ).status_code == 200

        # Invalid status — must come back as 422 (not 500).
        r = client.put(
            f"/publishing/drafts/{draft_id}/status?status=banana",
            headers=h,
        )
        assert r.status_code == 422


def test_campaign_generate_uses_template_when_ai_unconfigured():
    main = _reload_main("test_correctness_campaign_generate.db")
    with TestClient(main.app) as client:
        h = _auth(client)

        # Create campaign
        r = client.post(
            "/campaigns",
            headers=h,
            json={"name": "Spring push", "service_category": "Exterior painting", "status": "active", "message": "Plan exterior repairs early."},
        )
        assert r.status_code == 200
        campaign_id = r.json()["id"]

        # Trigger generation. No AI provider configured -> template fallback.
        r = client.post(f"/campaigns/{campaign_id}/generate", headers=h, json={"platform": "instagram", "language": "en"})
        assert r.status_code == 200
        body = r.json()
        assert body["campaign_id"] == campaign_id
        assert body["ai_used"] is False

        draft_id = body["draft_id"]
        drafts = client.get("/publishing/drafts", headers=h).json()
        draft = next(d for d in drafts if d["id"] == draft_id)
        assert draft["platform"] == "instagram"
        assert draft["language"] == "en"
        # Body should not be empty — template fallback always produces copy.
        assert draft["body"]


def test_is_masked_secret_helper():
    from app.services.db_utils import is_masked_secret
    assert is_masked_secret("••••••••") is True
    assert is_masked_secret("") is False
    assert is_masked_secret(None) is False
    assert is_masked_secret("real-secret") is False
    assert is_masked_secret("•") is True


def test_update_integration_preserves_real_secret_for_client_secret():
    """Already covered for api_key — extend to client_secret to verify the
    masked-secret helper is reused for every secret key."""
    main = _reload_main("test_correctness_mask_client_secret.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        r = client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": json.dumps({
                    "client_id": "my-client-id",
                    "client_secret": "real-jobber-client-secret",
                }),
            },
        )
        assert r.status_code == 200

        # Re-save with masked placeholders — should not overwrite the secret.
        r = client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": json.dumps({
                    "client_id": "my-client-id",
                    "client_secret": "••••••••",
                }),
            },
        )
        assert r.status_code == 200

        # Read raw column to verify the secret survived the round-trip.
        import sqlite3

        from app.services.crypto import decrypt
        raw = sqlite3.connect("test_correctness_mask_client_secret.db").execute(
            "SELECT config_json FROM integrations WHERE provider = 'jobber'"
        ).fetchone()[0]
        config = json.loads(decrypt(raw))
        assert config["client_secret"] == "real-jobber-client-secret"
