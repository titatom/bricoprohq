"""Tests for PR5 codebase health changes:
- Every social-studio and draft endpoint validates via a Pydantic schema
  (no more `payload: dict`), so bad payloads come back as HTTP 422 with a
  precise error message instead of being silently coerced.
- Partial update semantics on PUT /publishing/drafts/{id}.
- /social/image-presets round-trips through SaveImagePresetsIn.
"""

import importlib
import json
import os
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient


def _reload_main(db_name: str, env: dict | None = None):
    base = {
        "DATABASE_URL": f"sqlite+pysqlite:///./{db_name}",
        "ADMIN_EMAIL": "admin@bricopro.local",
        "ADMIN_PASSWORD": "admin1234",
        "SECRET_KEY": "test-codebase-health-key-aaaaaaaa",
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


def test_social_generate_image_rejects_missing_prompt_and_preset():
    main = _reload_main("test_codebase_gen_image_validation.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        # Both prompt and preset empty -> 400 (the only validation that lives
        # in the route handler, not the schema, since either field is
        # individually optional).
        r = client.post("/social/generate-image", headers=h, json={})
        assert r.status_code == 400


def test_social_generate_image_rejects_wrong_types():
    main = _reload_main("test_codebase_gen_image_types.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        # asset_ids must be a list of strings.
        r = client.post(
            "/social/generate-image",
            headers=h,
            json={"prompt": "hello", "asset_ids": "not-a-list"},
        )
        assert r.status_code == 422


def test_save_image_presets_round_trips_typed_payload():
    main = _reload_main("test_codebase_image_presets.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        body = {
            "presets": [
                {"id": "p1", "name": "Hero", "prompt": "Use natural light.", "editable": True},
                {"id": "p2", "name": "Detail shot", "prompt": "Macro of trim.", "editable": False},
            ]
        }
        r = client.put("/social/image-presets", headers=h, json=body)
        assert r.status_code == 200
        out = r.json()
        assert {p["id"] for p in out} == {"p1", "p2"}
        # GET returns the same payload.
        got = client.get("/social/image-presets", headers=h).json()
        assert {p["id"] for p in got} == {"p1", "p2"}


def test_save_image_presets_rejects_missing_required_fields():
    main = _reload_main("test_codebase_image_presets_invalid.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        r = client.put(
            "/social/image-presets",
            headers=h,
            json={"presets": [{"name": "missing id and prompt"}]},
        )
        assert r.status_code == 422


def test_update_draft_partial_update_keeps_unchanged_fields():
    main = _reload_main("test_codebase_draft_partial.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        created = client.post(
            "/publishing/drafts",
            headers=h,
            json={
                "title": "Original",
                "platform": "facebook",
                "body": "Original body",
                "hashtags": "#orig",
            },
        ).json()
        draft_id = created["id"]

        # Only update the title — body and hashtags should survive.
        r = client.put(
            f"/publishing/drafts/{draft_id}",
            headers=h,
            json={"title": "Updated"},
        )
        assert r.status_code == 200

        drafts = client.get("/publishing/drafts", headers=h).json()
        draft = next(d for d in drafts if d["id"] == draft_id)
        assert draft["title"] == "Updated"
        assert draft["body"] == "Original body"
        assert draft["hashtags"] == "#orig"


def test_update_draft_rejects_invalid_status():
    main = _reload_main("test_codebase_draft_invalid_status.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        created = client.post(
            "/publishing/drafts",
            headers=h,
            json={"title": "X", "platform": "facebook"},
        ).json()
        r = client.put(
            f"/publishing/drafts/{created['id']}",
            headers=h,
            json={"status": "not-a-real-status"},
        )
        assert r.status_code == 422


def test_upload_generated_image_validates_payload():
    main = _reload_main("test_codebase_upload_validates.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        # Passing a non-string for album_id triggers 422 from Pydantic.
        r = client.post(
            "/social/generated-images/deadbeef/upload-to-immich",
            headers=h,
            json={"album_id": ["not", "a", "string"]},
        )
        assert r.status_code == 422


def test_social_candidates_accepts_typed_payload_and_defaults():
    main = _reload_main("test_codebase_social_candidates.db")
    with TestClient(main.app) as client:
        h = _auth(client)
        r = client.post("/social/candidates", headers=h, json={})
        assert r.status_code == 200
        body = r.json()
        # Defaults from SocialCandidatesIn must show up.
        assert body["album_id"] == "recent-work"
        assert body["candidates"][0]["service_category"] == "Exterior painting"
