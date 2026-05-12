import json
import logging
import os
import secrets
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta, date
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse, Response, FileResponse
from sqlalchemy.orm import Session
from jose import JWTError

from . import db as _db_module
from .db import Base, get_db, _reinit as _db_reinit
_db_reinit()  # re-read DATABASE_URL in case env changed (e.g. test reloads)
from .models import (
    User, Setting, QuickLink, Integration, DashboardCache,
    ContentAsset, ContentDraft, Campaign, PostMetric, PostMetricSnapshot, OAuthState,
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
from .auth import verify_password, create_access_token, hash_password, decode_access_token
from .secret_key import DEFAULT_PLACEHOLDER, resolve_secret_key
from .services.connectors import validate_paperless_gpt_base_url, ConnectorNotConfigured, ConnectorError
from .services.rate_limit import (
    DEFAULT_LOGIN_LIMIT,
    DEFAULT_LOGIN_WINDOW_SECONDS,
    default_limiter,
)

log = logging.getLogger("bricopro")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _build_cors_origins() -> tuple[list[str], bool]:
    """
    Build the CORS allowlist from APP_BASE_URL + CORS_ALLOWED_ORIGINS.

    Returns ``(origins, allow_credentials)``. When the operator opts into the
    legacy wildcard via ``CORS_ALLOWED_ORIGINS=*``, browsers require
    ``allow_credentials=False``, so we honor that automatically.
    """
    raw_extra = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if raw_extra == "*":
        return ["*"], False

    origins: list[str] = []

    def _add(value: str) -> None:
        value = value.strip().rstrip("/")
        if value and value not in origins:
            origins.append(value)

    _add(os.getenv("APP_BASE_URL", "").strip())
    for value in raw_extra.split(","):
        _add(value)

    if not origins:
        origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

    return origins, True


# Resolve SECRET_KEY at import time so misconfigurations (production with the
# default placeholder) fail loudly during startup rather than at the first
# request — and so the dev-mode auto-generated key file is created up front.
try:
    resolve_secret_key()
except Exception as exc:  # pragma: no cover - logged then re-raised
    log.critical("SECRET_KEY misconfiguration: %s", exc)
    raise

app = FastAPI(title="Bricopro HQ API", version="1.0.0")

_cors_origins, _cors_allow_credentials = _build_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
log.info("CORS allowed_origins=%s allow_credentials=%s", _cors_origins, _cors_allow_credentials)

Base.metadata.create_all(bind=_db_module.engine)


def _sqlite_col_type(col) -> str:
    """Return a SQLite-compatible type string for a SQLAlchemy column."""
    from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Date
    t = type(col.type)
    if issubclass(t, String):
        length = getattr(col.type, "length", None)
        return f"VARCHAR({length})" if length else "TEXT"
    if issubclass(t, Text):
        return "TEXT"
    if issubclass(t, Boolean):
        return "INTEGER"
    if issubclass(t, Integer):
        return "INTEGER"
    if issubclass(t, Float):
        return "REAL"
    if issubclass(t, DateTime):
        return "DATETIME"
    if issubclass(t, Date):
        return "DATE"
    return "TEXT"


def _sqlite_alter_default(col) -> str:
    """
    Return the DEFAULT clause for ALTER TABLE ADD COLUMN.
    SQLite requires a non-null DEFAULT when adding a NOT NULL column so that
    existing rows receive a valid value.
    """
    if col.nullable:
        return ""
    from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Date
    t = type(col.type)
    if issubclass(t, (String, Text)):
        return " DEFAULT ''"
    if issubclass(t, (Integer, Boolean)):
        return " DEFAULT 0"
    if issubclass(t, Float):
        return " DEFAULT 0"
    if issubclass(t, DateTime):
        return " DEFAULT CURRENT_TIMESTAMP"
    if issubclass(t, Date):
        return " DEFAULT (date('now'))"
    return " DEFAULT ''"


def _migrate_db() -> None:
    """
    Add any model columns that are absent from the live database tables.

    SQLAlchemy's create_all() only creates entirely missing tables — it never
    alters existing ones.  Any column added to a model after a user's initial
    install will be absent from their live database, causing INSERT failures
    (HTTP 500) the next time that table is written to.

    This function is idempotent and safe on every startup.
    It only acts on SQLite (the app's default); for other engines create_all
    handles full schema creation on a fresh database.
    """
    from sqlalchemy import inspect, text

    if not str(_db_module.engine.url).startswith("sqlite"):
        return

    inspector = inspect(_db_module.engine)
    existing_tables = set(inspector.get_table_names())

    with _db_module.engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table — create_all already handled it
            existing_cols = {row["name"] for row in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.key in existing_cols:
                    continue
                col_type = _sqlite_col_type(col)
                default_clause = _sqlite_alter_default(col)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN {col.key} {col_type}{default_clause}'
                log.info("DB migration: %s", ddl)
                conn.execute(text(ddl))


_migrate_db()

SOURCES = ["google_calendar", "jobber", "immich", "immich-gpt", "paperless", "paperless-gpt", "meta", "google_business", "instagram"]
CACHE_TTL_MINUTES = 15
PENDING_IMAGE_STATUSES = {"new", "pending_ai", "needs_review"}
PENDING_DOC_STATUSES = {"new", "pending_ai", "needs_review", "missing_tags", "missing_correspondent", "missing_document_type"}
DEFAULT_ADMIN_EMAIL = "admin@bricopro.local"
DEFAULT_ADMIN_PASSWORD = "admin1234"


# ── Request origin helpers ────────────────────────────────────────────────────

def _origin_from_url(value: str = "") -> str:
    parsed = urlparse((value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _first_header_value(value: str = "") -> str:
    return (value or "").split(",")[0].strip()


def _request_app_base_urls(request: Request) -> str:
    """Collect known public app origins for validation behind reverse proxies."""
    bases: list[str] = []

    def add(value: str = "") -> None:
        value = value.strip().rstrip("/")
        if value and value not in bases:
            bases.append(value)

    add(os.getenv("APP_BASE_URL", ""))

    forwarded_host = _first_header_value(
        request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    )
    forwarded_proto = _first_header_value(
        request.headers.get("x-forwarded-proto") or request.url.scheme
    )
    if forwarded_host:
        add(f"{forwarded_proto or 'http'}://{forwarded_host}")

    add(_origin_from_url(request.headers.get("origin", "")))
    add(_origin_from_url(request.headers.get("referer", "")))
    return ",".join(bases)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def auth_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    try:
        email = decode_access_token(authorization[7:]).get("sub")
    except JWTError as exc:
        raise HTTPException(401, "Invalid token") from exc
    u = db.query(User).filter(User.email == email).first()
    if not u:
        raise HTTPException(401, "User not found")
    return u


# ── Startup seed ──────────────────────────────────────────────────────────────

def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _admin_credentials_from_env() -> tuple[str, str]:
    return (
        _normalize_email(os.getenv("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)),
        os.getenv("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD),
    )


def _sync_configured_admin(db: Session) -> tuple[User, bool]:
    email, pwd = _admin_credentials_from_env()
    admin = db.query(User).filter(User.email == email).first()
    if not admin:
        admin = User(email=email, password_hash=hash_password(pwd), role="admin")
        db.add(admin)
        log.info("Seeded admin user %s", email)
        return admin, True
    if pwd != DEFAULT_ADMIN_PASSWORD and not verify_password(pwd, admin.password_hash):
        admin.password_hash = hash_password(pwd)
        log.info("Updated admin password from ADMIN_PASSWORD for %s", email)
        return admin, True
    return admin, False


def _is_production_env() -> bool:
    return os.getenv("APP_ENV", "").strip().lower() == "production"


def _warn_default_admin_password() -> None:
    """Emit a loud warning when the admin password is left at the default."""
    _, pwd = _admin_credentials_from_env()
    if pwd == DEFAULT_ADMIN_PASSWORD:
        if _is_production_env():
            log.critical(
                "ADMIN_PASSWORD is left at the default value while APP_ENV=production. "
                "Set ADMIN_PASSWORD to a strong, unique value before exposing this app."
            )
        else:
            log.warning(
                "ADMIN_PASSWORD is left at the default value (%r). "
                "Change it in your .env before deploying to any network.",
                DEFAULT_ADMIN_PASSWORD,
            )


@app.on_event("startup")
def startup_seed():
    db = next(get_db())
    _sync_configured_admin(db)
    for s in SOURCES:
        if not db.query(Integration).filter(Integration.provider == s).first():
            db.add(Integration(provider=s, status="not_connected"))
    db.commit()
    _warn_default_admin_password()
    if (os.getenv("SECRET_KEY") or "").strip() in ("", DEFAULT_PLACEHOLDER):
        log.warning(
            "SECRET_KEY env var not set; using the on-disk dev fallback. "
            "Set SECRET_KEY explicitly in production."
        )
    _start_scheduler()


def _start_scheduler():
    """Start the APScheduler background scheduler for scheduled post publishing."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(_run_scheduled_posts, "interval", minutes=1, id="publish_scheduled", max_instances=1)
        scheduler.add_job(_cleanup_publish_assets, "interval", hours=6, id="cleanup_assets", max_instances=1)
        scheduler.start()
        app.state.scheduler = scheduler
        log.info("APScheduler started — checking scheduled posts every minute")
    except Exception as exc:
        log.warning("Could not start APScheduler: %s", exc)


@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass


def _cleanup_publish_assets():
    from .services.social_publisher import cleanup_old_publish_assets
    cleanup_old_publish_assets()


def _run_scheduled_posts():
    """Publish any drafts that are scheduled and past their planned_date/time."""
    from .services.social_publisher import _publish_draft
    db = next(get_db())
    try:
        now = datetime.now(timezone.utc)
        due = (
            db.query(ContentDraft)
            .filter(
                ContentDraft.status == "scheduled",
                ContentDraft.planned_date.isnot(None),
                ContentDraft.platform_account_id.isnot(None),
            )
            .all()
        )
        for draft in due:
            if not _draft_is_due(draft, now):
                continue
            try:
                app_base = os.getenv("APP_BASE_URL", "http://localhost:8000")
                _publish_draft(draft, db, app_base)
                log.info("Scheduled post published: draft_id=%s platform=%s", draft.id, draft.platform)
            except Exception as exc:
                log.error("Scheduled post failed draft_id=%s: %s", draft.id, exc)
                draft.status = "failed"
                draft.publish_error = str(exc)
                draft.updated_at = datetime.utcnow()
                db.commit()
    finally:
        db.close()


def _draft_is_due(draft: ContentDraft, now: datetime) -> bool:
    if not draft.planned_date:
        return False
    time_str = (draft.planned_time or "00:00").strip() or "00:00"
    try:
        hour, minute = [int(x) for x in time_str.split(":")[:2]]
    except (ValueError, AttributeError):
        hour, minute = 0, 0
    dt = datetime(
        draft.planned_date.year, draft.planned_date.month, draft.planned_date.day,
        hour, minute, tzinfo=timezone.utc
    )
    return now >= dt


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Auth endpoints ────────────────────────────────────────────────────────────

LOGIN_BUCKET = "auth.login"


def _login_identity(request: Request, email: str) -> str:
    """Build a per-IP+email key for login rate limiting."""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    client_host = forwarded or (request.client.host if request.client else "unknown")
    return f"{client_host}|{email}"


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)

    limiter = default_limiter()
    allowed, retry_after = limiter.check(
        LOGIN_BUCKET,
        _login_identity(request, email),
        limit=int(os.getenv("LOGIN_RATE_LIMIT", DEFAULT_LOGIN_LIMIT)),
        window_seconds=float(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", DEFAULT_LOGIN_WINDOW_SECONDS)),
    )
    if not allowed:
        log.warning("Login rate limit hit for %s", email)
        raise HTTPException(
            429,
            "Too many login attempts. Wait a moment and try again.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    u = db.query(User).filter(User.email == email).first()
    if u and verify_password(payload.password, u.password_hash):
        limiter.reset(LOGIN_BUCKET, _login_identity(request, email))
        return LoginResponse(access_token=create_access_token(u.email))

    env_email, env_pwd = _admin_credentials_from_env()
    if email == env_email and payload.password == env_pwd and (env_pwd != DEFAULT_ADMIN_PASSWORD or not u):
        u, changed = _sync_configured_admin(db)
        if changed:
            db.commit()
            db.refresh(u)
        limiter.reset(LOGIN_BUCKET, _login_identity(request, email))
        return LoginResponse(access_token=create_access_token(u.email))

    if not u or not verify_password(payload.password, u.password_hash):
        raise HTTPException(401, "Invalid credentials")
    limiter.reset(LOGIN_BUCKET, _login_identity(request, email))
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

OAUTH_STATE_TTL_SECONDS = 600


def _now_utc_naive() -> datetime:
    """Return current UTC time as a naive datetime for legacy `DateTime` columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _persist_oauth_state(provider: str, db: Session) -> str:
    """Generate, persist, and return a fresh OAuth CSRF state token."""
    state = secrets.token_hex(16)
    now = _now_utc_naive()
    expires_at = now + timedelta(seconds=OAUTH_STATE_TTL_SECONDS)
    db.add(OAuthState(state=state, provider=provider, created_at=now, expires_at=expires_at))
    db.commit()
    return state


def _consume_oauth_state(state: str, expected_provider: str, db: Session) -> bool:
    """Validate, then remove a stored OAuth state token."""
    if not state:
        return False
    row = db.query(OAuthState).filter(OAuthState.state == state).first()
    if not row:
        return False
    valid = row.provider == expected_provider and row.expires_at > _now_utc_naive()
    db.delete(row)
    db.flush()
    # Best-effort cleanup of any other expired rows so the table doesn't grow.
    db.query(OAuthState).filter(OAuthState.expires_at <= _now_utc_naive()).delete(synchronize_session=False)
    db.commit()
    return valid


# Secret config keys that are always masked in API responses
_SECRET_KEYS = {"api_key", "client_secret"}
_GOOGLE_PROVIDERS = {"google_calendar", "google_business"}
_GOOGLE_CANONICAL_PROVIDER = "google_calendar"
# Instagram shares App ID / App Secret from the "meta" integration row.
# Unlike Google, each provider stores its own independent access token.
_META_PROVIDERS = {"meta", "instagram"}
_META_CANONICAL_PROVIDER = "meta"

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
        # Facebook Login scopes for Page management only. Instagram publishing
        # uses the separate "instagram" provider (Instagram API with Instagram Login).
        "scopes": [
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
            "business_management",
        ],
        "extra_params": {},
        # Meta does not use standard refresh tokens; we exchange for a long-lived token post-callback.
        # FB long-lived exchange: grant_type=fb_exchange_token, param name=fb_exchange_token
        "long_lived_token":       True,
        "long_lived_token_url":   "https://graph.facebook.com/v21.0/oauth/access_token",
        "long_lived_grant":       "fb_exchange_token",
        "long_lived_token_param": "fb_exchange_token",
    },
    # Instagram API with Instagram Login — uses instagram_business_* scopes and a
    # separate authorization endpoint.  Credentials (App ID / Secret) are shared
    # from the "meta" integration row via _META_PROVIDERS.
    # IG long-lived exchange: grant_type=ig_exchange_token, param name=access_token
    "instagram": {
        "authorize_url": "https://api.instagram.com/oauth/authorize",
        "token_url":     "https://api.instagram.com/oauth/access_token",
        "scopes": [
            "instagram_business_basic",
            "instagram_business_content_publish",
        ],
        "extra_params": {},
        "long_lived_token":       True,
        "long_lived_token_url":   "https://graph.instagram.com/access_token",
        "long_lived_grant":       "ig_exchange_token",
        "long_lived_token_param": "access_token",
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
    if provider in _META_PROVIDERS:
        # Use the provider's own row first (allows Instagram-specific App ID/Secret).
        # Fall back to the meta row so the user only has to enter credentials once
        # when both integrations share the same Meta app.
        own = db.query(Integration).filter(Integration.provider == provider).first()
        if own and own.config_json:
            try:
                own_cfg = json.loads(own.config_json)
                if own_cfg.get("client_id") and own_cfg.get("client_secret"):
                    return own
            except Exception:
                pass
        canonical = db.query(Integration).filter(Integration.provider == _META_CANONICAL_PROVIDER).first()
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
    if i.provider == "paperless-gpt":
        config = {"api_key": config.get("api_key", "")}
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
def oauth_authorize(
    provider: str,
    mode: str = Query(default="redirect"),
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
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

    state = _persist_oauth_state(provider, db)

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

    authorization_url = f"{prov['authorize_url']}?{urlencode(params)}"
    if mode == "json":
        return {"authorization_url": authorization_url}
    return RedirectResponse(authorization_url)


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

    if not _consume_oauth_state(state or "", provider, db):
        raise HTTPException(400, "Invalid or expired OAuth state")

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

    # Some providers (Meta, Instagram) do not use standard refresh tokens.
    # Exchange the short-lived code token for a long-lived token immediately.
    ll_url = prov.get("long_lived_token_url")
    ll_grant = prov.get("long_lived_grant", "fb_exchange_token")
    ll_token_param = prov.get("long_lived_token_param", ll_grant)
    if prov.get("long_lived_token") and ll_url and access_token:
        try:
            ll_resp = httpx.get(
                ll_url,
                params={
                    "grant_type": ll_grant,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    ll_token_param: access_token,
                },
                timeout=15,
            )
            ll_resp.raise_for_status()
            ll_data = ll_resp.json()
            access_token = ll_data.get("access_token", access_token)
            expires_in = ll_data.get("expires_in", 5183944)  # ~60 days default
            log.info("%s: short-lived token exchanged for long-lived token (expires_in=%s)", provider, expires_in)
        except Exception as exc:
            log.warning("%s long-lived token exchange failed (using short-lived): %s", provider, exc)

    _store_oauth_tokens(provider, db, access_token, refresh_token, expires_in)
    db.commit()

    return RedirectResponse(f"{frontend_base}/settings?oauth_connected={provider}")


@app.get("/integrations/instagram/webhook")
def instagram_webhook_verify(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
):
    """
    Meta webhook verification endpoint for the Instagram product.

    When you configure a Webhook Callback URL in the Meta developer portal
    (Instagram product → Webhooks), Meta sends a GET request here with
    hub.mode=subscribe, hub.verify_token, and hub.challenge.  We confirm the
    verify token matches INSTAGRAM_WEBHOOK_VERIFY_TOKEN and echo the challenge.

    This URL goes in: Instagram product → Webhooks → Callback URL.
    The OAuth redirect URI goes separately in: Instagram Login → Valid OAuth Redirect URIs.
    """
    expected = os.getenv("INSTAGRAM_WEBHOOK_VERIFY_TOKEN", "").strip()
    if hub_mode == "subscribe" and hub_verify_token and expected and hub_verify_token == expected:
        log.info("Instagram webhook verified successfully")
        return PlainTextResponse(hub_challenge or "")
    log.warning(
        "Instagram webhook verification failed (mode=%s, token_match=%s)",
        hub_mode,
        hub_verify_token == expected if expected else "no token configured",
    )
    raise HTTPException(403, "Instagram webhook verification failed")


@app.post("/integrations/instagram/webhook")
async def instagram_webhook_receive(request: Request):
    """Receive Instagram webhook event payloads (no-op placeholder)."""
    log.info("Instagram webhook payload received")
    return {"ok": True}


@app.post("/integrations/{provider}/oauth/disconnect")
def oauth_disconnect(provider: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Remove stored OAuth tokens for a provider."""
    i = db.query(Integration).filter(Integration.provider == provider).first()
    if not i:
        raise HTTPException(404, f"Integration '{provider}' not found")
    _clear_oauth_tokens(provider, db)
    db.commit()
    return {"disconnected": True}


@app.post("/integrations/{provider}/disconnect")
def disconnect_integration(provider: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Clear all credentials and reset integration to not_connected."""
    i = db.query(Integration).filter(Integration.provider == provider).first()
    if not i:
        raise HTTPException(404, f"Integration '{provider}' not found")
    if i.oauth_access_token:
        _clear_oauth_tokens(provider, db)
    i.base_url = None
    i.config_json = "{}"
    i.status = "not_connected"
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
    request: Request,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    i = db.query(Integration).filter(Integration.provider == provider).first()
    if not i:
        i = Integration(provider=provider, status="not_connected")
    base_url = payload.base_url or ""
    if provider == "paperless-gpt":
        base_url = base_url.strip().rstrip("/")
        try:
            validate_paperless_gpt_base_url(base_url, _request_app_base_urls(request))
        except ConnectorNotConfigured as exc:
            raise HTTPException(400, str(exc))
    i.base_url = base_url

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

    if provider == "paperless-gpt":
        existing_config = {"api_key": existing_config.get("api_key", "")}

    # If a raw access token was pasted into the config (supported for instagram),
    # move it to oauth_access_token rather than persisting it in config_json.
    manual_token = (existing_config.pop("access_token", "") or "").strip()
    if manual_token and not all(c == "•" for c in manual_token):
        i.oauth_access_token = manual_token
        i.status = "ok"
        i.last_sync_at = datetime.now(timezone.utc)

    i.config_json = json.dumps(existing_config)
    db.add(i)
    db.commit()
    return _integration_out(i)


@app.post("/integrations/{provider}/test")
def test_integration(provider: str, request: Request, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Attempt a live connection test for an integration."""
    try:
        from .services.connectors import get_connector
        connector = get_connector(provider, db)
        if provider == "paperless-gpt":
            validate_paperless_gpt_base_url(connector.base_url, _request_app_base_urls(request))
            result = connector.test_connection()
        else:
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
        if isinstance(exc, ConnectorNotConfigured):
            raise HTTPException(400, str(exc))
        if isinstance(exc, ConnectorError):
            log.warning(
                "Integration test failed for %s: %s",
                provider,
                exc.message,
                extra={
                    "provider": provider,
                    "error_type": exc.error_type,
                    "target_url": exc.target_url,
                    "upstream_status": exc.upstream_status,
                    "configured_base_url": exc.configured_base_url,
                },
            )
            detail = exc.as_detail() if exc.structured else str(exc)
            raise HTTPException(exc.status_code, detail)
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


@app.get("/dashboard/jobber-stats")
def jobber_stats(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Fetch Jobber stats directly for the dashboard header (independent from card limits)."""
    from .services.connectors import JobberConnector, ConnectorNotConfigured, ConnectorError
    integration = db.query(Integration).filter(Integration.provider == "jobber").first()
    if not integration:
        return {"upcoming_unscheduled_count": 0, "action_required_count": 0, "new_requests_count": 0, "pending_invoice_count": 0}
    try:
        connector = JobberConnector(integration)
        return connector.fetch_stats()
    except (ConnectorNotConfigured, ConnectorError) as exc:
        log.warning("Jobber stats fetch failed: %s", exc)
        return {"upcoming_unscheduled_count": 0, "action_required_count": 0, "new_requests_count": 0, "pending_invoice_count": 0, "error": str(exc)}


def _publish_draft(draft: ContentDraft, db: Session, app_base_url: str) -> str:
    """
    Core publish logic used by both the on-demand endpoint and the scheduler.
    Returns the platform_post_id.
    """
    from .services.social_publisher import (
        post_to_facebook, post_to_instagram, post_to_gbp,
        _get_meta_token, _get_pages,
    )

    platform = (draft.platform or "").lower()
    account_id = draft.platform_account_id or ""
    image_ids = [x for x in (draft.image_ids or "").split(",") if x.strip()]
    message = "\n\n".join(filter(None, [draft.body, draft.hashtags]))

    if platform == "facebook":
        user_token = _get_meta_token(db)
        post_id = post_to_facebook(account_id, message, image_ids, db, user_token)
    elif platform == "instagram":
        user_token = _get_meta_token(db)
        pages = _get_pages(user_token)
        page_token = ""
        ig_user_id = account_id
        for p in pages:
            if p.get("ig_user_id") == account_id:
                page_token = p["access_token"]
                break
        if not page_token:
            page_token = _get_meta_token(db)
        caption = "\n\n".join(filter(None, [draft.body, draft.hashtags]))
        post_id = post_to_instagram(ig_user_id, caption, image_ids, db, page_token, app_base_url)
    elif platform == "gbp":
        post_id = post_to_gbp(account_id, message, draft.cta or "", image_ids, db, app_base_url)
    else:
        raise HTTPException(422, f"Direct publishing not supported for platform '{platform}'")

    now = datetime.utcnow()
    draft.platform_post_id = post_id
    draft.status = "posted"
    draft.published_at = now
    draft.publish_error = None
    draft.updated_at = now
    db.commit()
    return post_id


@app.get("/integrations/immich/assets/{asset_id}/original")
def immich_asset_original(asset_id: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Proxy a full-size Immich asset for use in social uploads."""
    i = db.query(Integration).filter(Integration.provider == "immich").first()
    if not i or not i.base_url:
        raise HTTPException(400, "Immich base_url not configured")
    try:
        config = json.loads(i.config_json or "{}")
    except Exception:
        config = {}
    api_key = config.get("api_key", "")
    if not api_key or all(c == '•' for c in api_key):
        raise HTTPException(400, "Immich api_key not configured")
    try:
        upstream = httpx.get(
            f"{i.base_url.rstrip('/')}/api/assets/{asset_id}/original",
            headers={"x-api-key": api_key},
            timeout=60,
            follow_redirects=True,
        )
        upstream.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Immich original request failed") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Immich original request failed: {exc}") from exc
    content_type = upstream.headers.get("content-type", "image/jpeg")
    return Response(content=upstream.content, media_type=content_type)


@app.get("/media/publish-assets/{filename}")
def serve_publish_asset(filename: str):
    """Serve a temp publish asset publicly (no auth) for Instagram / GBP image URLs."""
    from .services.social_publisher import PUBLISH_ASSETS_DIR
    import re
    if not re.match(r'^[a-f0-9]{32}\.[a-z]+$', filename):
        raise HTTPException(404, "Not found")
    path = PUBLISH_ASSETS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Asset not found or expired")
    return FileResponse(str(path))


@app.get("/integrations/immich/assets/{asset_id}/thumbnail")
def immich_asset_thumbnail(asset_id: str, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    i = db.query(Integration).filter(Integration.provider == "immich").first()
    if not i or not i.base_url:
        raise HTTPException(400, "Immich base_url not configured")
    try:
        config = json.loads(i.config_json or "{}")
    except Exception:
        config = {}
    api_key = config.get("api_key", "")
    if not api_key or all(c == '•' for c in api_key):
        raise HTTPException(400, "Immich api_key not configured")

    try:
        upstream = httpx.get(
            f"{i.base_url.rstrip('/')}/api/assets/{asset_id}/thumbnail",
            params={"size": "preview"},
            headers={"x-api-key": api_key},
            timeout=20,
        )
        upstream.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Immich thumbnail request failed") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Immich thumbnail request failed: {exc}") from exc

    content_type = upstream.headers.get("content-type", "image/jpeg")
    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=300"},
    )


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

    social_cfg = _social_settings_map(db)
    copy_model = social_cfg.get("copy_model", "")
    title = f"{payload.service_category} — {payload.platform}"
    ai_used = True

    try:
        generated = generate_social_content(payload.model_dump(), db, model_override=copy_model)
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
    configured_album_id = _configured_social_album_id(db)
    integration, base_url, api_key = _immich_config(db)
    if not integration or not base_url or not api_key:
        if configured_album_id:
            return [{
                "id": configured_album_id,
                "name": "Configured Immich album",
                "source": "immich",
                "asset_count": 0,
                "configured": False,
            }]
        return []

    try:
        r = httpx.get(
            f"{base_url}/api/albums",
            headers={"x-api-key": api_key},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Immich albums request failed") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Immich albums request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(502, "Immich albums response was not valid JSON") from exc

    albums = data if isinstance(data, list) else data.get("albums", data.get("results", []))
    result = []
    for album in albums:
        if not isinstance(album, dict):
            continue
        album_id = album.get("id")
        if not album_id:
            continue
        result.append({
            "id": album_id,
            "name": album.get("albumName") or album.get("name") or "Immich album",
            "source": "immich",
            "asset_count": album.get("assetCount") or album.get("asset_count") or len(album.get("assets", []) or []),
            "configured": album_id == configured_album_id,
        })

    if configured_album_id and not any(album["id"] == configured_album_id for album in result):
        result.insert(0, {
            "id": configured_album_id,
            "name": "Configured Immich album",
            "source": "immich",
            "asset_count": 0,
            "configured": True,
        })
    return result


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
    "image_generation_model": "",
    "copy_model": "",
    "default_language": "bilingual",
    "default_platforms": "facebook,instagram,gbp",
    "default_tone": "local",
    "default_city": "Montréal",
    "default_cta": "request_quote",
    "default_hashtags": "#montreal #renovation",
    "brand_voice": "Local, practical, trustworthy Bricopro voice",
    "image_picker_prompt": "Help identify clear project photos, but let the user make the final selection.",
    "copy_prompt": "Write practical, local, trustworthy Bricopro social posts based only on the provided job details and selected images.",
    "facebook_prompt": "Facebook: conversational, helpful, local, and clear about the service.",
    "instagram_prompt": "Instagram: concise caption, strong opening line, tasteful emojis, and relevant hashtags.",
    "gbp_prompt": "Google Business Profile: professional, service-focused, local, and direct.",
    "safety_prompt": "Never invent reviews, client names, addresses, prices, certifications, or regulated trade work.",
    "facebook_account": "",
    "instagram_account": "",
    "google_business_account": "",
    "meta_account_id": "",
    "google_ads_account_id": "",
    "meta_ads_account": "",
    "google_ads_account": "",
}


def _social_settings_map(db: Session) -> dict:
    values = {s.key.removeprefix("social_"): s.value for s in db.query(Setting).filter(Setting.key.like("social_%")).all()}
    return {**SOCIAL_SETTING_DEFAULTS, **values}


def _configured_social_album_id(db: Session) -> str:
    return _social_settings_map(db).get("default_album_id", "").strip()


def _immich_config(db: Session) -> tuple[Integration | None, str, str]:
    integration = db.query(Integration).filter(Integration.provider == "immich").first()
    if not integration:
        return None, "", ""
    try:
        config = json.loads(integration.config_json or "{}")
    except Exception:
        config = {}
    api_key = config.get("api_key", "")
    if api_key and all(c == '•' for c in api_key):
        api_key = ""
    return integration, (integration.base_url or "").strip().rstrip("/"), api_key


def _immich_ready(db: Session) -> tuple[Integration, str, str]:
    integration, base_url, api_key = _immich_config(db)
    if not integration or not base_url or not api_key:
        raise HTTPException(400, "Immich integration is not configured.")
    return integration, base_url, api_key


def _fetch_immich_image_b64(asset_id: str, base_url: str, api_key: str) -> str | None:
    """Fetch an Immich asset as a base64 data-URL for direct LLM upload.

    Uses the preview thumbnail (large enough for vision models, small enough
    to be fast). Returns ``None`` and logs a warning on any failure so a bad
    asset ID never aborts the whole generation request.
    """
    import base64 as _base64
    try:
        r = httpx.get(
            f"{base_url}/api/assets/{asset_id}/thumbnail",
            params={"size": "preview"},
            headers={"x-api-key": api_key},
            timeout=30,
        )
        r.raise_for_status()
        content_type = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        b64 = _base64.b64encode(r.content).decode("ascii")
        return f"data:{content_type};base64,{b64}"
    except Exception as exc:
        log.warning("Could not fetch Immich asset %s for LLM upload: %s", asset_id, exc)
        return None


def _immich_asset_payload(asset: dict, base_url: str) -> dict:
    asset_id = asset.get("id") or asset.get("assetId")
    filename = (
        asset.get("originalFileName")
        or asset.get("originalPath")
        or asset.get("fileName")
        or "Untitled photo"
    )
    return {
        "id": asset_id,
        "asset_id": asset_id,
        "title": filename,
        "filename": filename,
        "type": asset.get("type"),
        "created_at": asset.get("fileCreatedAt") or asset.get("createdAt") or asset.get("localDateTime"),
        "thumbnail_url": f"/integrations/immich/assets/{asset_id}/thumbnail" if asset_id else "",
        "asset_url": f"{base_url}/photos/{asset_id}" if asset_id else base_url,
    }


@app.get("/social/settings")
def social_settings(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return _social_settings_map(db)


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


@app.get("/social/immich/albums/{album_id}/assets")
def social_immich_album_assets(
    album_id: str,
    limit: int = Query(default=60, ge=1, le=200),
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    _, base_url, api_key = _immich_ready(db)
    try:
        r = httpx.get(
            f"{base_url}/api/albums/{album_id}",
            headers={"x-api-key": api_key},
            timeout=20,
        )
        r.raise_for_status()
        album = r.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Immich album assets request failed") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Immich album assets request failed: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(502, "Immich album response was not valid JSON") from exc

    assets = [
        asset
        for asset in (album.get("assets", []) if isinstance(album, dict) else [])
        if isinstance(asset, dict) and (asset.get("id") or asset.get("assetId"))
    ]
    return {
        "album_id": album_id,
        "name": (album.get("albumName") or album.get("name") or "Immich album") if isinstance(album, dict) else "Immich album",
        "assets": [_immich_asset_payload(asset, base_url) for asset in assets[:limit]],
    }


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


@app.post("/social/generate-image")
def social_generate_image(payload: dict, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Refine an image generation prompt using the configured chat model.

    Only the prompt supplied on the image generation page is used — brand
    voice and post-generation settings are intentionally excluded here.
    Selected Immich assets are uploaded directly to the LLM as image data
    rather than being appended as text IDs.
    """
    from .services.ai import generate_image_prompt, AINotConfigured, AIError

    social_cfg = _social_settings_map(db)
    prompt = payload.get("prompt", "").strip()
    preset = payload.get("preset", "").strip()
    asset_ids = payload.get("asset_ids", [])

    if not prompt and not preset:
        raise HTTPException(400, "A prompt or preset is required.")

    # Fetch selected Immich images as base64 data-URLs for vision upload.
    reference_images: list[str] = []
    if asset_ids:
        _, immich_base, immich_key = _immich_config(db)
        if immich_base and immich_key:
            for aid in asset_ids:
                img = _fetch_immich_image_b64(str(aid), immich_base, immich_key)
                if img:
                    reference_images.append(img)

    try:
        result = generate_image_prompt(prompt, social_cfg, db, images=reference_images or None)
    except AINotConfigured as exc:
        raise HTTPException(400, str(exc))
    except AIError as exc:
        raise HTTPException(502, f"Image generation failed: {exc}")

    return {
        "prompt_used": prompt,
        "result": result,
        "asset_ids": asset_ids,
    }


@app.post("/social/generate-image-actual")
def social_generate_image_actual(payload: dict, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Generate an actual image using the configured image generation model (DALL-E or compatible).

    Only the prompt supplied on the image generation page is used — brand
    voice and post-generation settings are intentionally excluded here.
    Selected Immich assets are fetched from Immich and uploaded directly to
    the LLM as image data so the model can use them as visual reference.
    """
    import base64
    from pathlib import Path
    from .services.ai import generate_image_prompt, generate_image_dall_e, AINotConfigured, AIError

    social_cfg = _social_settings_map(db)
    prompt = payload.get("prompt", "").strip()
    preset = payload.get("preset", "").strip()
    asset_ids = payload.get("asset_ids", [])
    size = payload.get("size", "1024x1024")
    quality = payload.get("quality", "standard")
    refine_prompt = payload.get("refine_prompt", True)

    if not prompt and not preset:
        raise HTTPException(400, "A prompt or preset is required.")

    # Fetch selected Immich images as base64 data-URLs for vision upload.
    # Failures per-asset are logged and skipped so one bad ID never blocks generation.
    reference_images: list[str] = []
    if asset_ids:
        _, immich_base, immich_key = _immich_config(db)
        if immich_base and immich_key:
            for aid in asset_ids:
                img = _fetch_immich_image_b64(str(aid), immich_base, immich_key)
                if img:
                    reference_images.append(img)

    images_arg = reference_images or None

    final_prompt = prompt
    refined_result = None
    if refine_prompt:
        try:
            refined_result = generate_image_prompt(prompt, social_cfg, db, images=images_arg)
            final_prompt = refined_result.get("image_prompt", prompt)
        except (AINotConfigured, AIError) as exc:
            log.warning("Image prompt refinement skipped (will use raw prompt): %s", exc)

    try:
        result = generate_image_dall_e(final_prompt, social_cfg, db, size=size, quality=quality, images=images_arg)
    except AINotConfigured as exc:
        raise HTTPException(400, str(exc))
    except AIError as exc:
        raise HTTPException(502, f"Image generation failed: {exc}")

    image_id = secrets.token_hex(12)
    image_b64 = result.get("image_b64", "")
    image_url = result.get("image_url", "")

    image_bytes: bytes = b""
    if image_b64:
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            log.error("Generated image base64 could not be decoded: %s", exc)
            raise HTTPException(502, "Generation model returned invalid image data.")
    elif image_url:
        # Some models return a (possibly short-lived / authenticated) URL instead of
        # inline base64. Download it server-side so we (a) can store it, (b) can serve
        # it back through our own endpoint with proper auth, and (c) can upload it to
        # Immich later — the previous behavior of forwarding the raw URL to the
        # browser broke for any host that required headers or wasn't reachable from
        # the user's network.
        try:
            dl = httpx.get(image_url, timeout=60, follow_redirects=True)
            dl.raise_for_status()
            image_bytes = dl.content
        except httpx.HTTPError as exc:
            log.error("Failed to download generated image from %s: %s", image_url, exc)
            raise HTTPException(502, f"Could not retrieve generated image: {exc}")
    else:
        raise HTTPException(502, "No image data returned from the generation model.")

    if not image_bytes:
        raise HTTPException(502, "Generation model returned empty image data.")

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    images_dir = data_dir / "generated_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    image_path = images_dir / f"{image_id}.png"
    image_path.write_bytes(image_bytes)

    # `image_url` is a backend path; in production it is reached via the Next.js
    # `/api/...` proxy and is JWT-protected, so a bare <img src> can't load it.
    # `image_data_url` is what the front-end actually renders — it embeds the bytes
    # directly so no second request (and no auth header) is needed.
    serve_url = f"/social/generated-images/{image_id}"
    image_data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")

    return {
        "image_id": image_id,
        "image_url": serve_url,
        "image_data_url": image_data_url,
        "revised_prompt": result.get("revised_prompt", final_prompt),
        "refined_prompt": refined_result if refined_result else None,
        "model": result.get("model", ""),
        "size": result.get("size", size),
        "prompt_used": final_prompt,
    }


@app.get("/social/generated-images/{image_id}")
def social_generated_image(image_id: str, _: User = Depends(auth_user)):
    """Serve a previously generated image."""
    from pathlib import Path
    import re

    if not re.match(r'^[a-f0-9]+$', image_id):
        raise HTTPException(400, "Invalid image ID")

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    image_path = data_dir / "generated_images" / f"{image_id}.png"
    if not image_path.exists():
        raise HTTPException(404, "Generated image not found")

    return Response(
        content=image_path.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.post("/social/generated-images/{image_id}/upload-to-immich")
def upload_generated_image_to_immich(image_id: str, payload: dict, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Upload a generated image to an Immich album."""
    from pathlib import Path
    import re

    if not re.match(r'^[a-f0-9]+$', image_id):
        raise HTTPException(400, "Invalid image ID")

    data_dir = Path(os.getenv("DATA_DIR", "/data"))
    image_path = data_dir / "generated_images" / f"{image_id}.png"
    if not image_path.exists():
        raise HTTPException(404, "Generated image not found")

    album_id = payload.get("album_id", "").strip()
    _, base_url, api_key = _immich_ready(db)

    image_bytes = image_path.read_bytes()
    filename = payload.get("filename", f"bricopro-generated-{image_id}.png")

    try:
        upload_resp = httpx.post(
            f"{base_url}/api/assets",
            headers={"x-api-key": api_key},
            files={"assetData": (filename, image_bytes, "image/png")},
            data={
                "deviceAssetId": f"bricopro-{image_id}",
                "deviceId": "bricopro-hq",
                "fileCreatedAt": datetime.now(timezone.utc).isoformat(),
                "fileModifiedAt": datetime.now(timezone.utc).isoformat(),
            },
            timeout=60,
        )
        upload_resp.raise_for_status()
        asset_data = upload_resp.json()
        asset_id = asset_data.get("id", "")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, f"Immich upload failed: {exc.response.text[:300]}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(502, f"Immich upload failed: {exc}") from exc

    if album_id and asset_id:
        try:
            add_resp = httpx.put(
                f"{base_url}/api/albums/{album_id}/assets",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={"ids": [asset_id]},
                timeout=20,
            )
            add_resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            log.warning("Failed to add asset to album %s: %s", album_id, exc)

    return {
        "ok": True,
        "asset_id": asset_id,
        "album_id": album_id,
        "filename": filename,
    }


@app.get("/social/image-presets")
def social_image_presets(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Return saved image generation presets."""
    presets_raw = db.query(Setting).filter(Setting.key == "social_image_presets").first()
    if presets_raw and presets_raw.value:
        try:
            return json.loads(presets_raw.value)
        except Exception:
            pass
    return [{"id": "before_after", "name": "Before / After", "prompt": "Create a clean side-by-side before and after comparison of a home renovation project. Show the transformation clearly.", "editable": True}]


@app.put("/social/image-presets")
def save_image_presets(payload: dict, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Save image generation presets."""
    presets = payload.get("presets", [])
    row = db.query(Setting).filter(Setting.key == "social_image_presets").first() or Setting(key="social_image_presets", value="[]")
    row.value = json.dumps(presets)
    db.add(row)
    db.commit()
    return presets


@app.post("/social/generate-pack")
def social_generate_pack(payload: dict, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    from .services.ai import generate_social_content, AINotConfigured, AIError

    social_cfg = _social_settings_map(db)
    copy_model = social_cfg.get("copy_model", "")
    raw_platforms = payload.get("platforms")
    if isinstance(raw_platforms, str):
        platforms = [p.strip() for p in raw_platforms.split(",") if p.strip()]
    elif isinstance(raw_platforms, list):
        platforms = [str(p).strip() for p in raw_platforms if str(p).strip()]
    else:
        platforms = [p.strip() for p in social_cfg.get("default_platforms", "facebook").split(",") if p.strip()]
    platforms = platforms or ["facebook"]
    selected_assets = payload.get("asset_ids") or []
    job_description = payload.get("job_description", "")
    if selected_assets:
        job_description = (
            f"{job_description}\n\nSelected Immich asset IDs: {', '.join(map(str, selected_assets))}."
        ).strip()
    if social_cfg.get("brand_voice"):
        job_description = f"{job_description}\n\nBrand voice: {social_cfg['brand_voice']}".strip()
    if social_cfg.get("copy_prompt"):
        job_description = f"{job_description}\n\nCopy instructions: {social_cfg['copy_prompt']}".strip()
    if social_cfg.get("safety_prompt"):
        job_description = f"{job_description}\n\nSafety rules: {social_cfg['safety_prompt']}".strip()

    drafts = []
    for platform in platforms:
        platform_key = f"{platform}_prompt"
        platform_job_description = job_description
        if social_cfg.get(platform_key):
            platform_job_description = f"{platform_job_description}\n\n{social_cfg[platform_key]}".strip()

        draft_payload = {
            "service_category": payload.get("service_category", "Bricopro project"),
            "platform": platform,
            "language": payload.get("language") or social_cfg.get("default_language", "bilingual"),
            "tone": payload.get("tone") or social_cfg.get("default_tone", "local"),
            "job_description": platform_job_description,
            "city": payload.get("city") or social_cfg.get("default_city", "Montréal"),
            "cta": payload.get("cta") or social_cfg.get("default_cta", "request_quote"),
        }
        ai_used = True
        try:
            generated = generate_social_content(draft_payload, db, model_override=copy_model)
        except AINotConfigured:
            generated = _template_fallback(SimpleNamespace(**draft_payload))
            ai_used = False
        except AIError as exc:
            raise HTTPException(502, f"AI generation failed: {exc}") from exc

        title = f"{draft_payload['service_category']} - {platform}"
        drafts.append({
            "draft_id": None,
            "title": title,
            "platform": platform,
            "main_copy": generated.get("main_copy", ""),
            "short_variation": generated.get("short_variation", ""),
            "hashtags": generated.get("hashtags", ""),
            "cta": generated.get("cta_text") or draft_payload["cta"],
            "selected_assets": selected_assets,
            "visual_direction": "Use the selected project photos as-is; the user made the final image picks.",
            "notes": generated.get("notes", "Review before publishing."),
            "ai_used": ai_used,
        })
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
    return [_draft_payload(d) for d in q.all()]


def _draft_payload(d: ContentDraft) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "platform": d.platform,
        "language": d.language,
        "status": d.status,
        "planned_date": d.planned_date.isoformat() if d.planned_date else None,
        "planned_time": getattr(d, "planned_time", "") or "",
        "campaign_id": d.campaign_id,
        "body": d.body,
        "short_body": d.short_body,
        "hashtags": d.hashtags,
        "cta": d.cta,
        "tone": d.tone,
        "service_category": d.service_category,
        "image_ids": getattr(d, "image_ids", "") or "",
        "platform_post_id": getattr(d, "platform_post_id", None),
        "platform_account_id": getattr(d, "platform_account_id", None),
        "published_at": d.published_at.isoformat() if getattr(d, "published_at", None) else None,
        "publish_error": getattr(d, "publish_error", None),
    }


@app.post("/publishing/drafts")
def create_draft(payload: DraftIn, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    try:
        pd = date.fromisoformat(payload.planned_date) if payload.planned_date else None
        d = ContentDraft(**payload.model_dump(exclude={"planned_date"}), planned_date=pd)
        db.add(d)
        db.commit()
        db.refresh(d)
        return {"id": d.id}
    except Exception as exc:
        db.rollback()
        log.error("create_draft failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not save draft: {exc}")


@app.put("/publishing/drafts/{draft_id}")
def update_draft(
    draft_id: int,
    payload: dict,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    """Full draft update - title, body, status, planned_date, etc."""
    from .schemas import DRAFT_STATUSES
    d = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if not d:
        raise HTTPException(404, "Draft not found")

    if "title" in payload:
        d.title = payload["title"]
    if "body" in payload:
        d.body = payload["body"]
    if "short_body" in payload:
        d.short_body = payload["short_body"]
    if "hashtags" in payload:
        d.hashtags = payload["hashtags"]
    if "cta" in payload:
        d.cta = payload["cta"]
    if "image_ids" in payload:
        d.image_ids = payload["image_ids"]
    if "status" in payload:
        if payload["status"] not in DRAFT_STATUSES:
            raise HTTPException(422, f"Invalid draft status '{payload['status']}'")
        d.status = payload["status"]
    if "planned_date" in payload:
        pd_val = payload["planned_date"]
        d.planned_date = date.fromisoformat(pd_val) if pd_val else None
    if "planned_time" in payload:
        d.planned_time = payload["planned_time"] or ""
    d.updated_at = datetime.utcnow()
    db.commit()
    return {"updated": True, "id": d.id}


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


@app.delete("/publishing/drafts/{draft_id}")
def delete_draft(draft_id: int, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    d = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if not d:
        raise HTTPException(404, "Draft not found")
    db.delete(d)
    db.commit()
    return {"deleted": True, "id": draft_id}


@app.get("/publishing/accounts")
def publishing_accounts(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Return all accounts available for publishing (Facebook Pages, Instagram, GBP locations)."""
    from .services.social_publisher import get_publishable_accounts
    try:
        return get_publishable_accounts(db)
    except Exception as exc:
        log.warning("Error fetching publishing accounts: %s", exc)
        return []


@app.post("/publishing/drafts/{draft_id}/publish")
def publish_draft(
    draft_id: int,
    payload: dict,
    request: Request,
    _: User = Depends(auth_user),
    db: Session = Depends(get_db),
):
    """
    Publish a draft immediately to the selected platform account,
    or schedule it (set status to 'scheduled' with account saved for later).

    payload:
      - platform_account_id: str  (required)
      - schedule: bool            (optional, default false — if true just saves account + status=scheduled)
    """
    d = db.query(ContentDraft).filter(ContentDraft.id == draft_id).first()
    if not d:
        raise HTTPException(404, "Draft not found")

    account_id = (payload.get("platform_account_id") or "").strip()
    if not account_id:
        raise HTTPException(422, "platform_account_id is required")

    schedule_only = bool(payload.get("schedule", False))

    # Always persist the chosen account so the scheduler can use it
    d.platform_account_id = account_id
    d.updated_at = datetime.utcnow()

    if schedule_only:
        d.status = "scheduled"
        db.commit()
        return {"scheduled": True, "draft_id": draft_id}

    app_base = _request_app_base_urls(request).split(",")[0] or os.getenv("APP_BASE_URL", "")
    if not app_base:
        app_base = str(request.base_url).rstrip("/")

    try:
        post_id = _publish_draft(d, db, app_base)
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Publish failed for draft %s: %s", draft_id, exc)
        d.publish_error = str(exc)
        d.updated_at = datetime.utcnow()
        db.commit()
        raise HTTPException(502, f"Publish failed: {exc}") from exc

    # Kick off an immediate insights seed (best-effort; non-blocking via thread)
    import threading
    def _seed():
        try:
            from .services.social_publisher import sync_post_insights
            seed_db = next(get_db())
            sync_post_insights(draft_id, seed_db)
        except Exception as e:
            log.info("Initial insights seed for draft %s: %s", draft_id, e)
    threading.Thread(target=_seed, daemon=True).start()

    return {
        "published": True,
        "draft_id": draft_id,
        "platform_post_id": post_id,
        "published_at": d.published_at.isoformat() if d.published_at else None,
    }


@app.get("/publishing/calendar")
def pub_calendar(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return [
        {
            "id": d.id,
            "title": d.title,
            "platform": d.platform,
            "date": d.planned_date.isoformat() if d.planned_date else None,
            "planned_time": getattr(d, "planned_time", "") or "",
            "status": d.status,
            "image_ids": getattr(d, "image_ids", "") or "",
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
    social_cfg = _social_settings_map(db)
    default_hashtags = social_cfg.get("default_hashtags", "#montreal #renovation")
    d = ContentDraft(
        title=f"{c.name} — draft",
        platform="facebook",
        service_category=c.service_category,
        body=c.message or f"Campagne {c.name} — {c.service_category}",
        short_body=(c.message or c.name)[:120],
        hashtags=default_hashtags,
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


# ── KPI: per-post tracking ────────────────────────────────────────────────────

@app.get("/kpi/posts")
def kpi_posts(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Return all published (or tracked) drafts with their latest PostMetric data."""
    drafts = (
        db.query(ContentDraft)
        .filter(ContentDraft.status.in_(["posted", "scheduled", "failed"]))
        .order_by(ContentDraft.published_at.desc().nullslast(), ContentDraft.updated_at.desc())
        .all()
    )
    result = []
    for d in drafts:
        metric = db.query(PostMetric).filter(PostMetric.draft_id == d.id).first()
        result.append({
            "draft": _draft_payload(d),
            "metric": _metric_payload(metric) if metric else None,
        })
    return result


@app.get("/kpi/posts/{draft_id}/snapshots")
def kpi_post_snapshots(draft_id: int, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Return time-series snapshot data for sparkline charts."""
    snaps = (
        db.query(PostMetricSnapshot)
        .filter(PostMetricSnapshot.draft_id == draft_id)
        .order_by(PostMetricSnapshot.captured_at.asc())
        .all()
    )
    return [
        {
            "captured_at": s.captured_at.isoformat(),
            "impressions": s.impressions,
            "reach": s.reach,
            "clicks": s.clicks,
            "engagements": s.engagements,
            "reactions": s.reactions,
            "shares": s.shares,
            "saves": s.saves,
        }
        for s in snaps
    ]


@app.post("/kpi/sync-post/{draft_id}")
def kpi_sync_post(draft_id: int, _: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Fetch latest platform metrics for a single published draft."""
    from .services.social_publisher import sync_post_insights
    try:
        metrics = sync_post_insights(draft_id, db)
        return {"synced": True, "draft_id": draft_id, "metrics": metrics}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        log.error("kpi_sync_post error for draft %s: %s", draft_id, exc)
        raise HTTPException(502, f"Insights sync failed: {exc}") from exc


@app.post("/kpi/sync-all")
def kpi_sync_all(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    """Bulk sync insights for all published drafts that have a platform_post_id."""
    from .services.social_publisher import sync_post_insights
    drafts = (
        db.query(ContentDraft)
        .filter(
            ContentDraft.status == "posted",
            ContentDraft.platform_post_id.isnot(None),
        )
        .all()
    )
    ok, failed = 0, []
    for d in drafts:
        try:
            sync_post_insights(d.id, db)
            ok += 1
        except Exception as exc:
            failed.append({"draft_id": d.id, "error": str(exc)})
    return {"synced": ok, "failed": failed, "total": len(drafts)}
