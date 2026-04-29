"""
AI generation service for Bricopro HQ.

Supports OpenAI, OpenRouter (OpenAI-compatible), and Ollama.
Reads provider/key/model/base_url from the settings table at call time —
no restart required when credentials change.
"""

import json
import logging
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from ..models import Setting

log = logging.getLogger("bricopro.ai")

OLLAMA_DEFAULT_BASE = "http://localhost:11434"
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"
OPENROUTER_DEFAULT_BASE = "https://openrouter.ai/api/v1"

DEFAULT_MODELS = {
    "openai":      "gpt-4o-mini",
    "openrouter":  "openai/gpt-4o-mini",
    "ollama":      "llama3.2",
}


class AINotConfigured(Exception):
    pass


class AIError(Exception):
    pass


def _get_settings(db: Session) -> dict:
    rows = db.query(Setting).filter(Setting.key.in_([
        "ai_provider", "ai_api_key", "ai_base_url", "ai_model",
    ])).all()
    return {r.key: r.value for r in rows}


def _build_system_prompt() -> str:
    return (
        "You are the AI content assistant for Bricopro, a local Montreal home renovation "
        "and handyman contractor. Bricopro is professional, friendly, licensed and insured.\n\n"
        "Rules you must always follow:\n"
        "- Never invent client testimonials or fake reviews.\n"
        "- Never invent prices or guarantee cost ranges.\n"
        "- Never claim certifications Bricopro does not hold.\n"
        "- Never mention specialized licensed trades (electrician, plumber, gasfitter) unless the user explicitly states Bricopro performed that work.\n"
        "- Never publish client names, addresses, or personal information.\n"
        "- Always keep content review-first — remind the user to review before posting.\n"
        "- French should be used for local homeowner content; English for broader reach; bilingual for both.\n"
        "- Keep the tone practical, trustworthy, and neighbourly. Not corporate.\n"
    )


def _build_user_prompt(payload: dict) -> str:
    platform_hints = {
        "facebook":  "Write a Facebook post (150-300 words). Conversational, a bit storytelling, ends with CTA.",
        "instagram": "Write an Instagram caption (100-150 words). Engaging opening line, emojis welcome, 5-10 hashtags at the end.",
        "gbp":       "Write a Google Business Profile post (150-250 words). Professional, focuses on the service and local area.",
        "linkedin":  "Write a LinkedIn post (200-350 words). Professional tone, highlight craftsmanship and business value.",
        "website":   "Write a project gallery description / case study (250-400 words). Describe the problem, approach, and result.",
        "ad":        "Write 3 short ad copy variants (headline + 1-2 lines each). Punchy, benefit-focused, clear CTA.",
        "email_sms": "Write a short email or SMS message (50-120 words). Direct, personal, clear action.",
    }
    platform_hint = platform_hints.get(payload.get("platform", "facebook"), platform_hints["facebook"])

    tone_hints = {
        "professional":  "Tone: professional and competent.",
        "friendly":      "Tone: warm, friendly, approachable.",
        "local":         "Tone: local and neighbourly — like a neighbour recommending a contractor.",
        "premium":       "Tone: premium and high-quality — worth the investment.",
        "educational":   "Tone: educational — teach the reader something useful about home maintenance.",
        "urgent":        "Tone: seasonal urgency — now is the right time to act before it's too late.",
        "trust":         "Tone: trust-building — focus on reliability, licence, insurance, past work.",
        "before_after":  "Tone: before/after showcase — describe the transformation vividly.",
    }
    tone_hint = tone_hints.get(payload.get("tone", "professional"), tone_hints["professional"])

    cta_labels = {
        "request_quote":    "Call to action: invite them to request a free quote.",
        "book_spring":      "Call to action: book their spring work now before the calendar fills.",
        "book_winter":      "Call to action: book before winter — last spots available.",
        "visit_website":    "Call to action: visit the Bricopro website to see more projects.",
        "call_message":     "Call to action: call or message Bricopro directly.",
        "ask_availability": "Call to action: ask about availability for this season.",
        "leave_review":     "Call to action: leave a Google review if they were happy.",
        "see_projects":     "Call to action: see more projects on our Instagram or website.",
    }
    cta_hint = cta_labels.get(payload.get("cta", "request_quote"), cta_labels["request_quote"])

    lang = payload.get("language", "fr")
    if lang == "fr":
        lang_hint = "Write entirely in French (Québec French is preferred)."
    elif lang == "en":
        lang_hint = "Write entirely in English."
    else:
        lang_hint = "Write in both French and English — provide the French version first, then English below."

    job_desc = payload.get("job_description", "").strip()
    job_line = f"\nJob description provided by the user: {job_desc}" if job_desc else ""

    return (
        f"Generate social media content for Bricopro.\n\n"
        f"Service category: {payload.get('service_category', 'renovation')}\n"
        f"Location/neighbourhood: {payload.get('city', 'Montréal')}\n"
        f"Platform: {payload.get('platform', 'facebook')}\n"
        f"{job_line}\n\n"
        f"{platform_hint}\n"
        f"{tone_hint}\n"
        f"{cta_hint}\n"
        f"{lang_hint}\n\n"
        "Return a JSON object with these exact keys:\n"
        "{\n"
        '  "main_copy": "full post text",\n'
        '  "short_variation": "shorter version (under 120 chars)",\n'
        '  "hashtags": "space-separated hashtags without # symbol — add # yourself",\n'
        '  "cta_text": "the call-to-action sentence to append",\n'
        '  "notes": "any important notes for the user to review before posting"\n'
        "}\n"
        "Return only valid JSON with those 5 keys. No markdown fences."
    )


def _call_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    extra_headers: Optional[dict] = None,
    timeout: int = 30,
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "temperature": 0.7,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }

    try:
        r = httpx.post(f"{base_url.rstrip('/')}/chat/completions", json=body, headers=headers, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AIError(f"HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.RequestError as exc:
        raise AIError(f"Request failed: {exc}") from exc

    try:
        content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as exc:
        raise AIError(f"Could not parse AI response as JSON: {exc}") from exc


def _call_ollama(base_url: str, model: str, system: str, user: str) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.7},
    }
    try:
        r = httpx.post(f"{base_url.rstrip('/')}/api/chat", json=body, timeout=60)
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise AIError(f"Ollama HTTP {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.RequestError as exc:
        raise AIError(f"Ollama request failed: {exc}") from exc

    try:
        content = r.json()["message"]["content"]
        return json.loads(content)
    except Exception as exc:
        raise AIError(f"Could not parse Ollama response: {exc}") from exc


def generate_social_content(payload: dict, db: Session) -> dict:
    """
    Call the configured AI provider and return a structured content dict.
    Raises AINotConfigured if no provider is set up, AIError on call failures.
    """
    cfg = _get_settings(db)
    provider = cfg.get("ai_provider", "").strip()
    api_key  = cfg.get("ai_api_key",  "").strip()
    base_url = cfg.get("ai_base_url", "").strip()
    model    = cfg.get("ai_model",    "").strip()

    if not provider:
        raise AINotConfigured("No AI provider configured. Go to Settings → AI Provider.")

    system = _build_system_prompt()
    user   = _build_user_prompt(payload)

    log.info("AI generate: provider=%s model=%s platform=%s lang=%s",
             provider, model, payload.get("platform"), payload.get("language"))

    if provider == "ollama":
        effective_base  = base_url or OLLAMA_DEFAULT_BASE
        effective_model = model or DEFAULT_MODELS["ollama"]
        result = _call_ollama(effective_base, effective_model, system, user)

    elif provider in ("openai", "openrouter"):
        if not api_key:
            raise AINotConfigured(f"API key not configured for {provider}. Go to Settings → AI Provider.")
        if provider == "openai":
            effective_base  = base_url or OPENAI_DEFAULT_BASE
            effective_model = model or DEFAULT_MODELS["openai"]
            extra = None
        else:
            effective_base  = base_url or OPENROUTER_DEFAULT_BASE
            effective_model = model or DEFAULT_MODELS["openrouter"]
            extra = {
                "HTTP-Referer": "https://bricopro.ca",
                "X-Title":      "Bricopro HQ",
            }
        result = _call_openai_compatible(effective_base, api_key, effective_model, system, user, extra_headers=extra)
    else:
        raise AINotConfigured(f"Unknown provider '{provider}'. Choose openai, openrouter, or ollama in Settings.")

    # Normalise — ensure all expected keys exist
    return {
        "main_copy":       result.get("main_copy", ""),
        "short_variation": result.get("short_variation", ""),
        "hashtags":        result.get("hashtags", "#montreal #bricopro #renovation"),
        "cta_text":        result.get("cta_text", ""),
        "notes":           result.get("notes", "Review before publishing."),
    }


def test_connection(db: Session) -> dict:
    """Send a minimal prompt to verify the provider is reachable and the key works."""
    cfg = _get_settings(db)
    provider = cfg.get("ai_provider", "").strip()
    api_key  = cfg.get("ai_api_key",  "").strip()
    base_url = cfg.get("ai_base_url", "").strip()
    model    = cfg.get("ai_model",    "").strip()

    if not provider:
        raise AINotConfigured("No AI provider configured.")

    ping_prompt = 'Reply with exactly this JSON: {"ok": true, "message": "Bricopro HQ connection test successful"}'

    if provider == "ollama":
        effective_base  = base_url or OLLAMA_DEFAULT_BASE
        effective_model = model or DEFAULT_MODELS["ollama"]
        result = _call_ollama(effective_base, effective_model, "You are a helpful assistant.", ping_prompt)
    elif provider in ("openai", "openrouter"):
        if not api_key:
            raise AINotConfigured(f"API key not configured for {provider}.")
        effective_base  = base_url  or (OPENAI_DEFAULT_BASE if provider == "openai" else OPENROUTER_DEFAULT_BASE)
        effective_model = model or DEFAULT_MODELS.get(provider, "gpt-4o-mini")
        extra = ({"HTTP-Referer": "https://bricopro.ca", "X-Title": "Bricopro HQ"} if provider == "openrouter" else None)
        result = _call_openai_compatible(effective_base, api_key, effective_model,
                                         "You are a helpful assistant.", ping_prompt, extra_headers=extra, timeout=15)
    else:
        raise AINotConfigured(f"Unknown provider '{provider}'.")

    return {"ok": True, "message": result.get("message", "Connection successful"), "provider": provider, "model": effective_model}
