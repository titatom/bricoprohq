from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
class UserMeResponse(BaseModel):
    email: EmailStr
    role: str

class QuickLinkIn(BaseModel):
    title: str
    url: str
    category: str = "general"
    icon: str = "link"
    sort_order: int = 0
    is_active: bool = True
class QuickLinkOut(QuickLinkIn):
    id: int
    class Config: from_attributes = True

class SettingIn(BaseModel):
    value: str
class SettingOut(BaseModel):
    id: int
    key: str
    value: str
    class Config: from_attributes = True

class AssetStatusIn(BaseModel):
    status: str
    note: str = ""

class SocialGenerateIn(BaseModel):
    service_category: str
    platform: str
    language: str = "fr"
    tone: str = "professional"
    job_description: str = ""
    city: str = "Montreal"
    cta: str = "request_quote"

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

class CampaignIn(BaseModel):
    name: str
    service_category: str = ""
    status: str = "draft"
    message: str = ""
