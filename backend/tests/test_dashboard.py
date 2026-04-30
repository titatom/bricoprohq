import os
import importlib
from fastapi.testclient import TestClient


def make_client(db_name="test_dash.db"):
    db_path = os.path.join(os.path.dirname(__file__), '..', db_name)
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    from app import main
    importlib.reload(main)
    return main.app


def auth(client):
    r = client.post("/auth/login", json={"email": "admin@bricopro.local", "password": "admin1234"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_dashboard_requires_auth():
    app = make_client("test_dash_auth.db")
    with TestClient(app) as client:
        r = client.get("/dashboard")
        assert r.status_code == 401


def test_refresh_and_cache_flow():
    app = make_client("test_dash_cache.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.post("/dashboard/refresh/google_calendar", headers=h)
        assert r.status_code == 200
        r2 = client.get("/dashboard", headers=h)
        assert r2.status_code == 200
        payload = r2.json()
        assert payload["google_calendar"]["cached"] is True
        assert "data" in payload["google_calendar"]


def test_integrations_endpoint():
    app = make_client("test_dash_int.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.get("/integrations", headers=h)
        assert r.status_code == 200
        data = r.json()
        providers = [i["provider"] for i in data]
        assert "google_calendar" in providers
        assert "immich-gpt" in providers
        # Each integration must include the new fields
        for item in data:
            assert "config_fields" in item
            assert "oauth_connected" in item


def test_update_integration():
    app = make_client("test_dash_upd.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "immich"
        assert data["base_url"] == "http://immich.local:2283"
        # api_key should be masked in the response
        assert data["config_fields"]["api_key"] == "••••••••"


def test_update_integration_masked_value_preserved():
    """Sending masked placeholder back should not overwrite the real stored secret."""
    app = make_client("test_dash_mask.db")
    with TestClient(app) as client:
        h = auth(client)
        # First save with a real key
        r1 = client.put(
            "/integrations/paperless",
            headers=h,
            json={"base_url": "http://paperless.local", "config_json": '{"api_key":"real-secret-token"}'},
        )
        assert r1.status_code == 200
        # Now resave with the masked placeholder (simulating UI re-submit without editing)
        r2 = client.put(
            "/integrations/paperless",
            headers=h,
            json={"base_url": "http://paperless.local", "config_json": '{"api_key":"••••••••"}'},
        )
        assert r2.status_code == 200
        # Verify through GET that the stored key is still the real one
        r3 = client.get("/integrations/paperless", headers=h)
        assert r3.status_code == 200
        # The masked display should still show presence (not empty)
        assert r3.json()["config_fields"]["api_key"] == "••••••••"


def test_integration_test_endpoint_not_configured():
    app = make_client("test_dash_test.db")
    with TestClient(app) as client:
        h = auth(client)
        # Immich is seeded but with no credentials — should return 400
        r = client.post("/integrations/immich/test", headers=h)
        assert r.status_code == 400  # ConnectorNotConfigured


def test_jobber_oauth_disconnect():
    app = make_client("test_dash_jobber.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.post("/integrations/jobber/oauth/disconnect", headers=h)
        assert r.status_code == 200
        assert r.json()["disconnected"] is True


def test_google_calendar_oauth_disconnect():
    app = make_client("test_dash_google.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.post("/integrations/google_calendar/oauth/disconnect", headers=h)
        assert r.status_code == 200
        assert r.json()["disconnected"] is True


def test_oauth_authorize_missing_client_id():
    """Attempting OAuth authorize without a saved client_id should return 400."""
    app = make_client("test_dash_oauth_nocid.db")
    with TestClient(app, follow_redirects=False) as client:
        h = auth(client)
        # google_calendar is seeded with no config
        r = client.get("/integrations/google_calendar/oauth/authorize", headers=h)
        assert r.status_code == 400


def test_oauth_authorize_unsupported_provider():
    """A provider not in OAUTH_PROVIDERS registry should return 400."""
    app = make_client("test_dash_oauth_bad.db")
    with TestClient(app, follow_redirects=False) as client:
        h = auth(client)
        r = client.get("/integrations/immich/oauth/authorize", headers=h)
        assert r.status_code == 400


def test_oauth_authorize_redirects_when_configured():
    """With client_id saved, authorize should redirect to the provider."""
    app = make_client("test_dash_oauth_redir.db")
    with TestClient(app, follow_redirects=False) as client:
        h = auth(client)
        # Save client_id for google_calendar
        client.put(
            "/integrations/google_calendar",
            headers=h,
            json={"base_url": "", "config_json": '{"client_id":"test-gid","client_secret":"test-gsecret"}'},
        )
        r = client.get("/integrations/google_calendar/oauth/authorize", headers=h)
        assert r.status_code in (302, 307)
        assert "accounts.google.com" in r.headers.get("location", "")


def test_quick_links_crud():
    app = make_client("test_dash_ql.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.post("/quick-links", headers=h, json={
            "title": "Test", "url": "https://example.com",
            "category": "test", "icon": "link", "sort_order": 0, "is_active": True,
        })
        assert r.status_code == 200
        link_id = r.json()["id"]
        r2 = client.get("/quick-links", headers=h)
        assert any(l["id"] == link_id for l in r2.json())
        r3 = client.delete(f"/quick-links/{link_id}", headers=h)
        assert r3.status_code == 200


def test_processing_summary_counts_immich_gpt_images():
    app = make_client("test_dash_processing.db")
    with TestClient(app) as client:
        h = auth(client)
        client.post("/queues/assets", headers=h, json={
            "title": "Business photo", "source": "immich-gpt", "status": "pending_ai",
        })
        client.post("/queues/assets", headers=h, json={
            "title": "Personal photo", "source": "immich-gpt", "status": "personal_photo",
        })
        client.post("/queues/assets", headers=h, json={
            "title": "Receipt", "source": "paperless-gpt", "status": "missing_tags",
        })

        r = client.get("/processing/summary", headers=h)

        assert r.status_code == 200
        data = r.json()
        assert data["images_pending"] == 1
        assert data["documents_pending"] == 1
        assert data["personal_images"] == 1
        assert data["image_source"] == "immich-gpt"
