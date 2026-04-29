import os
import importlib
from fastapi.testclient import TestClient


def make_client(db_name):
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


def test_social_to_publishing_to_campaign_flow():
    app = make_client("test_m3_flow.db")
    with TestClient(app) as c:
        h = auth(c)

        gen = c.post("/social/generate", headers=h, json={
            "service_category": "Peinture intérieure",
            "platform": "facebook",
            "language": "fr",
            "tone": "professional",
            "job_description": "Mur salon",
            "city": "Montréal",
            "cta": "request_quote",
        })
        assert gen.status_code == 200, gen.text
        data = gen.json()
        assert "draft_id" in data
        assert "main_copy" in data
        draft_id = data["draft_id"]

        move = c.put(f"/publishing/drafts/{draft_id}/status?status=needs_review", headers=h)
        assert move.status_code == 200, move.text

        camp = c.post("/campaigns", headers=h, json={
            "name": "Spring push", "service_category": "Peinture", "status": "active", "message": "Book now"
        })
        assert camp.status_code == 200, camp.text
        camp_id = camp.json()["id"]

        camp_gen = c.post(f"/campaigns/{camp_id}/generate", headers=h)
        assert camp_gen.status_code == 200, camp_gen.text

        cal = c.get("/publishing/calendar", headers=h)
        assert cal.status_code == 200

        kan = c.get("/publishing/kanban", headers=h)
        assert kan.status_code == 200


def test_queue_assets():
    app = make_client("test_m3_assets.db")
    with TestClient(app) as c:
        h = auth(c)

        r = c.post("/queues/assets", headers=h, json={
            "title": "Before shot", "source": "immich",
            "source_url": "http://immich.local/asset/1",
            "service_category": "Peinture", "status": "new",
        })
        assert r.status_code == 200, r.text
        asset_id = r.json()["id"]

        r2 = c.put(f"/queues/assets/{asset_id}/status", headers=h, json={"status": "social_worthy", "note": "Good shot"})
        assert r2.status_code == 200

        r3 = c.get("/queues/images", headers=h)
        assert r3.status_code == 200
        assert any(a["id"] == asset_id for a in r3.json())

        r4 = c.get("/queues/images?status=social_worthy", headers=h)
        assert r4.status_code == 200
        assert any(a["id"] == asset_id for a in r4.json())

        r5 = c.post("/queues/assets", headers=h, json={
            "title": "Receipt Home Depot", "source": "paperless",
            "source_url": "http://paperless.local/documents/5",
            "service_category": "", "status": "new",
        })
        assert r5.status_code == 200
        doc_id = r5.json()["id"]
        r6 = c.get("/queues/documents", headers=h)
        assert r6.status_code == 200
        assert any(a["id"] == doc_id for a in r6.json())


def test_invalid_status_rejected():
    app = make_client("test_m3_status.db")
    with TestClient(app) as c:
        h = auth(c)
        r = c.post("/queues/assets", headers=h, json={"title": "X", "source": "immich", "status": "new"})
        assert r.status_code == 200
        asset_id = r.json()["id"]
        r2 = c.put(f"/queues/assets/{asset_id}/status", headers=h, json={"status": "totally_made_up"})
        assert r2.status_code == 422


def test_settings_crud():
    app = make_client("test_m3_settings.db")
    with TestClient(app) as c:
        h = auth(c)
        r = c.put("/settings/ai_provider", headers=h, json={"value": "openai"})
        assert r.status_code == 200
        r2 = c.get("/settings", headers=h)
        assert r2.status_code == 200
        vals = {s["key"]: s["value"] for s in r2.json()}
        assert vals.get("ai_provider") == "openai"
