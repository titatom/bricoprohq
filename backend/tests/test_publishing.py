"""Tests for PR8 — real publishing & KPI ingestion."""

import importlib
import os
from datetime import date, timedelta
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


def _reload_main(db_name: str):
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    os.environ["SECRET_KEY"] = "test-publishing-key-aaaaaaaaaaaaa"
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


def _seed_meta_oauth(db_name: str, *, page_id: str = "111", token: str = "tok-page") -> None:
    """Mark the Meta integration as OAuth-connected and configure a Facebook page id."""
    from app.db import SessionLocal
    from app.models import Integration, Setting

    with SessionLocal() as db:
        i = db.query(Integration).filter(Integration.provider == "meta").first()
        i.oauth_access_token = token
        db.add(Setting(key="social_facebook_account", value=page_id))
        db.commit()


# ── Facebook publishing ──────────────────────────────────────────────────────

def test_publish_facebook_success_marks_draft_posted():
    db_name = "test_publishing_fb_success.db"
    main = _reload_main(db_name)
    with TestClient(main.app) as client:
        h = _auth(client)
        # Seed the integration credentials & the draft.
        _seed_meta_oauth(db_name, page_id="111", token="tok-page")

        draft = client.post(
            "/publishing/drafts",
            headers=h,
            json={"title": "Spring push", "platform": "facebook", "body": "Hello Montréal!"},
        ).json()
        draft_id = draft["id"]

        post_response = httpx.Response(
            200,
            json={"id": "111_99999"},
            request=httpx.Request("POST", "https://graph.facebook.com/v21.0/111/feed"),
        )
        with patch("httpx.post", return_value=post_response) as mock_post:
            r = client.post(f"/publishing/drafts/{draft_id}/publish", headers=h)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["post_id"] == "111_99999"
        assert "facebook.com" in body["post_url"]

        # Verify the post body included the draft text and hit the right URL.
        called_url = str(mock_post.call_args.args[0])
        assert called_url == "https://graph.facebook.com/v21.0/111/feed"
        assert mock_post.call_args.kwargs["data"]["message"] == "Hello Montréal!"
        assert mock_post.call_args.kwargs["data"]["access_token"] == "tok-page"

        # Draft moved to status=posted and was stamped with post_id/post_url/published_at.
        drafts = client.get("/publishing/drafts", headers=h).json()
        d = next(d for d in drafts if d["id"] == draft_id)
        assert d["status"] == "posted"


def test_publish_facebook_records_attempt_on_meta_4xx():
    db_name = "test_publishing_fb_failure.db"
    main = _reload_main(db_name)
    with TestClient(main.app) as client:
        h = _auth(client)
        _seed_meta_oauth(db_name)

        draft = client.post(
            "/publishing/drafts",
            headers=h,
            json={"title": "Bad post", "platform": "facebook", "body": "hi"},
        ).json()
        draft_id = draft["id"]

        rejection = httpx.Response(
            400,
            text='{"error":{"message":"Page admin permission required"}}',
            request=httpx.Request("POST", "https://graph.facebook.com/v21.0/111/feed"),
        )
        with patch("httpx.post", return_value=rejection):
            r = client.post(f"/publishing/drafts/{draft_id}/publish", headers=h)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "error"
        assert "Page admin permission required" in body["error"]

        # The attempt is preserved in the audit table.
        attempts = client.get(f"/publishing/drafts/{draft_id}/attempts", headers=h).json()
        assert len(attempts) == 1
        assert attempts[0]["status"] == "error"
        assert "Page admin permission required" in attempts[0]["error_message"]


def test_publish_unsupported_platform_returns_attempt_with_error():
    main = _reload_main("test_publishing_unsupported.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        draft = client.post(
            "/publishing/drafts",
            headers=h,
            json={"title": "LinkedIn post", "platform": "linkedin", "body": "hi"},
        ).json()
        r = client.post(f"/publishing/drafts/{draft['id']}/publish", headers=h)
        body = r.json()
        assert body["status"] == "error"
        assert "linkedin" in body["error"].lower()


def test_publish_facebook_requires_oauth_and_page_id():
    main = _reload_main("test_publishing_no_oauth.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        draft = client.post(
            "/publishing/drafts",
            headers=h,
            json={"title": "X", "platform": "facebook", "body": "hi"},
        ).json()
        r = client.post(f"/publishing/drafts/{draft['id']}/publish", headers=h)
        body = r.json()
        assert body["status"] == "not_configured"
        assert "Facebook Page" in body["error"]


# ── Scheduler integration ────────────────────────────────────────────────────

def test_publish_due_drafts_picks_up_scheduled_drafts_in_the_past():
    db_name = "test_publishing_due.db"
    main = _reload_main(db_name)
    with TestClient(main.app) as client:
        h = _auth(client)
        _seed_meta_oauth(db_name, page_id="222")

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        client.post(
            "/publishing/drafts",
            headers=h,
            json={
                "title": "Past due",
                "platform": "facebook",
                "body": "Hello",
                "status": "scheduled",
                "planned_date": yesterday,
                "planned_time": "08:00",
            },
        )

    post_response = httpx.Response(
        200,
        json={"id": "222_postid"},
        request=httpx.Request("POST", "https://graph.facebook.com/v21.0/222/feed"),
    )
    from app.workers.scheduler import publish_due_drafts
    with patch("httpx.post", return_value=post_response):
        outcome = publish_due_drafts()
    assert outcome["due_count"] == 1
    assert list(outcome["results"].values()) == ["success"]


def test_publish_due_drafts_skips_future_scheduled_drafts():
    db_name = "test_publishing_not_due.db"
    main = _reload_main(db_name)
    with TestClient(main.app) as client:
        h = _auth(client)
        _seed_meta_oauth(db_name)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        client.post(
            "/publishing/drafts",
            headers=h,
            json={
                "title": "Future",
                "platform": "facebook",
                "body": "Hello",
                "status": "scheduled",
                "planned_date": tomorrow,
                "planned_time": "08:00",
            },
        ).json()

    from app.workers.scheduler import publish_due_drafts
    with patch("httpx.post") as mock_post:
        outcome = publish_due_drafts()
    assert outcome["due_count"] == 0
    mock_post.assert_not_called()


# ── KPI ingestion ────────────────────────────────────────────────────────────

def test_kpi_refresh_upserts_post_metrics_from_meta_insights():
    db_name = "test_publishing_kpi.db"
    main = _reload_main(db_name)
    with TestClient(main.app) as client:
        h = _auth(client)
        _seed_meta_oauth(db_name, page_id="333")
        # Create an already-published draft.
        draft = client.post(
            "/publishing/drafts",
            headers=h,
            json={"title": "Published", "platform": "facebook", "body": "hi"},
        ).json()
        draft_id = draft["id"]

        # Mark it as posted with a known post_id (simulating a prior publish).
        from app.db import SessionLocal
        from app.models import ContentDraft, utc_now
        with SessionLocal() as db:
            d = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
            d.post_id = "333_postid"
            d.post_url = "https://www.facebook.com/333_postid"
            d.published_at = utc_now()
            d.status = "posted"
            db.commit()

        insights_response = httpx.Response(
            200,
            json={
                "data": [
                    {"name": "post_impressions", "values": [{"value": 1200}]},
                    {"name": "post_impressions_unique", "values": [{"value": 900}]},
                    {"name": "post_clicks", "values": [{"value": 35}]},
                    {
                        "name": "post_reactions_by_type_total",
                        "values": [{"value": {"like": 12, "love": 3}}],
                    },
                ]
            },
            request=httpx.Request("GET", "https://graph.facebook.com/v21.0/333_postid/insights"),
        )
        with patch("httpx.get", return_value=insights_response):
            r = client.post("/kpi/refresh", headers=h)

        assert r.status_code == 200
        body = r.json()
        assert body["refreshed_count"] == 1
        record = body["records"][0]
        assert record["impressions"] == 1200
        assert record["reach"] == 900
        assert record["clicks"] == 35
        assert record["engagements"] == 15  # 12 + 3
        assert record["engagement_rate"] == round((15 / 1200) * 100, 2)
