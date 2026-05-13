import os
import json
from types import SimpleNamespace

import httpx

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test_social_publisher.db")

from app.services import social_publisher as publisher


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text="", content=b"", headers=None):
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {}

    @property
    def is_success(self):
        return self.status_code < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.is_success:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("GET", "http://test.local"),
                response=httpx.Response(self.status_code),
            )


class FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class FakeDb:
    def __init__(self, integration):
        self.integration = integration

    def query(self, model):
        return FakeQuery(self.integration)


def test_instagram_login_carousel_uses_json_bearer(monkeypatch):
    responses = [
        FakeResponse({"id": "item-1"}),
        FakeResponse({"id": "item-2"}),
        FakeResponse({"id": "carousel-1"}),
        FakeResponse({"id": "media-1"}),
    ]
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(publisher.httpx, "post", fake_post)
    monkeypatch.setattr(publisher, "_get_instagram_token", lambda db: "ig-token")
    monkeypatch.setattr(
        publisher,
        "_prepare_public_image",
        lambda asset_id, db, app_base_url, instagram_compatible=False: f"https://app.test/{asset_id}.jpg",
    )

    result = publisher.post_to_instagram(
        "ig-user",
        "caption",
        ["asset-1", "asset-2"],
        object(),
        "page-token",
        "https://app.test",
    )

    assert result == "media-1"
    first_item_kwargs = calls[0][1]
    assert calls[0][0] == "https://graph.instagram.com/v21.0/ig-user/media"
    assert first_item_kwargs["headers"] == {"Authorization": "Bearer ig-token"}
    assert first_item_kwargs["json"] == {
        "image_url": "https://app.test/asset-1.jpg",
        "is_carousel_item": True,
    }
    assert "params" not in first_item_kwargs
    assert "data" not in first_item_kwargs


def test_legacy_instagram_carousel_keeps_form_encoded_page_token(monkeypatch):
    responses = [
        FakeResponse({"id": "item-1"}),
        FakeResponse({"id": "item-2"}),
        FakeResponse({"id": "carousel-1"}),
        FakeResponse({"id": "media-1"}),
    ]
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(publisher.httpx, "post", fake_post)
    monkeypatch.setattr(publisher, "_get_instagram_token", lambda db: None)
    monkeypatch.setattr(
        publisher,
        "_prepare_public_image",
        lambda asset_id, db, app_base_url, instagram_compatible=False: f"https://app.test/{asset_id}.jpg",
    )

    result = publisher.post_to_instagram(
        "ig-user",
        "caption",
        ["asset-1", "asset-2"],
        object(),
        "page-token",
        "https://app.test",
    )

    assert result == "media-1"
    first_item_kwargs = calls[0][1]
    assert calls[0][0] == "https://graph.facebook.com/v21.0/ig-user/media"
    assert first_item_kwargs["params"] == {"access_token": "page-token"}
    assert first_item_kwargs["data"] == {
        "image_url": "https://app.test/asset-1.jpg",
        "is_carousel_item": "true",
    }
    assert "headers" not in first_item_kwargs
    assert "json" not in first_item_kwargs


def test_instagram_public_image_uses_immich_jpeg_preview_for_non_jpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(publisher, "PUBLISH_ASSETS_DIR", tmp_path)
    get_calls = []

    def fake_get(url, **kwargs):
        get_calls.append((url, kwargs))
        if url.endswith("/original"):
            return FakeResponse(content=b"png-bytes", headers={"content-type": "image/png"})
        if url.endswith("/thumbnail"):
            return FakeResponse(content=b"jpeg-bytes", headers={"content-type": "image/jpeg"})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(publisher.httpx, "get", fake_get)
    integration = SimpleNamespace(
        base_url="http://immich.local:2283/",
        config_json=json.dumps({"api_key": "immich-key"}),
    )

    url = publisher._prepare_public_image(
        "asset-1",
        FakeDb(integration),
        "https://app.test",
        instagram_compatible=True,
    )

    filename = url.rsplit("/", 1)[1]
    assert filename.endswith(".jpg")
    assert (tmp_path / filename).read_bytes() == b"jpeg-bytes"
    assert get_calls[1] == (
        "http://immich.local:2283/api/assets/asset-1/thumbnail",
        {
            "params": {"size": "preview", "format": "JPEG"},
            "headers": {"x-api-key": "immich-key"},
            "timeout": 60,
            "follow_redirects": True,
        },
    )
