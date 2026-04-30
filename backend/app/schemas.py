from pydantic import BaseModel, field_validator

# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserMeResponse(BaseModel):
    email: str
    role: str

# ── Settings / Quick Links ────────────────────────────────────────────────────

class QuickLinkIn(BaseModel):
    title: str
    url: str
    category: str = "general"
    icon: str = "link"
    sort_order: int = 0
    is_active: bool = True

class QuickLinkOut(QuickLinkIn):
    id: int
    model_config = {"from_attributes": True}

class SettingIn(BaseModel):
    value: str

class SettingOut(BaseModel):
    id: int
    key: str
    value: str
    model_config = {"from_attributes": True}

# ── Integrations ──────────────────────────────────────────────────────────────

class IntegrationUpdateIn(BaseModel):
    base_url: str = ""
    config_json: str = "{}"

class IntegrationOut(BaseModel):
    provider: str
    base_url: str
    status: str
    last_sync_at: str | None = None
    config_fields: dict = {}
    oauth_connected: bool = False
    class Config: from_attributes = True

# ── Queues ────────────────────────────────────────────────────────────────────

IMAGE_STATUSES = {
    "new", "pending_ai", "needs_review", "business_photo", "personal_photo",
    "trash_candidate", "social_worthy", "website_worthy", "needs_client_approval",
    "used_in_content", "do_not_publish",
}
DOC_STATUSES = {
    "new", "pending_ai", "needs_review", "business_receipt", "personal_document",
    "missing_tags", "missing_correspondent", "missing_document_type", "ready",
}
ALL_ASSET_STATUSES = IMAGE_STATUSES | DOC_STATUSES

class AssetStatusIn(BaseModel):
    status: str
    note: str = ""

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in ALL_ASSET_STATUSES:
            raise ValueError(f"Invalid status '{v}'")
        return v

class AssetCreateIn(BaseModel):
    title: str
    source: str
    source_url: str = ""
    service_category: str = ""
    status: str = "new"

    @field_validator("source")
    @classmethod
    def valid_source(cls, v: str) -> str:
        if v not in {"immich", "immich-gpt", "paperless", "paperless-gpt"}:
            raise ValueError(f"Unknown source '{v}'")
        return v

# ── Social Studio ─────────────────────────────────────────────────────────────

PLATFORMS = {"facebook", "instagram", "gbp", "linkedin", "website", "ad", "email_sms"}
LANGUAGES = {"fr", "en", "bilingual"}

class SocialGenerateIn(BaseModel):
    service_category: str
    platform: str
    language: str = "fr"
    tone: str = "professional"
    job_description: str = ""
    city: str = "Montréal"
    cta: str = "request_quote"
    album_id: str = ""
    candidate_id: int | None = None
    image_refs: str = ""
    before_after_notes: str = ""

    @field_validator("platform")
    @classmethod
    def valid_platform(cls, v: str) -> str:
        if v not in PLATFORMS:
            raise ValueError(f"Unknown platform '{v}'")
        return v

    @field_validator("language")
    @classmethod
    def valid_lang(cls, v: str) -> str:
        if v not in LANGUAGES:
            raise ValueError(f"Unknown language '{v}'")
        return v

# ── Drafts ────────────────────────────────────────────────────────────────────

DRAFT_STATUSES = {
    "idea", "draft_generated", "needs_images", "needs_review", "approved",
    "scheduled", "posted", "reuse_later", "turn_into_ad", "turn_into_page", "archived",
}

class DraftIn(BaseModel):
    title: str
    platform: str
    language: str = "fr"
    tone: str = "professional"
    service_category: str = ""
    body: str = ""
    short_body: str = ""
    hashtags: str = ""
    cta: str = "request_quote"
    status: str = "draft_generated"
    planned_date: str | None = None
    campaign_id: int | None = None

class DraftStatusIn(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in DRAFT_STATUSES:
            raise ValueError(f"Invalid draft status '{v}'")
        return v

# ── Campaigns ─────────────────────────────────────────────────────────────────

CAMPAIGN_STATUSES = {"draft", "active", "paused", "completed", "archived"}

class CampaignIn(BaseModel):
    name: str
    service_category: str = ""
    status: str = "draft"
    message: str = ""

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in CAMPAIGN_STATUSES:
            raise ValueError(f"Invalid campaign status '{v}'")
        return v

# ── KPI / Performance ─────────────────────────────────────────────────────────

class PostMetricIn(BaseModel):
    draft_id: int | None = None
    campaign_id: int | None = None
    title: str = ""
    campaign_name: str = ""
    platform: str
    post_url: str = ""
    post_id: str = ""
    published_date: str | None = None
    spend: float = 0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    leads: int = 0
    messages: int = 0
    calls: int = 0
    engagements: int = 0
    engagement_rate: float = 0
    notes: str = ""
