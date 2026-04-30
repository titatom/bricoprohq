import json
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta, date
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from . import db as _db_module
from .db import Base, get_db, _reinit as _db_reinit
_db_reinit()  # re-read DATABASE_URL in case env changed (e.g. test reloads)
from .models import (
    User, Setting, QuickLink, Integration, DashboardCache,
    ContentAsset, ContentDraft, Campaign, PostMetric,
)
from .schemas import (
    LoginRequest, LoginResponse, UserMeResponse,
    SettingIn, SettingOut,
    QuickLinkIn, QuickLinkOut,
    IntegrationUpdateIn,
    AssetStatusIn, AssetCreateIn,
    SocialGenerateIn,
    DraftIn, DraftStatusIn,
    CampaignIn,
    PostMetricIn,
)
from .auth import verify_password, create_access_token, hash_password, SECRET_KEY, ALGORITHM

log = logging.getLogger("bricopro")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Bricopro HQ API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=_db_module.engine)

SOURCES = ["google_calendar", "jobber", "immich", "immich-gpt", "paperless", "meta", "google_business"]
CACHE_TTL_MINUTES = 15
PENDING_IMAGE_STATUSES = {"new", "pending_ai", "needs_review"}
PENDING_DOC_STATUSES = {"new", "pending_ai", "needs_review", "missing_tags", "missing_correspondent", "missing_document_type"}
DEFAULT_ADMIN_EMAIL = "admin@bricopro.local"
DEFAULT_ADMIN_PASSWORD = "admin1234"


# ── Auth helpers ──────────────────────────────────────────────────────────────

def auth_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    try:
        email = jwt.decode(authorization[7:], SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except JWTError as exc:
        raise HTTPException(401, "Invalid token") from exc
    u = db.query(User).filter(User.email == email).first()
    if not u:
        raise HTTPException(401, "User not found")
    return u


# ── Startup seed ──────────────────────────────────────────────────────────────

def _normalize_email(email: str) -> str:
    return email.strip().lower()


@app.on_event("startup")
def startup_seed():
    db = next(get_db())
    email = _normalize_email(os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL))
    pwd = os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)
    admin = db.query(User).filter(User.email == email).first()
    if not admin:
        db.add(User(email=email, password_hash=hash_password(pwd), role="admin"))
        log.info("Seeded admin user %s", email)
    elif pwd != DEFAULT_ADMIN_PASSWORD and not verify_password(pwd, admin.password_hash):
        admin.password_hash = hash_password(pwd)
        log.info("Updated admin password from ADMIN_PASSWORD for %s", email)
    for s in SOURCES:
        if not db.query(Integration).filter(Integration.provider == s).first():
            db.add(Integration(provider=s, status="not_connected"))
    db.commit()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Auth endpoints ────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == _normalize_email(payload.email)).first()
    if not u or not verify_password(payload.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return LoginResponse(access_token=create_access_token(u.email))


@app.get("/auth/me", response_model=UserMeResponse)
def me(u: User = Depends(auth_user)):
    return UserMeResponse(email=u.email, role=u.role)


# ── Settings ──────────────────────────────────────────────────────────────────

@app.get("/settings", response_model=list[SettingOut])
def settings(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return db.query(Setting).all()


@app.put("/settings/{key}", response_model=SettingOut)
def set_setting(key: str, payload: SettingIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    s = db.query(Setting).filter(Setting.key == key).first() or Setting(key=key, value="")
    s.value = payload.value
    db.add(s); db.commit(); db.refresh(s)
    return s


# ── Quick Links ───────────────────────────────────────────────────────────────

@app.get("/quick-links", response_model=list[QuickLinkOut])
def ql(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return db.query(QuickLink).order_by(QuickLink.sort_order.asc()).all()


@app.post("/quick-links", response_model=QuickLinkOut)
def ql_create(payload: QuickLinkIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    o = QuickLink(**payload.model_dump())
    db.add(o); db.commit(); db.refresh(o)
    return o


@app.put("/quick-links/{id}", response_model=QuickLinkOut)
def ql_update(id: int, payload: QuickLinkIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    o = db.query(QuickLink).filter(QuickLink.id == id).first()
    if not o:
        raise HTTPException(404, "Not found")
    for k, v in payload.model_dump().items():
        setattr(o, k, v)
    db.commit(); db.refresh(o)
    return o


@app.delete("/quick-links/{id}")
def ql_del(id: int, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    o = db.query(QuickLink).filter(QuickLink.id == id).first()
    if not o:
        raise HTTPException(404, "Not found")
    db.delete(o); db.commit()
    return {"deleted": True}


# ── Integrations ──────────────────────────────────────────────────────────────

# In-memory CSRF state store: state_token → provider name
_oauth_states: dict[str, str] = {}

# Secret config keys that are always masked in API responses
_SECRET_KEYS = {"api_key", "client_secret"}
_GOOGLE_PROVIDERS = {"google_calendar", "google_business"}
_GOOGLE_CANONICAL_PROVIDER = "google_calendar"

# ── OAuth provider registry ────────────────────────────────────────────────────
# Each entry describes how to build an authorization URL and exchange the code.

OAUTH_PROVIDERS: dict[str, dict] = {
    "jobber": {
        "authorize_url": "https://api.getjobber.com/api/oauth/authorize",
        "token_url":     "https://api.getjobber.com/api/oauth/token",
        "scopes":        [],  # Jobber scopes are configured in the Developer Center app
        "extra_params":  {},
    },
    "google_calendar": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url":     "https://oauth2.googleapis.com/token",
        "refresh_url":   "https://oauth2.googleapis.com/token",
        "scopes":        [
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/business.manage",
        ],
        # access_type=offline → Google returns a refresh_token
        # prompt=consent → always show consent screen so refresh_token is included
        "extra_params":  {"access_type": "offline", "prompt": "consent"},
    },
    "meta": {
        "authorize_url": "https://www.facebook.com/v21.0/dialog/oauth",
        "token_url":     "https://graph.facebook.com/v21.0/oauth/access_token",
        # Pages permissions: manage posts + read page insights; Instagram requires pages_show_list
        "scopes": [
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
            "instagram_basic",
            "instagram_content_publish",
            "business_management",
        ],
        "extra_params": {},
        # Meta does not use standard refresh tokens; we exchange for a long-lived token post-callback.
        "long_lived_token": True,
    },
}


def _oauth_registry_provider(provider: str) -> str:
    """Return the OAuth provider config key used for a logical integration."""
    if provider in _GOOGLE_PROVIDERS:
        return _GOOGLE_CANONICAL_PROVIDER
    return provider


def _oauth_config_integration(provider: str, db: Session) -> Integration | None:
    """Return the integration row that owns OAuth client configuration."""
    if provider in _GOOGLE_PROVIDERS:
        canonical = db.query(Integration).filter(Integration.provider == _GOOGLE_CANONICAL_PROVIDER).first()
        if canonical and canonical.config_json:
            return canonical
    return db.query(Integration).filter(Integration.provider == provider).first()


def _store_oauth_tokens(
    provider: str,
    db: Session,
    access_token: str,
    refresh_token: str,
    expires_in: int | str,
) -> None:
    """Persist OAuth tokens, syncing shared Google auth across Google integrations."""
    providers = sorted(_GOOGLE_PROVIDERS) if provider in _GOOGLE_PROVIDERS else [provider]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    for p in providers:
        i = db.query(Integration).filter(Integration.provider == p).first()
        if not i:
            i = Integration(provider=p, status="not_connected")
            db.add(i)
        i.oauth_access_token = access_token
        if refresh_token:
            i.oauth_refresh_token = refresh_token
        i.oauth_token_expires_at = expires_at
        i.status = "ok"
        i.last_sync_at = datetime.now(timezone.utc)


def _clear_oauth_tokens(provider: str, db: Session) -> None:
    """Clear OAuth tokens, syncing shared Google auth across Google integrations."""
    providers = sorted(_GOOGLE_PROVIDERS) if provider in _GOOGLE_PROVIDERS else [provider]
    for p in providers:
        i = db.query(Integration).filter(Integration.provider == p).first()
        if not i:
            continue
        i.oauth_access_token = None
        i.oauth_refresh_token = None
        i.oauth_token_expires_at = None
        i.status = "not_connected"


def _oauth_redirect_uri(provider: str) -> str:
    """
    Return the public-facing OAuth callback URL for a given provider.
    Priority:
      1. {PROVIDER_UPPER}_REDIRECT_URI env var (e.g. JOBBER_REDIRECT_URI)
      2. APP_BASE_URL env var + /api/integrations/{provider}/oauth/callback
      3. localhost:3000 fallback (dev only)
    The callback is served by the backend through the Next.js /api/* proxy.
    """
    env_key = f"{provider.upper().replace('-', '_')}_REDIRECT_URI"
    explicit = os.getenv(env_key, "").strip()
    if explicit:
        return explicit
    base = os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")
    return f"{base}/api/integrations/{provider}/oauth/callback"


def _integration_out(i: Integration) -> dict:
    """Serialize an Integration row, returning masked config fields."""
    try:
        config = json.loads(i.config_json or "{}")
    except Exception:
        config = {}
    config_fields = {}
    for k, v in config.items():
        config_fields[k] = "••••••••" if (k in _SECRET_KEYS and v) else v
    return {
        "provider": i.provider,
        "base_url": i.base_url or "",
        "status": i.status,
        "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None,
        "config_fields": config_fields,
        "oauth_connected": bool(i.oauth_access_token),
    }


@app.get("/integrations")
def integrations(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return [_integration_out(i) for i in db.query(Integration).all()]


# ── Generic OAuth routes — must come before the /{provider} wildcard ──────────

@app.get("/integrations/{provider}/oauth/authorize")
def oauth_authorize(provider: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Start OAuth 2.0 authorization flow for any registered OAuth provider."""
    registry_provider = _oauth_registry_provider(provider)
    if registry_provider not in OAUTH_PROVIDERS:
        raise HTTPException(400, f"OAuth not supported for provider '{provider}'")

    i = _oauth_config_integration(provider, db)
    if not i:
        raise HTTPException(404, f"Integration '{provider}' not configured")
    try:
        config = json.loads(i.config_json or "{}")
    except Exception:
        config = {}

    client_id = config.get("client_id", "")
    if not client_id:
        raise HTTPException(400, f"{provider} client_id not configured. Save Client ID first.")

    state = secrets.token_hex(16)
    _oauth_states[state] = provider

    prov = OAUTH_PROVIDERS[registry_provider]
    redirect_uri = _oauth_redirect_uri(provider)
    params: dict = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        **prov.get("extra_params", {}),
    }
    scopes = prov.get("scopes", [])
    if scopes:
        params["scope"] = " ".join(scopes)

    return RedirectResponse(f"{prov['authorize_url']}?{urlencode(params)}")


@app.get("/integrations/{provider}/oauth/callback")
def oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    """Handle OAuth 2.0 callback for any registered OAuth provider."""
    frontend_base = os.getenv("APP_BASE_URL", "http://localhost:3000").rstrip("/")

    if error:
        log.warning("OAuth error for %s: %s — %s", provider, error, error_description)
        return RedirectResponse(
            f"{frontend_base}/settings?oauth_error={error}&oauth_provider={provider}"
        )

    if not state or _oauth_states.get(state) != provider:
        raise HTTPException(400, "Invalid or expired OAuth state")
    _oauth_states.pop(state, None)

    if not code:
        raise HTTPException(400, "Authorization code missing")

    registry_provider = _oauth_registry_provider(provider)
    if registry_provider not in OAUTH_PROVIDERS:
        raise HTTPException(400, f"OAuth not supported for provider '{provider}'")

    i = _oauth_config_integration(provider, db)
    if not i:
        raise HTTPException(404, f"Integration '{provider}' not found")
    try:
        config = json.loads(i.config_json or "{}")
    except Exception:
        config = {}

    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    if not client_id or not client_secret:
        raise HTTPException(400, f"{provider} client_id/client_secret not configured")

    prov = OAUTH_PROVIDERS[registry_provider]
    redirect_uri = _oauth_redirect_uri(provider)

    try:
        resp = httpx.post(
            prov["token_url"],
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("%s token exchange failed: %s %s", provider, exc.response.status_code, exc.response.text)
        raise HTTPException(502, f"{provider} token exchange failed: {exc.response.status_code}")
    except httpx.RequestError as exc:
        raise HTTPException(502, f"{provider} token exchange request failed: {exc}")

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = token_data.get("expires_in", 3600)

    # Meta does not use standard refresh tokens. Exchange the short-lived token
    # (valid ~1 hour) for a long-lived token (~60 days) immediately.
    if prov.get("long_lived_token") and access_token:
        try:
            ll_resp = httpx.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "fb_exchange_token": access_token,
                },
                timeout=15,
            )
            ll_resp.raise_for_status()
            ll_data = ll_resp.json()
            access_token = ll_data.get("access_token", access_token)
            expires_in = ll_data.get("expires_in", 5183944)  # ~60 days default
            log.info("Meta: short-lived token exchanged for long-lived token (expires_in=%s)", expires_in)
        except Exception as exc:
            log.warning("Meta long-lived token exchange failed (using short-lived): %s", exc)

    _store_oauth_tokens(provider, db, access_token, refresh_token, expires_in)
    db.commit()

    return RedirectResponse(f"{frontend_base}/settings?oauth_connected={provider}")


@app.post("/integrations/{provider}/oauth/disconnect")
def oauth_disconnect(provider: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Remove stored OAuth tokens for a provider."""
    i = db.query(Integration).filter(Integration.provider == provider).first()
    if not i:
        raise HTTPException(404, f"Integration '{provider}' not found")
    _clear_oauth_tokens(provider, db)
    db.commit()
    return {"disconnected": True}


# ── Per-provider CRUD (wildcard — must come after specific oauth/* routes) ─────

@app.get("/integrations/{provider}")
def get_integration(provider: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    i = db.query(Integration).filter(Integration.provider == provider).first()
    if not i:
        raise HTTPException(404, "Integration not found")
    return _integration_out(i)


@app.put("/integrations/{provider}")
def update_integration(
    provider: str,
    payload: IntegrationUpdateIn,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    i = db.query(Integration).filter(Integration.provider == provider).first()
    if not i:
        i = Integration(provider=provider, status="not_connected")
    i.base_url = payload.base_url

    # Merge incoming config with existing so that masked values ("••••••••")
    # do not overwrite real secrets.
    try:
        existing_config = json.loads(i.config_json or "{}")
    except Exception:
        existing_config = {}
    try:
        new_config = json.loads(payload.config_json or "{}")
    except Exception:
        new_config = {}

    SECRET_KEYS = {"api_key", "client_secret"}
    for k, v in new_config.items():
        if k in SECRET_KEYS and v and all(c == '•' for c in v):
            # User left the masked placeholder — keep existing value
            pass
        else:
            existing_config[k] = v

    i.config_json = json.dumps(existing_config)
    db.add(i)
    db.commit()
    return _integration_out(i)


@app.post("/integrations/{provider}/test")
def test_integration(provider: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Attempt a live connection test for an integration."""
    try:
        from .services.connectors import get_connector, ConnectorNotConfigured, ConnectorError
        connector = get_connector(provider, db)
        result = connector.fetch()
        i = db.query(Integration).filter(Integration.provider == provider).first()
        if i:
            i.status = "ok"
            i.last_sync_at = datetime.now(timezone.utc)
            db.commit()
        return {"ok": True, "message": f"Connected successfully. Fetched data from {provider}.", "data": result}
    except Exception as exc:
        i = db.query(Integration).filter(Integration.provider == provider).first()
        if i:
            i.status = "error"
            db.commit()
        from .services.connectors import ConnectorNotConfigured
        if isinstance(exc, ConnectorNotConfigured):
            raise HTTPException(400, str(exc))
        raise HTTPException(502, str(exc))


# ── Dashboard cache ───────────────────────────────────────────────────────────

def _fetch_source_data(source: str, db: Session) -> dict:
    """Attempt real connector; fall back to mock summary."""
    try:
        from .services.connectors import get_connector
        connector = get_connector(source, db)
        return connector.fetch()
    except Exception as exc:
        log.warning("Connector %s failed: %s", source, exc)
        return {"source": source, "timestamp": datetime.now(timezone.utc).isoformat(), "summary": "mock", "error": str(exc)}


@app.post("/dashboard/refresh/{source}")
def refresh(source: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    if source not in SOURCES:
        raise HTTPException(404, "Unknown source")
    now = datetime.now(timezone.utc)
    data = _fetch_source_data(source, db)
    c = db.query(DashboardCache).filter(DashboardCache.source == source).first() or DashboardCache(
        source=source, data_json="{}", expires_at=now
    )
    c.data_json = json.dumps(data)
    c.synced_at = now
    c.expires_at = now + timedelta(minutes=CACHE_TTL_MINUTES)
    db.add(c)
    i = db.query(Integration).filter(Integration.provider == source).first()
    if i:
        had_error = "error" in data
        i.status = "error" if had_error else "ok"
        i.last_sync_at = now
    db.commit()
    return {"status": "ok", "source": source}


@app.get("/dashboard")
def dashboard(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    out = {}
    for s in SOURCES:
        c = db.query(DashboardCache).filter(DashboardCache.source == s).first()
        i = db.query(Integration).filter(Integration.provider == s).first()
        out[s] = {
            "status": i.status if i else "unknown",
            "cached": bool(c),
            "stale": True if not c else c.expires_at.replace(tzinfo=timezone.utc) < now,
            "data": {} if not c else json.loads(c.data_json),
        }
    return out


# ── Processing summary ────────────────────────────────────────────────────────

@app.get("/processing/summary")
def processing_summary(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    image_q = db.query(ContentAsset).filter(ContentAsset.source.in_(["immich", "immich-gpt"]))
    doc_q = db.query(ContentAsset).filter(ContentAsset.source.in_(["paperless", "paperless-gpt"]))
    pending_images = image_q.filter(
        ContentAsset.source == "immich-gpt",
        ContentAsset.status.in_(PENDING_IMAGE_STATUSES),
    ).count()
    pending_docs = doc_q.filter(ContentAsset.status.in_(PENDING_DOC_STATUSES)).count()

    return {
        "images_pending": pending_images,
        "documents_pending": pending_docs,
        "needs_review": db.query(ContentAsset).filter(ContentAsset.status == "needs_review").count(),
        "image_source": "immich-gpt",
        "document_source": "paperless / paperless-gpt",
        "personal_images": image_q.filter(ContentAsset.status == "personal_photo").count(),
        "business_images": image_q.filter(ContentAsset.status == "business_photo").count(),
        "social_candidates": image_q.filter(ContentAsset.status == "social_worthy").count(),
    }


# ── Queues ────────────────────────────────────────────────────────────────────

@app.get("/queues/images")
def queue_images(
    status: str | None = None,
    source: str | None = None,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    q = db.query(ContentAsset).filter(ContentAsset.source.in_(["immich", "immich-gpt"]))
    if status:
        q = q.filter(ContentAsset.status == status)
    if source:
        q = q.filter(ContentAsset.source == source)
    return [{"id": a.id, "source": a.source, "title": a.title, "status": a.status, "url": a.source_url, "note": a.note} for a in q.all()]


@app.get("/queues/documents")
def queue_docs(
    status: str | None = None,
    source: str | None = None,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    q = db.query(ContentAsset).filter(ContentAsset.source.in_(["paperless", "paperless-gpt"]))
    if status:
        q = q.filter(ContentAsset.status == status)
    if source:
        q = q.filter(ContentAsset.source == source)
    return [{"id": a.id, "source": a.source, "title": a.title, "status": a.status, "url": a.source_url, "note": a.note} for a in q.all()]


@app.post("/queues/assets")
def create_asset(payload: AssetCreateIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    a = ContentAsset(
        source=payload.source,
        title=payload.title,
        source_url=payload.source_url,
        service_category=payload.service_category,
        status=payload.status,
    )
    db.add(a); db.commit(); db.refresh(a)
    return {"id": a.id}


@app.put("/queues/assets/{asset_id}/status")
def set_asset_status(
    asset_id: int,
    payload: AssetStatusIn,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    a = db.query(ContentAsset).filter(ContentAsset.id == asset_id).first()
    if not a:
        raise HTTPException(404, "Asset not found")
    a.status = payload.status
    a.note = payload.note
    db.commit()
    return {"updated": True}


# ── AI test connection ────────────────────────────────────────────────────────

@app.post("/ai/test")
def ai_test(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    from .services.ai import test_connection, AINotConfigured, AIError
    try:
        result = test_connection(db)
        return {"ok": True, "message": result.get("message", "Connection successful"), "provider": result.get("provider"), "model": result.get("model")}
    except AINotConfigured as exc:
        raise HTTPException(400, str(exc))
    except AIError as exc:
        raise HTTPException(502, str(exc))


# ── Social Studio ─────────────────────────────────────────────────────────────

def _template_fallback(payload: SocialGenerateIn) -> dict:
    """Simple template-based copy used when no AI provider is configured."""
    lang = payload.language
    if lang == "fr":
        body = (
            f"✅ Travaux récents : {payload.service_category} à {payload.city}.\n\n"
            f"{payload.job_description}\n\n"
            "Bricopro est votre entrepreneur local de confiance. "
            "Licencié et assuré. Demandez votre soumission gratuite aujourd'hui !"
        )
        short = f"{payload.service_category} à {payload.city} — travaux professionnels. Contactez Bricopro !"
        tags = "#montreal #bricopro #renovation #entrepreneur"
    elif lang == "en":
        body = (
            f"✅ Recent work: {payload.service_category} in {payload.city}.\n\n"
            f"{payload.job_description}\n\n"
            "Bricopro is your trusted local contractor. "
            "Licensed and insured. Request your free estimate today!"
        )
        short = f"{payload.service_category} in {payload.city} — professional work. Contact Bricopro!"
        tags = "#montreal #bricopro #renovation #contractor"
    else:
        body = (
            f"✅ {payload.service_category} à {payload.city} / in {payload.city}.\n\n"
            f"{payload.job_description}\n\n"
            "Bricopro — entrepreneur local / local contractor. Licencié et assuré / Licensed and insured."
        )
        short = f"{payload.service_category} — Bricopro, Montréal"
        tags = "#montreal #bricopro #renovation #entrepreneur #contractor"
    return {"main_copy": body, "short_variation": short, "hashtags": tags, "cta_text": "", "notes": "No AI provider configured — template used. Set up an AI provider in Settings for richer copy."}


@app.post("/social/generate")
def social_generate(payload: SocialGenerateIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    from .services.ai import generate_social_content, AINotConfigured, AIError

    title = f"{payload.service_category} — {payload.platform}"
    ai_used = True

    try:
        generated = generate_social_content(payload.model_dump(), db)
    except AINotConfigured as exc:
        log.warning("AI not configured, using template fallback: %s", exc)
        generated = _template_fallback(payload)
        ai_used = False
    except AIError as exc:
        log.error("AI generation failed: %s", exc)
        raise HTTPException(502, f"AI generation failed: {exc}")

    d = ContentDraft(
        title=title,
        platform=payload.platform,
        language=payload.language,
        tone=payload.tone,
        service_category=payload.service_category,
        body=generated["main_copy"],
        short_body=generated["short_variation"],
        hashtags=generated["hashtags"],
        cta=payload.cta,
        status="draft_generated",
    )
    db.add(d); db.commit(); db.refresh(d)
    return {
        "draft_id": d.id,
        "title": d.title,
        "main_copy": d.body,
        "short_variation": d.short_body,
        "cta": generated.get("cta_text") or payload.cta,
        "hashtags": d.hashtags,
        "notes": generated.get("notes", "Review and edit before publishing."),
        "ai_used": ai_used,
    }


@app.get("/social/albums")
def social_albums(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    default_album = db.query(Setting).filter(Setting.key == "social_default_album_id").first()
    album_id = default_album.value if default_album and default_album.value else "recent-work"
    return [
        {"id": album_id, "name": "Configured Immich album", "source": "immich", "asset_count": 24},
        {"id": "seasonal-exterior", "name": "Seasonal exterior ideas", "source": "immich", "asset_count": 18},
        {"id": "before-after", "name": "Before / after candidates", "source": "immich", "asset_count": 12},
    ]


@app.post("/social/candidates")
def social_candidates(payload: dict, _: User = Depends(auth_user)):
    album_id = payload.get("album_id", "recent-work")
    service = payload.get("service_category") or "Exterior painting"
    return {
        "album_id": album_id,
        "candidates": [
            {
                "id": f"{album_id}-hero",
                "title": "Best hero image",
                "score": 94,
                "kind": "business_photo",
                "service_category": service,
                "reason": "Clean finished-work image with strong social composition.",
                "before_after": True,
            },
            {
                "id": f"{album_id}-detail",
                "title": "Detail/process image",
                "score": 86,
                "kind": "social_worthy",
                "service_category": service,
                "reason": "Useful supporting image for carousel or proof-of-work post.",
                "before_after": False,
            },
            {
                "id": f"{album_id}-website",
                "title": "Website gallery candidate",
                "score": 81,
                "kind": "website_worthy",
                "service_category": service,
                "reason": "Good long-term portfolio asset with neutral framing.",
                "before_after": False,
            },
        ],
        "campaign_ideas": [
            {
                "title": "Summer exterior painting push",
                "service_category": "Réparations extérieures",
                "season": "spring",
                "focus": "Use March/April planning to fill summer exterior painting bookings.",
            },
            {
                "title": "Before / after trust builder",
                "service_category": service,
                "season": "evergreen",
                "focus": "Show visible transformation and invite quote requests.",
            },
        ],
    }


SOCIAL_SETTING_DEFAULTS = {
    "default_album_id": "",
    "image_model": "",
    "copy_model": "",
    "default_language": "bilingual",
    "default_platforms": "facebook,instagram,gbp",
    "brand_voice": "Local, practical, trustworthy Bricopro voice",
    "facebook_account": "",
    "instagram_account": "",
    "google_business_account": "",
    "meta_account_id": "",
    "google_ads_account_id": "",
    "meta_ads_account": "",
    "google_ads_account": "",
    "before_after_enabled": "true",
}


@app.get("/social/settings")
def social_settings(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    values = {s.key.removeprefix("social_"): s.value for s in db.query(Setting).filter(Setting.key.like("social_%")).all()}
    return {**SOCIAL_SETTING_DEFAULTS, **values}


@app.put("/social/settings")
def save_social_settings(payload: dict, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    if payload.get("meta_account_id") and not payload.get("meta_ads_account"):
        payload["meta_ads_account"] = payload["meta_account_id"]
    if payload.get("google_ads_account_id") and not payload.get("google_ads_account"):
        payload["google_ads_account"] = payload["google_ads_account_id"]
    out = {}
    for key, default in SOCIAL_SETTING_DEFAULTS.items():
        value = str(payload.get(key, default))
        setting_key = f"social_{key}"
        row = db.query(Setting).filter(Setting.key == setting_key).first() or Setting(key=setting_key, value="")
        row.value = value
        db.add(row)
        out[key] = value
    db.commit()
    return out


@app.get("/social/immich/albums")
def social_immich_albums(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return social_albums(_, db)


@app.post("/social/analyze-album")
def social_analyze_album(payload: dict, _: User = Depends(auth_user)):
    result = social_candidates({"album_id": payload.get("album_id"), "service_category": payload.get("service_category")}, _)
    candidates = [
        {
            "id": c["id"],
            "asset_id": c["id"],
            "title": c["title"],
            "score": c["score"],
            "status": c["kind"],
            "service_category": c["service_category"],
            "reason": c["reason"],
            "before_after_pair": c["before_after"],
            "labels": [c["kind"], "before_after" if c["before_after"] else "single_image"],
            "image_url": "",
        }
        for c in result["candidates"]
    ]
    return {
        "album_id": result["album_id"],
        "candidates": candidates,
        "campaign_suggestions": result["campaign_ideas"],
    }


@app.post("/social/generate-pack")
def social_generate_pack(payload: dict, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    platforms = payload.get("platforms") or ["facebook"]
    drafts = []
    for platform in platforms:
        draft = ContentDraft(
            title=f"{payload.get('service_category', 'Bricopro project')} - {platform}",
            platform=platform,
            language=payload.get("language", "bilingual"),
            tone=payload.get("tone", "local"),
            service_category=payload.get("service_category", ""),
            campaign_id=payload.get("campaign_id"),
            body=(
                f"Generated from Immich album {payload.get('album_id', '')}. "
                f"Showcase selected project images and invite customers to request a quote."
            ),
            short_body=f"{payload.get('service_category', 'Recent work')} - ready for review.",
            hashtags="#bricopro #montreal #renovation",
            cta=payload.get("cta", "request_quote"),
            status="draft_generated",
        )
        db.add(draft)
        db.flush()
        drafts.append({
            "draft_id": draft.id,
            "title": draft.title,
            "platform": draft.platform,
            "main_copy": draft.body,
            "short_variation": draft.short_body,
            "hashtags": draft.hashtags,
            "cta": draft.cta,
            "selected_assets": payload.get("asset_ids", []),
        })
    db.commit()
    return {"drafts": drafts}


# ── Publishing ────────────────────────────────────────────────────────────────

@app.get("/publishing/drafts")
def drafts(
    platform: str | None = None,
    status: str | None = None,
    campaign_id: int | None = None,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    q = db.query(ContentDraft)
    if platform:
        q = q.filter(ContentDraft.platform == platform)
    if status:
        q = q.filter(ContentDraft.status == status)
    if campaign_id:
        q = q.filter(ContentDraft.campaign_id == campaign_id)
    return [
        {
            "id": d.id,
            "title": d.title,
            "platform": d.platform,
            "language": d.language,
            "status": d.status,
            "planned_date": d.planned_date.isoformat() if d.planned_date else None,
            "campaign_id": d.campaign_id,
        }
        for d in q.all()
    ]


@app.post("/publishing/drafts")
def create_draft(payload: DraftIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    pd = date.fromisoformat(payload.planned_date) if payload.planned_date else None
    d = ContentDraft(**payload.model_dump(exclude={"planned_date"}), planned_date=pd)
    db.add(d); db.commit(); db.refresh(d)
    return {"id": d.id}


@app.put("/publishing/drafts/{draft_id}/status")
def move_draft(
    draft_id: int,
    status: str = Query(...),
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    from .schemas import DRAFT_STATUSES
    if status not in DRAFT_STATUSES:
        raise HTTPException(422, f"Invalid draft status '{status}'")
    d = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if not d:
        raise HTTPException(404, "Draft not found")
    d.status = status
    d.updated_at = datetime.utcnow()
    db.commit()
    return {"updated": True}


@app.get("/publishing/calendar")
def pub_calendar(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return [
        {
            "id": d.id,
            "title": d.title,
            "platform": d.platform,
            "date": d.planned_date.isoformat() if d.planned_date else None,
            "status": d.status,
        }
        for d in db.query(ContentDraft).all()
    ]


@app.get("/publishing/kanban")
def kanban(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    cols: dict[str, list] = {}
    for d in db.query(ContentDraft).all():
        cols.setdefault(d.status, []).append({"id": d.id, "title": d.title, "platform": d.platform})
    return cols


# ── Campaigns ─────────────────────────────────────────────────────────────────

@app.get("/campaigns")
def campaigns(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return [
        {
            "id": c.id,
            "name": c.name,
            "service_category": c.service_category,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "status": c.status,
            "message": c.message,
        }
        for c in db.query(Campaign).all()
    ]


@app.post("/campaigns")
def create_campaign(payload: CampaignIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    c = Campaign(
        name=payload.name,
        service_category=payload.service_category,
        status=payload.status,
        message=payload.message,
    )
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id}


@app.put("/campaigns/{campaign_id}")
def update_campaign(
    campaign_id: int,
    payload: CampaignIn,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    for k, v in payload.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return {"updated": True}


@app.post("/campaigns/{campaign_id}/generate")
def campaign_generate(campaign_id: int, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    c = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not c:
        raise HTTPException(404, "Campaign not found")
    d = ContentDraft(
        title=f"{c.name} — draft",
        platform="facebook",
        service_category=c.service_category,
        body=c.message or f"Campagne {c.name} — {c.service_category}",
        short_body=(c.message or c.name)[:120],
        hashtags="#montreal #bricopro",
        status="draft_generated",
        campaign_id=c.id,
    )
    db.add(d); db.commit(); db.refresh(d)
    return {"draft_id": d.id, "campaign_id": c.id}


# ── KPI / performance tracking ────────────────────────────────────────────────

def _metric_payload(m: PostMetric) -> dict:
    cost_per_lead = round(m.spend_cents / m.leads, 2) if m.leads else 0
    return {
        "id": m.id,
        "draft_id": m.draft_id,
        "campaign_id": m.campaign_id,
        "title": m.title,
        "campaign_name": m.campaign_name,
        "platform": m.platform,
        "post_url": m.post_url,
        "published_date": m.posted_at.isoformat() if m.posted_at else None,
        "spend": m.spend_cents,
        "impressions": m.impressions,
        "reach": m.reach,
        "clicks": m.clicks,
        "leads": m.leads,
        "messages": m.messages,
        "calls": m.calls,
        "engagements": m.engagements,
        "engagement_rate": m.engagement_rate,
        "cost_per_lead": cost_per_lead,
        "notes": m.notes,
    }


@app.get("/kpi/records")
def kpi_records(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return [_metric_payload(m) for m in db.query(PostMetric).order_by(PostMetric.created_at.desc()).all()]


@app.post("/kpi/records")
def create_kpi_record(payload: PostMetricIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    try:
        posted_at = date.fromisoformat(payload.published_date) if payload.published_date else None
    except ValueError as exc:
        raise HTTPException(422, "published_date must be YYYY-MM-DD") from exc
    metric = PostMetric(
        draft_id=payload.draft_id,
        campaign_id=payload.campaign_id,
        title=payload.title,
        campaign_name=payload.campaign_name,
        platform=payload.platform,
        post_url=payload.post_url,
        posted_at=posted_at,
        spend_cents=payload.spend,
        impressions=payload.impressions,
        reach=payload.reach,
        clicks=payload.clicks,
        leads=payload.leads,
        messages=payload.messages,
        calls=payload.calls,
        engagements=payload.engagements,
        engagement_rate=payload.engagement_rate,
        notes=payload.notes,
    )
    db.add(metric); db.commit(); db.refresh(metric)
    return _metric_payload(metric)


@app.get("/kpi/summary")
def kpi_summary(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    records = db.query(PostMetric).all()
    total_spend = sum(r.spend_cents for r in records)
    total_leads = sum(r.leads for r in records)
    total_clicks = sum(r.clicks for r in records)
    total_impressions = sum(r.impressions for r in records)
    return {
        "total_spend": total_spend,
        "spend": total_spend,
        "total_leads": total_leads,
        "leads": total_leads,
        "total_clicks": total_clicks,
        "clicks": total_clicks,
        "total_impressions": total_impressions,
        "impressions": total_impressions,
        "cost_per_lead": round(total_spend / total_leads, 2) if total_leads else 0,
        "click_through_rate": round((total_clicks / total_impressions) * 100, 2) if total_impressions else 0,
    }
