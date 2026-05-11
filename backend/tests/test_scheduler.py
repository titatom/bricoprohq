"""Tests for PR6 in-process scheduler:
- start_scheduler is a no-op when SCHEDULER_ENABLED is unset.
- start_scheduler is idempotent under repeated calls.
- refresh_all_integrations only touches integrations with credentials and
  funnels each one through refresh_source.
- A failing connector does not abort the sweep.
"""

import importlib
import os
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


def _reload_main(db_name: str, env: dict | None = None):
    base = {
        "DATABASE_URL": f"sqlite+pysqlite:///./{db_name}",
        "ADMIN_EMAIL": "admin@bricopro.local",
        "ADMIN_PASSWORD": "admin1234",
        "SECRET_KEY": "test-scheduler-key-aaaaaaaaaaaaaa",
    }
    base.update(env or {})
    for k in ("SCHEDULER_ENABLED", "SCHEDULER_REFRESH_INTERVAL_MINUTES"):
        os.environ.pop(k, None)
    for k, v in base.items():
        os.environ[k] = v
    if os.path.exists(db_name):
        os.remove(db_name)
    from app import main
    importlib.reload(main)
    return main


def test_scheduler_is_disabled_by_default():
    main = _reload_main("test_scheduler_disabled.db")
    from app.workers.scheduler import current_scheduler

    with TestClient(main.app):
        # Lifespan startup runs; the scheduler must NOT be created.
        assert current_scheduler() is None


def test_scheduler_starts_when_enabled_and_is_idempotent():
    _reload_main("test_scheduler_enabled.db", env={"SCHEDULER_ENABLED": "true"})
    from app.workers import scheduler

    first = scheduler.start_scheduler()
    second = scheduler.start_scheduler()
    try:
        assert first is not None
        assert first is second  # idempotent
        assert first.running
    finally:
        scheduler.stop_scheduler()
        assert scheduler.current_scheduler() is None


def test_refresh_all_integrations_skips_unconfigured_providers():
    main = _reload_main("test_scheduler_skip_unconfigured.db")
    with TestClient(main.app) as client:
        # Configure only one integration so the sweep has exactly one target.
        h = main_auth(client)
        client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )

    from app.workers.scheduler import refresh_all_integrations

    request = httpx.Request("POST", "http://immich.local:2283/api/search/metadata")
    response = httpx.Response(200, json={"assets": []}, request=request)
    with patch("httpx.post", return_value=response):
        outcome = refresh_all_integrations()

    assert outcome["providers"] == ["immich"]
    assert outcome["results"] == {"immich": "ok"}


def test_refresh_all_integrations_records_failure_per_provider():
    main = _reload_main("test_scheduler_failure_per_provider.db")
    with TestClient(main.app) as client:
        h = main_auth(client)
        # Configure two integrations; the Immich one will succeed via mock,
        # but the Paperless one points at a host that will not resolve.
        client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"test-key"}'},
        )
        client.put(
            "/integrations/paperless",
            headers=h,
            json={"base_url": "http://paperless.local:9999", "config_json": '{"api_key":"tok"}'},
        )

    from app.workers.scheduler import refresh_all_integrations

    immich_request = httpx.Request("POST", "http://immich.local:2283/api/search/metadata")
    immich_response = httpx.Response(200, json={"assets": []}, request=immich_request)

    def selective_post(url, *args, **kwargs):
        if "immich.local" in str(url):
            return immich_response
        raise httpx.ConnectError("nope", request=httpx.Request("POST", str(url)))

    def selective_get(url, *args, **kwargs):
        if "paperless.local" in str(url):
            raise httpx.ConnectError("nope", request=httpx.Request("GET", str(url)))
        # Be safe with any other GETs (auth + integrations fetch).
        return httpx.Response(200, json={}, request=httpx.Request("GET", str(url)))

    with patch("httpx.post", side_effect=selective_post):
        with patch("httpx.get", side_effect=selective_get):
            outcome = refresh_all_integrations()

    assert set(outcome["providers"]) == {"immich", "paperless"}
    # Immich succeeded; Paperless failed gracefully (without aborting the sweep).
    assert outcome["results"]["immich"] == "ok"
    assert outcome["results"]["paperless"] == "error"


def main_auth(client):
    r = client.post(
        "/auth/login",
        json={"email": "admin@bricopro.local", "password": "admin1234"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
