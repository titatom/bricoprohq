from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, Text, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator
from .db import Base


class EncryptedText(TypeDecorator):
    """
    Transparent at-rest encryption for `Text` columns.

    Values are encrypted on write and decrypted on read. Plaintext values
    written before this column type was introduced are read back unchanged
    (the prefix-tagged ciphertext format makes legacy rows distinguishable),
    and they are upgraded to ciphertext the next time the row is updated.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        from .services.crypto import encrypt
        return encrypt(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        from .services.crypto import decrypt
        return decrypt(value)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Setting(Base):
    __tablename__ = "settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Settings include API keys (for example ai_api_key), so store values encrypted.
    value: Mapped[str] = mapped_column(EncryptedText, default="")

class QuickLink(Base):
    __tablename__ = "quick_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(1000))
    category: Mapped[str] = mapped_column(String(100), default="general")
    icon: Mapped[str] = mapped_column(String(100), default="link")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class Integration(Base):
    __tablename__ = "integrations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(1000), default="")
    auth_type: Mapped[str] = mapped_column(String(100), default="none")
    status: Mapped[str] = mapped_column(String(50), default="unknown")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # config_json contains API keys and OAuth client secrets — encrypted at rest.
    config_json: Mapped[str] = mapped_column(EncryptedText, default="{}")
    oauth_access_token: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    oauth_refresh_token: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    oauth_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OAuthState(Base):
    """
    Short-lived CSRF state tokens for in-flight OAuth authorization requests.
    Persisted so the callback can verify state across worker restarts and
    multi-process deployments. Rows older than `expires_at` are treated as
    invalid and may be cleaned up at any time.
    """
    __tablename__ = "oauth_states"
    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class DashboardCache(Base):
    __tablename__ = "dashboard_cache"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    service_category: Mapped[str] = mapped_column(String(255), default="")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_neighbourhoods: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    notes: Mapped[str] = mapped_column(Text, default="")

class ContentAsset(Base):
    __tablename__ = "content_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(String(1000), default="")
    title: Mapped[str] = mapped_column(String(255), default="")
    service_category: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(100), default="new")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ContentDraft(Base):
    __tablename__ = "content_drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    platform: Mapped[str] = mapped_column(String(100), default="facebook")
    language: Mapped[str] = mapped_column(String(20), default="fr")
    tone: Mapped[str] = mapped_column(String(100), default="professional")
    service_category: Mapped[str] = mapped_column(String(255), default="")
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    short_body: Mapped[str] = mapped_column(Text, default="")
    hashtags: Mapped[str] = mapped_column(Text, default="")
    cta: Mapped[str] = mapped_column(String(255), default="request_quote")
    image_ids: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(100), default="draft_generated")
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_time: Mapped[str] = mapped_column(String(10), default="")
    # Social publishing tracking
    platform_post_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    platform_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publish_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PostMetricSnapshot(Base):
    """Time-series snapshots of platform metrics for a published draft."""
    __tablename__ = "post_metric_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("content_drafts.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    engagements: Mapped[int] = mapped_column(Integer, default=0)
    reactions: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)


class PostMetric(Base):
    __tablename__ = "post_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int | None] = mapped_column(ForeignKey("content_drafts.id"), nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    campaign_name: Mapped[str] = mapped_column(String(255), default="")
    platform: Mapped[str] = mapped_column(String(100), default="facebook")
    post_url: Mapped[str] = mapped_column(String(1000), default="")
    post_id: Mapped[str] = mapped_column(String(255), default="")
    posted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    spend_cents: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    engagements: Mapped[int] = mapped_column(Integer, default=0)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0)
    leads: Mapped[int] = mapped_column(Integer, default=0)
    messages: Mapped[int] = mapped_column(Integer, default=0)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
