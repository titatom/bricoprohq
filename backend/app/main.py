import json
import logging
import os
from datetime import datetime, timezone, timedelta, date

from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from . import db as _db_module
from .db import Base, get_db, _reinit as _db_reinit
_db_reinit()  # re-read DATABASE_URL in case env changed (e.g. test reloads)
from .models import (
    User, Setting, QuickLink, Integration, DashboardCache,
    ContentAsset, ContentDraft, Campaign,
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

SOURCES = ["google_calendar", "jobber", "immich", "paperless"]
CACHE_TTL_MINUTES = 15


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

@app.on_event("startup")
def startup_seed():
    db = next(get_db())
    email = os.getenv("ADMIN_EMAIL", "admin@bricopro.local")
    pwd = os.getenv("ADMIN_PASSWORD", "admin1234")
    if not db.query(User).filter(User.email == email).first():
        db.add(User(email=email, password_hash=hash_password(pwd), role="admin"))
        log.info("Seeded admin user %s", email)
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
    u = db.query(User).filter(User.email == payload.email).first()
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

@app.get("/integrations")
def integrations(_: User = Depends(auth_user), db: Session = Depends(get_db)):
    return [
        {
            "provider": i.provider,
            "base_url": i.base_url,
            "status": i.status,
            "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None,
        }
        for i in db.query(Integration).all()
    ]


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
    i.config_json = payload.config_json
    db.add(i); db.commit()
    return {"updated": True}


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
