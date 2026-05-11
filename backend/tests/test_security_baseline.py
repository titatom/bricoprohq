"""Tests for the PR1 security baseline:
- SECRET_KEY resolver behaviour (production guard, dev fallback caching)
- At-rest encryption of integration secrets and OAuth tokens
- OAuth state CSRF tokens persisted in the database
- CORS allowlist driven by APP_BASE_URL / CORS_ALLOWED_ORIGINS
- Login rate limit on /auth/login
"""

import importlib
import os

import pytest
from fastapi.testclient import TestClient

# ── Helpers ──────────────────────────────────────────────────────────────────

def _base_env(db_name: str) -> dict:
    return {
        "DATABASE_URL": f"sqlite+pysqlite:///./{db_name}",
        "ADMIN_EMAIL": "admin@bricopro.local",
        "ADMIN_PASSWORD": "admin1234",
    }


def _reload_main(env: dict | None = None, *, reset_db: bool = True):
    if env:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    db_name = (env or {}).get("DATABASE_URL", "")
    if reset_db and db_name.startswith("sqlite+pysqlite:///./"):
        path = db_name.replace("sqlite+pysqlite:///./", "")
        if os.path.exists(path):
            os.remove(path)

    from app import main, secret_key
    importlib.reload(secret_key)
    importlib.reload(main)
    return main


def _auth(client) -> dict:
    r = client.post(
        "/auth/login",
        json={"email": "admin@bricopro.local", "password": "admin1234"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ── Encryption ───────────────────────────────────────────────────────────────

def test_integration_secrets_are_encrypted_at_rest():
    db_name = "test_security_encrypt.db"
    main = _reload_main(_base_env(db_name) | {"SECRET_KEY": "test-secret-aaaaaaaaaaaaaaaa"})

    with TestClient(main.app) as client:
        h = _auth(client)
        r = client.put(
            "/integrations/immich",
            headers=h,
            json={"base_url": "http://immich.local:2283", "config_json": '{"api_key":"plain-text-key"}'},
        )
        assert r.status_code == 200

    # Read raw config_json directly from SQLite — should NOT contain the cleartext key.
    import sqlite3
    db_path = db_name
    raw = sqlite3.connect(db_path).execute(
        "SELECT config_json FROM integrations WHERE provider = ?", ("immich",)
    ).fetchone()[0]
    assert "plain-text-key" not in raw
    assert raw.startswith("enc:v1:"), f"expected encryption prefix, got {raw[:20]!r}"

    # And the application API still decrypts/masks transparently.
    main = _reload_main(
        {"DATABASE_URL": f"sqlite+pysqlite:///./{db_name}", "SECRET_KEY": "test-secret-aaaaaaaaaaaaaaaa"},
        reset_db=False,
    )
    with TestClient(main.app) as client:
        h = _auth(client)
        r = client.get("/integrations/immich", headers=h)
        assert r.status_code == 200
        assert r.json()["config_fields"]["api_key"] == "••••••••"


def test_legacy_plaintext_config_is_still_readable():
    """Rows written before this feature must continue to work."""
    db_name = "test_security_legacy.db"
    main = _reload_main(_base_env(db_name) | {"SECRET_KEY": "test-secret-bbbbbbbbbbbbbbbb"})

    # Trigger startup_seed so the integrations table is populated.
    with TestClient(main.app):
        pass

    # Force the row to plaintext, simulating data written before encryption was introduced.
    import sqlite3
    conn = sqlite3.connect(db_name)
    conn.execute(
        "UPDATE integrations SET base_url = ?, config_json = ? WHERE provider = ?",
        ("http://immich.local:2283", '{"api_key": "legacy-plaintext"}', "immich"),
    )
    conn.commit()
    conn.close()

    with TestClient(main.app) as client:
        h = _auth(client)
        # Reading still works (decrypt() passes plaintext through unchanged).
        r = client.get("/integrations/immich", headers=h)
        assert r.status_code == 200
        assert r.json()["config_fields"]["api_key"] == "••••••••"


# ── OAuth state ──────────────────────────────────────────────────────────────

def test_oauth_state_persists_in_db_and_blocks_replay():
    db_name = "test_security_oauth_state.db"
    main = _reload_main(_base_env(db_name) | {"SECRET_KEY": "test-secret-cccccccccccccccc"})

    from datetime import datetime

    from app.db import SessionLocal
    from app.models import OAuthState

    with SessionLocal() as db:
        state = main._persist_oauth_state("jobber", db)

    # State row should exist with a future expiry.
    with SessionLocal() as db:
        row = db.query(OAuthState).filter(OAuthState.state == state).first()
        assert row is not None
        assert row.provider == "jobber"
        assert row.expires_at > datetime.utcnow()

    # First consume succeeds; second consume of the same state must fail.
    with SessionLocal() as db:
        assert main._consume_oauth_state(state, "jobber", db) is True
    with SessionLocal() as db:
        assert main._consume_oauth_state(state, "jobber", db) is False


def test_oauth_state_rejects_wrong_provider():
    db_name = "test_security_oauth_state_provider.db"
    main = _reload_main(_base_env(db_name) | {"SECRET_KEY": "test-secret-dddddddddddddddd"})

    from app.db import SessionLocal

    with SessionLocal() as db:
        state = main._persist_oauth_state("jobber", db)

    with SessionLocal() as db:
        assert main._consume_oauth_state(state, "meta", db) is False


def test_oauth_state_rejects_expired_state():
    db_name = "test_security_oauth_state_expiry.db"
    main = _reload_main(_base_env(db_name) | {"SECRET_KEY": "test-secret-eeeeeeeeeeeeeeee"})

    from datetime import datetime, timedelta

    from app.db import SessionLocal
    from app.models import OAuthState

    with SessionLocal() as db:
        state = main._persist_oauth_state("jobber", db)
        row = db.query(OAuthState).filter(OAuthState.state == state).first()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

    with SessionLocal() as db:
        assert main._consume_oauth_state(state, "jobber", db) is False


# ── CORS ─────────────────────────────────────────────────────────────────────

def test_cors_allowlist_uses_app_base_url():
    db_name = "test_security_cors_app_base.db"
    main = _reload_main(
        _base_env(db_name)
        | {
            "SECRET_KEY": "test-secret-ffffffffffffffff",
            "APP_BASE_URL": "https://hq.bricopro.example",
            "CORS_ALLOWED_ORIGINS": "",
        }
    )
    origins, allow_credentials = main._build_cors_origins()
    assert origins == ["https://hq.bricopro.example"]
    assert allow_credentials is True


def test_cors_explicit_extra_origins():
    db_name = "test_security_cors_extra.db"
    main = _reload_main(
        _base_env(db_name)
        | {
            "SECRET_KEY": "test-secret-gggggggggggggggg",
            "APP_BASE_URL": "https://hq.bricopro.example",
            "CORS_ALLOWED_ORIGINS": "https://staff.bricopro.example,https://other.example/",
        }
    )
    origins, allow_credentials = main._build_cors_origins()
    assert origins == [
        "https://hq.bricopro.example",
        "https://staff.bricopro.example",
        "https://other.example",
    ]
    assert allow_credentials is True


def test_cors_wildcard_drops_credentials():
    db_name = "test_security_cors_wildcard.db"
    main = _reload_main(
        _base_env(db_name)
        | {
            "SECRET_KEY": "test-secret-hhhhhhhhhhhhhhhh",
            "APP_BASE_URL": "https://hq.bricopro.example",
            "CORS_ALLOWED_ORIGINS": "*",
        }
    )
    origins, allow_credentials = main._build_cors_origins()
    assert origins == ["*"]
    # Browsers refuse credentialed requests when allow_origin is "*",
    # so the middleware must drop the credentials flag automatically.
    assert allow_credentials is False


# ── SECRET_KEY guard ─────────────────────────────────────────────────────────

def test_secret_key_production_guard_rejects_default():
    from app import secret_key
    importlib.reload(secret_key)

    os.environ["APP_ENV"] = "production"
    os.environ["SECRET_KEY"] = "change-me"
    try:
        with pytest.raises(secret_key.SecretKeyMisconfigured):
            secret_key.resolve_secret_key()
    finally:
        os.environ.pop("APP_ENV", None)
        os.environ.pop("SECRET_KEY", None)


def test_secret_key_explicit_value_is_returned():
    from app import secret_key
    importlib.reload(secret_key)

    os.environ["SECRET_KEY"] = "very-strong-explicit-secret-32chars"
    try:
        assert secret_key.resolve_secret_key() == "very-strong-explicit-secret-32chars"
    finally:
        os.environ.pop("SECRET_KEY", None)


# ── Login rate limit ─────────────────────────────────────────────────────────

def test_login_rate_limit_returns_429_after_threshold():
    db_name = "test_security_rate_limit.db"
    main = _reload_main(
        _base_env(db_name)
        | {
            "SECRET_KEY": "test-secret-iiiiiiiiiiiiiiii",
            "LOGIN_RATE_LIMIT": "3",
            "LOGIN_RATE_LIMIT_WINDOW_SECONDS": "30",
        }
    )

    # Reset the limiter to keep this test independent of others in the run.
    from app.services.rate_limit import default_limiter
    default_limiter().clear()

    with TestClient(main.app) as client:
        # 3 failed attempts allowed within the window.
        for _ in range(3):
            r = client.post(
                "/auth/login",
                json={"email": "admin@bricopro.local", "password": "wrong"},
            )
            assert r.status_code == 401
        # 4th attempt is rate limited.
        r = client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "wrong"},
        )
        assert r.status_code == 429
        assert "Retry-After" in r.headers


def test_login_success_resets_rate_limit_counter():
    db_name = "test_security_rate_limit_reset.db"
    main = _reload_main(
        _base_env(db_name)
        | {
            "SECRET_KEY": "test-secret-jjjjjjjjjjjjjjjj",
            "LOGIN_RATE_LIMIT": "2",
            "LOGIN_RATE_LIMIT_WINDOW_SECONDS": "30",
        }
    )

    from app.services.rate_limit import default_limiter
    default_limiter().clear()

    with TestClient(main.app) as client:
        # 1 bad attempt
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "wrong"},
        ).status_code == 401
        # Successful login should clear the counter
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "admin1234"},
        ).status_code == 200
        # Another bad attempt should still be allowed (counter reset).
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "wrong"},
        ).status_code == 401
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "wrong"},
        ).status_code == 401
        assert client.post(
            "/auth/login",
            json={"email": "admin@bricopro.local", "password": "wrong"},
        ).status_code == 429
