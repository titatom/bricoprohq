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


# ── OpenRouter image generation ───────────────────────────────────────────────

def test_openrouter_image_gen_images_field():
    """OpenRouter image gen succeeds when response uses the message.images[] format."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Here is your image.",
                "images": [{
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="
                    }
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        result = _generate_image_openrouter(
            "sk-or-test", "", "google/gemini-2.5-flash-image",
            "A sunset over mountains", "1024x1024", "standard"
        )

    assert result["image_b64"] == "iVBORw0KGgoAAAANSUhEUg=="
    assert result["image_url"] == ""
    assert result["model"] == "google/gemini-2.5-flash-image"
    assert result["size"] == "1024x1024"

    call_body = mock_post.call_args[1]["json"]
    assert call_body["modalities"] == ["image", "text"]
    assert call_body["image_config"] == {"aspect_ratio": "1:1"}


def test_openrouter_image_gen_content_fallback():
    """OpenRouter image gen succeeds with legacy content[] format (fallback)."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="
                    }
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        result = _generate_image_openrouter(
            "sk-or-test", "", "black-forest-labs/flux.2-pro",
            "A cat in space", "1792x1024", "standard"
        )

    assert result["image_b64"] == "/9j/4AAQSkZJRg=="
    assert result["image_url"] == ""


def test_openrouter_image_gen_remote_url():
    """OpenRouter image gen returns image_url when response has an HTTP URL."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Image generated.",
                "images": [{
                    "type": "image_url",
                    "image_url": {
                        "url": "https://cdn.openrouter.ai/images/abc123.png"
                    }
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        result = _generate_image_openrouter(
            "sk-or-test", "", "some-model",
            "A landscape", "1024x1024", "standard"
        )

    assert result["image_b64"] == ""
    assert result["image_url"] == "https://cdn.openrouter.ai/images/abc123.png"


def test_openrouter_image_gen_no_image_data_raises():
    """OpenRouter image gen raises AIError when no image data is in response."""
    from app.services.ai import _generate_image_openrouter, AIError

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "I cannot generate images."
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        try:
            _generate_image_openrouter(
                "sk-or-test", "", "text-only-model",
                "A sunset", "1024x1024", "standard"
            )
            assert False, "Should have raised AIError"
        except AIError as e:
            assert "did not return image data" in str(e)


def test_openrouter_image_gen_aspect_ratio_mapping():
    """Verify size-to-aspect_ratio mapping is sent in image_config."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "images": [{
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"}
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        _generate_image_openrouter(
            "sk-or-test", "", "model",
            "test", "1024x1792", "hd"
        )

    call_body = mock_post.call_args[1]["json"]
    assert call_body["image_config"] == {"aspect_ratio": "9:16"}


def test_openrouter_image_gen_no_aspect_for_unknown_size():
    """No image_config sent when size doesn't map to a known aspect ratio."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "images": [{
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAAA"}
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        _generate_image_openrouter(
            "sk-or-test", "", "model",
            "test", "512x512", "standard"
        )

    call_body = mock_post.call_args[1]["json"]
    assert "image_config" not in call_body


def test_openrouter_image_gen_image_only_model_modalities():
    """Image-only models (e.g. Flux) should use modalities: ['image'] only."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "images": [{
                    "image_url": {"url": "data:image/png;base64,AAAA"}
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        _generate_image_openrouter(
            "sk-or-test", "", "black-forest-labs/flux.2-pro",
            "test", "1024x1024", "standard"
        )

    call_body = mock_post.call_args[1]["json"]
    assert call_body["modalities"] == ["image"]


def test_openrouter_image_gen_text_and_image_model_modalities():
    """Multimodal models (e.g. Gemini) should use modalities: ['image', 'text']."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Here is your image.",
                "images": [{
                    "image_url": {"url": "data:image/png;base64,AAAA"}
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        _generate_image_openrouter(
            "sk-or-test", "", "google/gemini-2.5-flash-image",
            "test", "1024x1024", "standard"
        )

    call_body = mock_post.call_args[1]["json"]
    assert call_body["modalities"] == ["image", "text"]


def test_openrouter_image_gen_no_max_tokens():
    """Image generation requests should NOT include max_tokens."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "images": [{
                    "image_url": {"url": "data:image/png;base64,AAAA"}
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        _generate_image_openrouter(
            "sk-or-test", "", "google/gemini-2.5-flash-image",
            "test", "1024x1024", "standard"
        )

    call_body = mock_post.call_args[1]["json"]
    assert "max_tokens" not in call_body


def test_openrouter_image_gen_content_string_data_uri():
    """Handle response where content is a string containing a data URI directly."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "data:image/png;base64,dGVzdGRhdGE="
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        result = _generate_image_openrouter(
            "sk-or-test", "", "some-model",
            "A test", "1024x1024", "standard"
        )

    assert result["image_b64"] == "dGVzdGRhdGE="
    assert result["image_url"] == ""


def test_openrouter_image_gen_content_string_http_url():
    """Handle response where content is a plain HTTP URL string."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "https://cdn.openrouter.ai/generated/img123.png"
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        result = _generate_image_openrouter(
            "sk-or-test", "", "some-model",
            "A test", "1024x1024", "standard"
        )

    assert result["image_b64"] == ""
    assert result["image_url"] == "https://cdn.openrouter.ai/generated/img123.png"


def test_openrouter_image_gen_images_direct_url_string():
    """Handle response where images[] contains direct URL strings."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Generated!",
                "images": [
                    "data:image/png;base64,aW1hZ2VkYXRh"
                ]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        result = _generate_image_openrouter(
            "sk-or-test", "", "some-model",
            "A test", "1024x1024", "standard"
        )

    assert result["image_b64"] == "aW1hZ2VkYXRh"


def test_openrouter_image_gen_images_url_key_shorthand():
    """Handle response where images[] items use 'url' key directly (no nested image_url)."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{
            "message": {
                "role": "assistant",
                "images": [{
                    "url": "data:image/jpeg;base64,anBlZ2RhdGE="
                }]
            }
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        result = _generate_image_openrouter(
            "sk-or-test", "", "some-model",
            "A test", "1024x1024", "standard"
        )

    assert result["image_b64"] == "anBlZ2RhdGE="


def test_openrouter_image_gen_data_array_format():
    """Handle response with top-level data[] array (images/generations style)."""
    from app.services.ai import _generate_image_openrouter

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": ""}}],
        "data": [{
            "b64_json": "dG9wbGV2ZWxkYXRh",
            "revised_prompt": "enhanced prompt"
        }]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.post", return_value=mock_resp):
        result = _generate_image_openrouter(
            "sk-or-test", "", "some-model",
            "A test", "1024x1024", "standard"
        )

    assert result["image_b64"] == "dG9wbGV2ZWxkYXRh"
    assert result["revised_prompt"] == "enhanced prompt"
