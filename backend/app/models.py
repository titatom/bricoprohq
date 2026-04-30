from datetime import datetime, date
from sqlalchemy import String, Integer, Boolean, DateTime, Date, Text, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

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
    value: Mapped[str] = mapped_column(Text, default="")

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
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    oauth_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
    status: Mapped[str] = mapped_column(String(100), default="draft_generated")
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
