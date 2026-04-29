"""
Tests for AI generation, test-connection endpoint, and settings persistence.
Uses unittest.mock to avoid calling real LLM APIs.
"""
import json
import os
import importlib
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def make_client(db_name="test_ai.db"):
    # Always start from a clean database to avoid inter-test state leakage
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


# ── Settings persistence ──────────────────────────────────────────────────────

def test_settings_persist_across_requests():
    """Settings written via PUT /settings/:key are returned on next GET."""
    app = make_client("test_ai_settings.db")
    with TestClient(app) as c:
        h = auth(c)
        c.put("/settings/ai_provider", headers=h, json={"value": "openrouter"})
        c.put("/settings/ai_api_key",  headers=h, json={"value": "sk-or-test-key"})
        c.put("/settings/ai_model",    headers=h, json={"value": "openai/gpt-4o-mini"})
        c.put("/settings/ai_base_url", headers=h, json={"value": "https://openrouter.ai/api/v1"})

        r = c.get("/settings", headers=h)
        assert r.status_code == 200
        vals = {s["key"]: s["value"] for s in r.json()}
        assert vals["ai_provider"] == "openrouter"
        assert vals["ai_model"]    == "openai/gpt-4o-mini"
        assert vals["ai_base_url"] == "https://openrouter.ai/api/v1"
        # Key is stored (value may be redacted in display but present)
        assert "ai_api_key" in vals


def test_settings_overwrite_not_duplicate():
    """Calling PUT /settings/:key twice replaces the value, no duplicate rows."""
    app = make_client("test_ai_overwrite.db")
    with TestClient(app) as c:
        h = auth(c)
        c.put("/settings/ai_provider", headers=h, json={"value": "openai"})
        c.put("/settings/ai_provider", headers=h, json={"value": "ollama"})

        r = c.get("/settings", headers=h)
        vals = {s["key"]: s["value"] for s in r.json()}
        assert vals["ai_provider"] == "ollama"
        # Exactly one row for this key
        all_keys = [s["key"] for s in r.json()]
        assert all_keys.count("ai_provider") == 1


# ── AI generate — no provider configured ─────────────────────────────────────

def test_social_generate_template_fallback_when_no_provider():
    """Without a provider configured, /social/generate returns a template draft with ai_used=False."""
    app = make_client("test_ai_noprov.db")
    with TestClient(app) as c:
        h = auth(c)
        r = c.post("/social/generate", headers=h, json={
            "service_category": "Peinture intérieure",
            "platform": "facebook",
            "language": "fr",
            "tone": "professional",
            "job_description": "Salon repaint",
            "city": "Montréal",
            "cta": "request_quote",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "draft_id" in data
        assert "main_copy" in data
        assert data["ai_used"] is False


# ── AI generate — OpenRouter mocked ──────────────────────────────────────────

MOCK_AI_RESPONSE = {
    "main_copy":       "Voici un beau texte de test pour Bricopro à Montréal.",
    "short_variation": "Bricopro à Montréal — professionnels de confiance!",
    "hashtags":        "#montreal #bricopro #renovation",
    "cta_text":        "Demandez votre soumission gratuite.",
    "notes":           "Review before posting.",
}


def _make_mock_httpx_response(body: dict, status: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": json.dumps(body)}}]
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_social_generate_with_openrouter(tmp_path):
    app = make_client("test_ai_openrouter.db")
    with TestClient(app) as c:
        h = auth(c)
        # Configure OpenRouter in settings
        c.put("/settings/ai_provider", headers=h, json={"value": "openrouter"})
        c.put("/settings/ai_api_key",  headers=h, json={"value": "sk-or-test"})
        c.put("/settings/ai_base_url", headers=h, json={"value": "https://openrouter.ai/api/v1"})
        c.put("/settings/ai_model",    headers=h, json={"value": "openai/gpt-4o-mini"})

        with patch("httpx.post", return_value=_make_mock_httpx_response(MOCK_AI_RESPONSE)):
            r = c.post("/social/generate", headers=h, json={
                "service_category": "Peinture intérieure",
                "platform": "instagram",
                "language": "fr",
                "tone": "friendly",
                "job_description": "Repainted a bedroom",
                "city": "Montréal",
                "cta": "request_quote",
            })

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ai_used"] is True
        assert data["main_copy"] == MOCK_AI_RESPONSE["main_copy"]
        assert data["draft_id"] is not None


def test_social_generate_with_openai(tmp_path):
    app = make_client("test_ai_openai.db")
    with TestClient(app) as c:
        h = auth(c)
        c.put("/settings/ai_provider", headers=h, json={"value": "openai"})
        c.put("/settings/ai_api_key",  headers=h, json={"value": "sk-test-openai"})
        c.put("/settings/ai_model",    headers=h, json={"value": "gpt-4o-mini"})

        with patch("httpx.post", return_value=_make_mock_httpx_response(MOCK_AI_RESPONSE)):
            r = c.post("/social/generate", headers=h, json={
                "service_category": "Réparation de gypse",
                "platform": "facebook",
                "language": "en",
                "tone": "professional",
                "job_description": "Fixed drywall cracks",
                "city": "Montréal",
                "cta": "call_message",
            })

        assert r.status_code == 200
        data = r.json()
        assert data["ai_used"] is True
        assert "draft_id" in data


# ── AI test connection ────────────────────────────────────────────────────────

def test_ai_test_endpoint_not_configured():
    app = make_client("test_ai_testconn_empty.db")
    with TestClient(app) as c:
        h = auth(c)
        r = c.post("/ai/test", headers=h)
        assert r.status_code == 400
        assert "No AI provider" in r.json()["detail"]


def test_ai_test_endpoint_success():
    app = make_client("test_ai_testconn_ok.db")
    with TestClient(app) as c:
        h = auth(c)
        c.put("/settings/ai_provider", headers=h, json={"value": "openrouter"})
        c.put("/settings/ai_api_key",  headers=h, json={"value": "sk-or-test"})

        ping_resp = MagicMock()
        ping_resp.status_code = 200
        ping_resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"ok": True, "message": "Bricopro HQ connection test successful"})}}]
        }
        ping_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=ping_resp):
            r = c.post("/ai/test", headers=h)

        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "successful" in data["message"].lower()
