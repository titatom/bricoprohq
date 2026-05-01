import os
import importlib
from fastapi.testclient import TestClient
from unittest.mock import patch

import httpx


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


def test_admin_password_env_change_updates_seeded_user():
    db_name = "test_dash_admin_password_rotate.db"
    app = make_client(db_name)
    with TestClient(app) as client:
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "admin1234"},
        ).status_code == 200

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "new-admin-password"
    from app import main
    importlib.reload(main)

    with TestClient(main.app) as client:
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "admin1234"},
        ).status_code == 401
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "new-admin-password"},
        ).status_code == 200


def test_default_admin_password_does_not_reset_existing_custom_password():
    db_name = "test_dash_admin_password_default_guard.db"
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "custom-admin-password"
    from app import main
    importlib.reload(main)

    with TestClient(main.app) as client:
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "custom-admin-password"},
        ).status_code == 200

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "admin1234"
    importlib.reload(main)

    with TestClient(main.app) as client:
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "admin1234"},
        ).status_code == 401
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "custom-admin-password"},
        ).status_code == 200


def test_login_repairs_stale_configured_admin_password_without_startup():
    db_name = "test_dash_admin_password_login_repair.db"
    app = make_client(db_name)
    with TestClient(app) as client:
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "admin1234"},
        ).status_code == 200

    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///./{db_name}"
    os.environ["ADMIN_EMAIL"] = "admin@bricopro.local"
    os.environ["ADMIN_PASSWORD"] = "new-admin-password"
    from app import main
    importlib.reload(main)

    # Do not enter TestClient as a context manager here. That intentionally skips
    # startup so this verifies login can repair a stale admin row by itself.
    client = TestClient(main.app)
    assert client.post(
        "/auth/login",
        json={"email": "admin@bricopro.local", "password": "new-admin-password"},
    ).status_code == 200
    assert client.post(
        "/auth/login",
        json={"email": "admin@bricopro.local", "password": "admin1234"},
    ).status_code == 401


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
        assert "paperless-gpt" in providers
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


def test_immich_test_endpoint_handles_non_json_response():
    app = make_client("test_dash_immich_non_json.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )
        assert r.status_code == 200

        request = httpx.Request("POST", "http://immich.local:2283/api/search/metadata")
        response = httpx.Response(200, text="Internal Server Error", request=request)
        with patch("httpx.post", return_value=response):
            r = client.post("/integrations/immich/test", headers=h)

        assert r.status_code == 502
        assert r.json()["detail"] == "Immich returned a non-JSON response: Internal Server Error"


def test_immich_test_endpoint_uses_search_metadata():
    app = make_client("test_dash_immich_search.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )

        request = httpx.Request("POST", "http://immich.local:2283/api/search/metadata")
        response = httpx.Response(
            200,
            json={"assets": {"items": [{"id": "asset-1", "originalFileName": "photo.jpg", "type": "IMAGE"}]}},
            request=request,
        )
        with patch("httpx.post", return_value=response) as mock_post:
            r = client.post("/integrations/immich/test", headers=h)

        assert r.status_code == 200
        assert mock_post.call_args.kwargs["json"] == {"page": 1, "size": 6}
        assert mock_post.call_args.kwargs["headers"]["x-api-key"] == "test-key"
        assert r.json()["data"]["recent_assets"][0]["filename"] == "photo.jpg"
        assert r.json()["data"]["recent_assets"][0]["preview_url"] == "/integrations/immich/assets/asset-1/thumbnail"


def test_immich_thumbnail_proxy_uses_api_key():
    app = make_client("test_dash_immich_thumbnail_proxy.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )

        request = httpx.Request(
            "GET",
            "http://immich.local:2283/api/assets/asset-1/thumbnail?size=preview",
        )
        response = httpx.Response(
            200,
            content=b"fake-image",
            headers={"content-type": "image/jpeg"},
            request=request,
        )
        with patch("httpx.get", return_value=response) as mock_get:
            r = client.get("/integrations/immich/assets/asset-1/thumbnail", headers=h)

        assert r.status_code == 200
        assert r.content == b"fake-image"
        assert r.headers["content-type"] == "image/jpeg"
        assert str(mock_get.call_args.args[0]) == "http://immich.local:2283/api/assets/asset-1/thumbnail"
        assert mock_get.call_args.kwargs["params"] == {"size": "preview"}
        assert mock_get.call_args.kwargs["headers"]["x-api-key"] == "test-key"


def test_immich_404_has_actionable_error():
    app = make_client("test_dash_immich_404.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )

        request = httpx.Request("POST", "http://immich.local:2283/api/search/metadata")
        response = httpx.Response(404, json={"message": "Not Found"}, request=request)
        with patch("httpx.post", return_value=response):
            r = client.post("/integrations/immich/test", headers=h)

        assert r.status_code == 502
        assert "Immich HTTP error 404 at /api/search/metadata" in r.json()["detail"]
        assert "check the base URL and service API version" in r.json()["detail"]


def test_paperless_test_endpoint_handles_non_json_response():
    app = make_client("test_dash_paperless_non_json.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.put(
            "/integrations/paperless",
            headers=h,
            json={"base_url": "http://paperless.local:8000", "config_json": '{"api_key":"test-key"}'},
        )
        assert r.status_code == 200

        request = httpx.Request("GET", "http://paperless.local:8000/api/documents/")
        response = httpx.Response(200, text="Internal Server Error", request=request)
        with patch("httpx.get", return_value=response):
            r = client.post("/integrations/paperless/test", headers=h)

        assert r.status_code == 502
        assert r.json()["detail"] == "Paperless-ngx returned a non-JSON response: Internal Server Error"


def test_paperless_gpt_defaults_to_no_auth_documents_endpoint():
    app = make_client("test_dash_paperless_gpt_no_auth.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/paperless-gpt",
            headers=h,
            json={"base_url": "http://paperless-gpt.local:8080", "config_json": "{}"},
        )

        request = httpx.Request("GET", "http://paperless-gpt.local:8080/api/documents")
        response = httpx.Response(
            200,
            json={"documents": [{"id": 1, "title": "Invoice", "tags": ["paperless-gpt"]}]},
            request=request,
        )
        with patch("httpx.get", return_value=response) as mock_get:
            r = client.post("/integrations/paperless-gpt/test", headers=h)

        assert r.status_code == 200
        assert "Authorization" not in mock_get.call_args.kwargs["headers"]
        assert r.json()["data"] == {
            "pending_documents": 1,
            "needs_review": 1,
            "processed_documents": 0,
        }


def test_paperless_gpt_supports_bearer_auth_mode():
    app = make_client("test_dash_paperless_gpt_bearer.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/paperless-gpt",
            headers=h,
            json={
                "base_url": "http://paperless-gpt.local:8080",
                "config_json": '{"auth_mode":"bearer","api_key":"secret-token"}',
            },
        )

        request = httpx.Request("GET", "http://paperless-gpt.local:8080/api/documents")
        response = httpx.Response(200, json={"documents": []}, request=request)
        with patch("httpx.get", return_value=response) as mock_get:
            r = client.post("/integrations/paperless-gpt/test", headers=h)

        assert r.status_code == 200
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_paperless_gpt_base_url_update_takes_effect_with_masked_secret():
    app = make_client("test_dash_paperless_gpt_update_base_url.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/paperless-gpt",
            headers=h,
            json={
                "base_url": "https://bricoprohq.thomasrich.ca",
                "config_json": '{"auth_mode":"bearer","api_key":"secret-token"}',
            },
        )

        update = client.put(
            "/integrations/paperless-gpt",
            headers=h,
            json={
                "base_url": "http://paperless-gpt.local:8080",
                "config_json": '{"auth_mode":"bearer","api_key":"••••••••"}',
            },
        )
        assert update.status_code == 200
        assert update.json()["base_url"] == "http://paperless-gpt.local:8080"
        assert update.json()["config_fields"]["api_key"] == "••••••••"

        request = httpx.Request("GET", "http://paperless-gpt.local:8080/api/documents")
        response = httpx.Response(200, json={"documents": []}, request=request)
        with patch("httpx.get", return_value=response) as mock_get:
            r = client.post("/integrations/paperless-gpt/test", headers=h)

        assert r.status_code == 200
        assert str(mock_get.call_args.args[0]) == "http://paperless-gpt.local:8080/api/documents"
        assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer secret-token"


def test_jobber_base_url_update_takes_effect_with_masked_oauth_secret():
    app = make_client("test_dash_jobber_update_base_url.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://old-jobber-proxy.local/graphql",
                "config_json": '{"client_id":"jobber-client","client_secret":"jobber-secret"}',
            },
        )

        from app.db import SessionLocal
        from app.models import Integration

        db = SessionLocal()
        try:
            jobber = db.query(Integration).filter(Integration.provider == "jobber").first()
            jobber.oauth_access_token = "jobber-access-token"
            db.commit()
        finally:
            db.close()

        update = client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://new-jobber-proxy.local/graphql",
                "config_json": '{"client_id":"jobber-client","client_secret":"••••••••"}',
            },
        )
        assert update.status_code == 200
        assert update.json()["base_url"] == "https://new-jobber-proxy.local/graphql"
        assert update.json()["config_fields"]["client_secret"] == "••••••••"

        request = httpx.Request("POST", "https://new-jobber-proxy.local/graphql")
        response = httpx.Response(200, json={"data": {"jobs": {"nodes": []}}}, request=request)
        with patch("httpx.post", return_value=response) as mock_post:
            r = client.post("/integrations/jobber/test", headers=h)

        assert r.status_code == 200
        assert str(mock_post.call_args.args[0]) == "https://new-jobber-proxy.local/graphql"
        assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer jobber-access-token"


def test_jobber_dashboard_limit_setting_controls_query_size():
    app = make_client("test_dash_jobber_limit_setting.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": '{"client_id":"jobber-client","client_secret":"jobber-secret"}',
            },
        )
        client.put("/settings/dashboard.jobber.limit", headers=h, json={"value": "3"})

        from app.db import SessionLocal
        from app.models import Integration

        db = SessionLocal()
        try:
            jobber = db.query(Integration).filter(Integration.provider == "jobber").first()
            jobber.oauth_access_token = "jobber-access-token"
            db.commit()
        finally:
            db.close()

        request = httpx.Request("POST", "https://api.getjobber.com/api/graphql")
        response = httpx.Response(
            200,
            json={
                "data": {
                    "jobs": {
                        "nodes": [
                            {"title": "Deck repair", "jobStatus": "ACTIVE", "startAt": "2026-05-01T10:00:00Z", "client": {"name": "Alice"}},
                            {"title": "Kitchen quote", "jobStatus": "UPCOMING", "startAt": "2026-05-02T10:00:00Z", "client": {"name": "Bob"}},
                        ]
                    }
                }
            },
            request=request,
        )
        with patch("httpx.post", side_effect=[response, response, response, response]) as mock_post:
            r = client.post("/dashboard/refresh/jobber", headers=h)

        assert r.status_code == 200
        assert "first: 3" in mock_post.call_args.kwargs["json"]["query"]
        payload = client.get("/dashboard", headers=h).json()
        assert payload["jobber"]["data"]["limit"] == 3
        assert payload["jobber"]["data"]["upcoming_jobs"][0]["client"]["name"] == "Alice"
        assert "pending_requests" in payload["jobber"]["data"]
        assert "pending_quotes" in payload["jobber"]["data"]
        assert "pending_invoices" in payload["jobber"]["data"]


def test_jobber_502_reports_actionable_error_without_html_dump():
    app = make_client("test_dash_jobber_502.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": '{"client_id":"jobber-client","client_secret":"jobber-secret"}',
            },
        )

        from app.db import SessionLocal
        from app.models import Integration

        db = SessionLocal()
        try:
            jobber = db.query(Integration).filter(Integration.provider == "jobber").first()
            jobber.oauth_access_token = "jobber-access-token"
            db.commit()
        finally:
            db.close()

        request = httpx.Request("POST", "https://api.getjobber.com/api/graphql")
        response = httpx.Response(
            502,
            headers={"content-type": "text/html; charset=UTF-8"},
            content=b"<!DOCTYPE html><html><head><title>thomasrich.ca | 502: Bad gateway</title></head><body>Cloudflare</body></html>",
            request=request,
        )
        with patch("httpx.post", return_value=response):
            r = client.post("/integrations/jobber/test", headers=h)

        assert r.status_code == 502
        detail = r.json()["detail"]
        assert "Jobber HTTP error 502 at /api/graphql" in detail
        assert "thomasrich.ca | 502: Bad gateway" in detail
        assert "<!DOCTYPE html>" not in detail


def test_jobber_dashboard_refresh_caches_error_when_primary_query_fails():
    app = make_client("test_dash_jobber_dashboard_502.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/jobber",
            headers=h,
            json={
                "base_url": "https://api.getjobber.com/api/graphql",
                "config_json": '{"client_id":"jobber-client","client_secret":"jobber-secret"}',
            },
        )

        from app.db import SessionLocal
        from app.models import Integration

        db = SessionLocal()
        try:
            jobber = db.query(Integration).filter(Integration.provider == "jobber").first()
            jobber.oauth_access_token = "jobber-access-token"
            db.commit()
        finally:
            db.close()

        request = httpx.Request("POST", "https://api.getjobber.com/api/graphql")
        response = httpx.Response(502, json={"message": "Bad gateway"}, request=request)
        with patch("httpx.post", return_value=response):
            r = client.post("/dashboard/refresh/jobber", headers=h)

        assert r.status_code == 200
        payload = client.get("/dashboard", headers=h).json()
        assert payload["jobber"]["status"] == "error"
        assert "Jobber HTTP error 502 at /api/graphql" in payload["jobber"]["data"]["error"]


def test_paperless_gpt_401_has_actionable_error():
    app = make_client("test_dash_paperless_gpt_401.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/paperless-gpt",
            headers=h,
            json={
                "base_url": "http://paperless-gpt.local:8080",
                "config_json": '{"auth_mode":"bearer","api_key":"bad-token"}',
            },
        )

        request = httpx.Request("GET", "http://paperless-gpt.local:8080/api/documents")
        response = httpx.Response(401, json={"message": "Unauthorized"}, request=request)
        with patch("httpx.get", return_value=response):
            r = client.post("/integrations/paperless-gpt/test", headers=h)

        assert r.status_code == 502
        assert "Paperless-GPT HTTP error 401 at /api/documents" in r.json()["detail"]
        assert "check the API key/auth mode" in r.json()["detail"]


def test_paperless_gpt_404_has_actionable_error():
    app = make_client("test_dash_paperless_gpt_404.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/paperless-gpt",
            headers=h,
            json={"base_url": "http://paperless-gpt.local:8080", "config_json": "{}"},
        )

        request = httpx.Request("GET", "http://paperless-gpt.local:8080/api/documents")
        response = httpx.Response(404, json={"message": "Not Found"}, request=request)
        with patch("httpx.get", return_value=response):
            r = client.post("/integrations/paperless-gpt/test", headers=h)

        assert r.status_code == 502
        assert "Paperless-GPT HTTP error 404 at /api/documents" in r.json()["detail"]
        assert "check the base URL and service API version" in r.json()["detail"]


def test_paperless_dashboard_filters_ai_processed_documents():
    app = make_client("test_dash_paperless_tag.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/paperless",
            headers=h,
            json={"base_url": "http://paperless.local:8000", "config_json": '{"api_key":"test-key"}'},
        )

        tag_request = httpx.Request("GET", "http://paperless.local:8000/api/tags/")
        docs_request = httpx.Request("GET", "http://paperless.local:8000/api/documents/")
        responses = [
            httpx.Response(200, json={"results": [{"id": 7, "name": "ai-processed"}]}, request=tag_request),
            httpx.Response(
                200,
                json={
                    "count": 1,
                    "results": [{"id": 42, "title": "Invoice ABC", "added": "2026-04-30T12:00:00Z"}],
                },
                request=docs_request,
            ),
        ]

        with patch("httpx.get", side_effect=responses) as mock_get:
            r = client.post("/dashboard/refresh/paperless", headers=h)

        assert r.status_code == 200
        params = mock_get.call_args_list[1].kwargs["params"]
        assert params["tags__id__all"] == 7
        payload = client.get("/dashboard", headers=h).json()
        docs = payload["paperless"]["data"]["recent_documents"]
        assert docs == [
            {
                "id": 42,
                "title": "Invoice ABC",
                "added": "2026-04-30T12:00:00Z",
                "document_url": "http://paperless.local:8000/documents/42/details",
            }
        ]
        assert payload["paperless"]["data"]["tag"] == "ai-processed"


def test_paperless_dashboard_tag_setting_is_customizable():
    app = make_client("test_dash_paperless_tag_setting.db")
    with TestClient(app) as client:
        h = auth(client)
        client.put(
            "/integrations/paperless",
            headers=h,
            json={"base_url": "http://paperless.local:8000", "config_json": '{"api_key":"test-key"}'},
        )
        client.put("/settings/dashboard.paperless.tag", headers=h, json={"value": "tax"})

        tag_request = httpx.Request("GET", "http://paperless.local:8000/api/tags/")
        docs_request = httpx.Request("GET", "http://paperless.local:8000/api/documents/")
        responses = [
            httpx.Response(200, json={"results": [{"id": 9, "name": "tax"}]}, request=tag_request),
            httpx.Response(200, json={"count": 0, "results": []}, request=docs_request),
        ]

        with patch("httpx.get", side_effect=responses) as mock_get:
            r = client.post("/dashboard/refresh/paperless", headers=h)

        assert r.status_code == 200
        assert mock_get.call_args_list[0].kwargs["params"]["query"] == "tax"
        assert mock_get.call_args_list[1].kwargs["params"]["tags__id__all"] == 9
        assert client.get("/dashboard", headers=h).json()["paperless"]["data"]["tag"] == "tax"


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
        loc = r.headers.get("location", "")
        assert "accounts.google.com" in loc
        assert "calendar.readonly" in loc
        assert "business.manage" in loc


def test_oauth_authorize_json_mode_returns_authorization_url():
    """Settings UI can fetch the OAuth URL with bearer auth before browser redirect."""
    app = make_client("test_dash_oauth_json.db")
    with TestClient(app, follow_redirects=False) as client:
        h = auth(client)
        client.put(
            "/integrations/jobber",
            headers=h,
            json={"base_url": "", "config_json": '{"client_id":"test-jobber-id","client_secret":"test-jobber-secret"}'},
        )
        r = client.get("/integrations/jobber/oauth/authorize?mode=json", headers=h)
        assert r.status_code == 200
        url = r.json()["authorization_url"]
        assert "api.getjobber.com/api/oauth/authorize" in url
        assert "client_id=test-jobber-id" in url
        assert "state=" in url


def test_meta_oauth_authorize_redirects():
    """Meta authorize should redirect to facebook.com with correct scopes."""
    app = make_client("test_dash_meta_auth.db")
    with TestClient(app, follow_redirects=False) as client:
        h = auth(client)
        client.put(
            "/integrations/meta",
            headers=h,
            json={"base_url": "", "config_json": '{"client_id":"test-meta-id","client_secret":"test-meta-secret"}'},
        )
        r = client.get("/integrations/meta/oauth/authorize", headers=h)
        assert r.status_code in (302, 307)
        loc = r.headers.get("location", "")
        assert "facebook.com" in loc
        assert "pages_manage_posts" in loc


def test_google_business_oauth_authorize_uses_shared_google_config():
    """Google Business authorize uses the shared Google Calendar OAuth config."""
    app = make_client("test_dash_gbp_auth.db")
    with TestClient(app, follow_redirects=False) as client:
        h = auth(client)
        client.put(
            "/integrations/google_calendar",
            headers=h,
            json={"base_url": "", "config_json": '{"client_id":"test-gid","client_secret":"test-gsecret"}'},
        )
        r = client.get("/integrations/google_business/oauth/authorize", headers=h)
        assert r.status_code in (302, 307)
        loc = r.headers.get("location", "")
        assert "accounts.google.com" in loc
        assert "calendar.readonly" in loc
        assert "business.manage" in loc


def test_google_oauth_callback_syncs_google_integrations():
    """A single Google OAuth callback should mark Calendar and Business connected."""
    app = make_client("test_dash_google_oauth_shared.db")
    with TestClient(app, follow_redirects=False) as client:
        h = auth(client)
        client.put(
            "/integrations/google_calendar",
            headers=h,
            json={"base_url": "", "config_json": '{"client_id":"test-gid","client_secret":"test-gsecret"}'},
        )
        r = client.get("/integrations/google_calendar/oauth/authorize", headers=h)
        assert r.status_code in (302, 307)
        loc = r.headers.get("location", "")
        state = loc.split("state=")[1].split("&")[0]

        token_response = httpx.Response(
            200,
            json={"access_token": "google-access", "refresh_token": "google-refresh", "expires_in": 3600},
            request=httpx.Request("POST", "https://oauth2.googleapis.com/token"),
        )
        with patch("httpx.post", return_value=token_response):
            callback = client.get(
                f"/integrations/google_calendar/oauth/callback?code=test-code&state={state}"
            )

        assert callback.status_code in (302, 307)
        integrations = {i["provider"]: i for i in client.get("/integrations", headers=h).json()}
        assert integrations["google_calendar"]["oauth_connected"] is True
        assert integrations["google_business"]["oauth_connected"] is True

        r = client.post("/integrations/google_business/oauth/disconnect", headers=h)
        assert r.status_code == 200
        integrations = {i["provider"]: i for i in client.get("/integrations", headers=h).json()}
        assert integrations["google_calendar"]["oauth_connected"] is False
        assert integrations["google_business"]["oauth_connected"] is False


def test_meta_and_google_business_seeded():
    """meta and google_business should appear in the integrations list after startup."""
    app = make_client("test_dash_social_seed.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.get("/integrations", headers=h)
        assert r.status_code == 200
        providers = [i["provider"] for i in r.json()]
        assert "meta" in providers
        assert "google_business" in providers


def test_meta_oauth_disconnect():
    app = make_client("test_dash_meta_disc.db")
    with TestClient(app) as client:
        h = auth(client)
        r = client.post("/integrations/meta/oauth/disconnect", headers=h)
        assert r.status_code == 200
        assert r.json()["disconnected"] is True


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
