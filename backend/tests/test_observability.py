"""Tests for PR4 observability primitives:
- Per-request X-Request-Id propagation + generation
- JSON log formatter surfaces extras + request_id
- /readyz returns ok/not_ready with structured checks
- /version returns the configured build info
- /metrics is gated by METRICS_ENABLED and renders Prometheus text on demand
"""

import importlib
import json
import logging
import os
import re
from io import StringIO

from fastapi.testclient import TestClient


def _reload_main(db_name: str, env: dict | None = None):
    base = {
        "DATABASE_URL": f"sqlite+pysqlite:///./{db_name}",
        "ADMIN_EMAIL": "admin@bricopro.local",
        "ADMIN_PASSWORD": "admin1234",
        "SECRET_KEY": "test-observability-key-aaaaaaaaaa",
    }
    base.update(env or {})
    for k, v in base.items():
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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_request_id_is_generated_when_missing_and_returned():
    main = _reload_main("test_obs_request_id.db")
    with TestClient(main.app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        rid = r.headers.get("x-request-id")
        assert rid
        # Looks like a hex token (uuid4().hex)
        assert re.fullmatch(r"[0-9a-f]{32}", rid)


def test_request_id_is_preserved_when_supplied_by_caller():
    main = _reload_main("test_obs_request_id_supplied.db")
    with TestClient(main.app) as client:
        supplied = "deadbeefcafebabedeadbeefcafebabe"
        r = client.get("/health", headers={"X-Request-Id": supplied})
        assert r.headers.get("x-request-id") == supplied


def test_json_log_formatter_includes_request_id_and_extras(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    from app.services.observability import (
        JsonFormatter,
        set_request_id,
    )

    stream = StringIO()
    logger = logging.getLogger("bricopro.test")
    logger.handlers = []
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False

    set_request_id("test-rid-123")
    try:
        logger.info("hello", extra={"provider": "immich", "upstream_status": 500})
    finally:
        set_request_id("")

    line = stream.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["message"] == "hello"
    assert payload["level"] == "info"
    assert payload["request_id"] == "test-rid-123"
    assert payload["provider"] == "immich"
    assert payload["upstream_status"] == 500


def test_readyz_returns_ok_when_seeded():
    main = _reload_main("test_obs_readyz.db")
    with TestClient(main.app) as client:
        r = client.get("/readyz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["seed_admin"] == "ok"


def test_readyz_returns_503_when_admin_missing():
    main = _reload_main("test_obs_readyz_missing_admin.db")
    # Bring up the app once so the table is created, then drop the seeded admin.
    with TestClient(main.app):
        pass

    import sqlite3
    sqlite3.connect("test_obs_readyz_missing_admin.db").execute("DELETE FROM users").connection.commit()

    # Recreate the engine to drop any cached state, but skip startup_seed.
    client = TestClient(main.app)
    r = client.get("/readyz")
    assert r.status_code == 503
    body = r.json()["detail"]
    assert body["status"] == "not_ready"
    assert body["checks"]["seed_admin"] == "missing"


def test_version_endpoint_reports_configured_values():
    main = _reload_main(
        "test_obs_version.db",
        env={"APP_VERSION": "1.2.3-test", "GIT_SHA": "abc1234"},
    )
    with TestClient(main.app) as client:
        r = client.get("/version")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] == "1.2.3-test"
        assert body["git_sha"] == "abc1234"


def test_metrics_is_404_when_disabled():
    main = _reload_main("test_obs_metrics_off.db", env={"METRICS_ENABLED": "false"})
    with TestClient(main.app) as client:
        r = client.get("/metrics")
        assert r.status_code == 404


def test_metrics_renders_prometheus_when_enabled():
    main = _reload_main(
        "test_obs_metrics_on.db",
        env={"METRICS_ENABLED": "true"},
    )
    with TestClient(main.app) as client:
        # Generate a couple of requests so counters move.
        for _ in range(3):
            client.get("/health")
        r = client.get("/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        body = r.text
        assert "bricoprohq_http_requests_total" in body
        # Health endpoint shows up under its template path.
        assert 'path="/health"' in body
