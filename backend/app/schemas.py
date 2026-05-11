from pydantic import BaseModel, Field, field_validator

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

INTEGRATION_STATUSES = {"unknown", "not_connected", "ok", "error"}


class IntegrationUpdateIn(BaseModel):
    base_url: str = ""
    config_json: str = "{}"

class IntegrationOut(BaseModel):
    provider: str
    base_url: str
    status: str
    last_sync_at: str | None = None
    last_error: str = ""
    last_error_at: str | None = None
    upstream_version: str = ""
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

# ── Social Studio (additional endpoints) ──────────────────────────────────────


class SocialCandidatesIn(BaseModel):
    album_id: str = "recent-work"
    service_category: str = "Exterior painting"


class SocialAnalyzeAlbumIn(BaseModel):
    album_id: str = "recent-work"
    service_category: str = "Exterior painting"


class SocialGenerateImageIn(BaseModel):
    prompt: str = ""
    preset: str = ""
    asset_ids: list[str] = Field(default_factory=list)


class SocialGenerateImageActualIn(BaseModel):
    prompt: str = ""
    preset: str = ""
    asset_ids: list[str] = Field(default_factory=list)
    size: str = "1024x1024"
    quality: str = "standard"
    refine_prompt: bool = True


class UploadGeneratedImageToImmichIn(BaseModel):
    album_id: str = ""
    filename: str = ""


class ImagePresetIn(BaseModel):
    id: str
    name: str
    prompt: str
    editable: bool = True


class SaveImagePresetsIn(BaseModel):
    presets: list[ImagePresetIn] = Field(default_factory=list)


class SocialGeneratePackIn(BaseModel):
    service_category: str = "Bricopro project"
    platforms: list[str] | str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    before_after_requested: bool = False
    before_after: bool = False
    job_description: str = ""
    language: str | None = None
    tone: str | None = None
    city: str | None = None
    cta: str | None = None


class SocialSettingsIn(BaseModel):
    # Free-form, lots of optional knobs; we type the dict as ``dict[str, str]``
    # so callers cannot pass arbitrary nested data, but every known key from
    # SOCIAL_SETTING_DEFAULTS is still accepted.
    model_config = {"extra": "allow"}


class DraftUpdateIn(BaseModel):
    """Partial update for a content draft.

    All fields are optional so callers can patch one attribute at a time.
    """
    title: str | None = None
    body: str | None = None
    short_body: str | None = None
    hashtags: str | None = None
    cta: str | None = None
    image_ids: str | None = None
    status: str | None = None
    planned_date: str | None = None
    planned_time: str | None = None


class CampaignGenerateIn(BaseModel):
    platform: str | None = None
    language: str | None = None
    tone: str | None = None
    cta: str | None = None
    city: str | None = None
    job_description: str | None = None
    service_category: str | None = None


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
    image_ids: str = ""
    status: str = "draft_generated"
    planned_date: str | None = None
    planned_time: str = ""
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
