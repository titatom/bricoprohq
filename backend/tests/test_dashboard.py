import os
import importlib
from fastapi.testclient import TestClient


def make_client():
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///./test.db"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    from app import main
    importlib.reload(main)
    return main.app


def login(client):
    r = client.post("/auth/login", json={"email": "admin@bricopro.local", "password": "admin1234"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_dashboard_requires_auth():
    app = make_client()
    with TestClient(app) as client:
        r = client.get("/dashboard")
        assert r.status_code == 401


def test_refresh_and_cache_flow():
    app = make_client()
    with TestClient(app) as client:
        h = login(client)
        r = client.post("/dashboard/refresh/google_calendar", headers=h)
        assert r.status_code == 200
        r2 = client.get("/dashboard", headers=h)
        assert r2.status_code == 200
        payload = r2.json()
        assert payload["google_calendar"]["cached"] is True
        assert "data" in payload["google_calendar"]


def test_integrations_endpoint():
    app = make_client()
    with TestClient(app) as client:
        h = login(client)
        r = client.get("/integrations", headers=h)
        assert r.status_code == 200
        providers = [i["provider"] for i in r.json()]
        assert "google_calendar" in providers


def test_update_integration():
    app = make_client()
    with TestClient(app) as client:
        h = login(client)
        r = client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )
        assert r.status_code == 200


def test_quick_links_crud():
    app = make_client()
    with TestClient(app) as client:
        h = login(client)
        r = client.post("/quick-links", headers=h, json={"title": "Test", "url": "https://example.com", "category": "test", "icon": "link", "sort_order": 0, "is_active": True})
        assert r.status_code == 200
        link_id = r.json()["id"]
        r2 = client.get("/quick-links", headers=h)
        assert any(l["id"] == link_id for l in r2.json())
        r3 = client.delete(f"/quick-links/{link_id}", headers=h)
        assert r3.status_code == 200
