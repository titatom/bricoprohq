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


def _resolve_model(cfg: dict, provider: str, model_override: str = "") -> str:
    """Pick the effective model: explicit override > global ai_model > provider default."""
    override = (model_override or "").strip()
    if override:
        return override
    global_model = cfg.get("ai_model", "").strip()
    if global_model:
        return global_model
    return DEFAULT_MODELS.get(provider, "gpt-4o-mini")


def _dispatch_llm(
    cfg: dict,
    provider: str,
    model: str,
    system: str,
    user: str,
) -> dict:
    """Route a chat-completion call to the right backend."""
    api_key = cfg.get("ai_api_key", "").strip()
    base_url = cfg.get("ai_base_url", "").strip()

    if provider == "ollama":
        effective_base = base_url or OLLAMA_DEFAULT_BASE
        return _call_ollama(effective_base, model, system, user)

    if provider in ("openai", "openrouter"):
        if not api_key:
            raise AINotConfigured(f"API key not configured for {provider}. Go to Settings → AI Provider.")
        if provider == "openai":
            effective_base = base_url or OPENAI_DEFAULT_BASE
            extra = None
        else:
            effective_base = base_url or OPENROUTER_DEFAULT_BASE
            extra = {
                "HTTP-Referer": "https://bricopro.ca",
                "X-Title":      "Bricopro HQ",
            }
        return _call_openai_compatible(effective_base, api_key, model, system, user, extra_headers=extra)

    raise AINotConfigured(f"Unknown provider '{provider}'. Choose openai, openrouter, or ollama in Settings.")


def generate_social_content(payload: dict, db: Session, model_override: str = "") -> dict:
    """
    Call the configured AI provider and return a structured content dict.

    ``model_override`` lets callers pass a Social-Studio-specific model
    (e.g. the ``copy_model`` setting) that takes priority over the global
    ``ai_model`` from Settings → AI Provider.

    Raises AINotConfigured if no provider is set up, AIError on call failures.
    """
    cfg = _get_settings(db)
    provider = cfg.get("ai_provider", "").strip()

    if not provider:
        raise AINotConfigured("No AI provider configured. Go to Settings → AI Provider.")

    effective_model = _resolve_model(cfg, provider, model_override)

    system = _build_system_prompt()
    user   = _build_user_prompt(payload)

    log.info("AI generate: provider=%s model=%s (override=%s) platform=%s lang=%s",
             provider, effective_model, model_override or "<none>",
             payload.get("platform"), payload.get("language"))

    result = _dispatch_llm(cfg, provider, effective_model, system, user)

    return {
        "main_copy":       result.get("main_copy", ""),
        "short_variation": result.get("short_variation", ""),
        "hashtags":        result.get("hashtags", "#montreal #bricopro #renovation"),
        "cta_text":        result.get("cta_text", ""),
        "notes":           result.get("notes", "Review before publishing."),
    }


def generate_image_prompt(prompt: str, social_cfg: dict, db: Session) -> dict:
    """
    Send an image generation prompt to the configured image generation model.

    Model priority: image_generation_model > copy_model > global ai_model.
    """
    cfg = _get_settings(db)
    provider = cfg.get("ai_provider", "").strip()

    if not provider:
        raise AINotConfigured("No AI provider configured. Go to Settings → AI Provider.")

    image_model = (social_cfg.get("image_generation_model") or "").strip()
    copy_model = (social_cfg.get("copy_model") or "").strip()
    model_override = image_model or copy_model
    effective_model = _resolve_model(cfg, provider, model_override)

    system = (
        "You are an AI image generation assistant for Bricopro, a Montreal home renovation contractor. "
        "You help create image prompts and visual descriptions for social media content. "
        "Given the user's description, generate a detailed image generation prompt suitable for "
        "DALL-E, Stable Diffusion, or similar tools.\n\n"
        "Return a JSON object with these keys:\n"
        '{\n'
        '  "image_prompt": "detailed prompt for image generation",\n'
        '  "style": "suggested style (photo-realistic, illustration, etc.)",\n'
        '  "aspect_ratio": "suggested aspect ratio (1:1, 4:5, 16:9)",\n'
        '  "notes": "any notes for the user about the generated image"\n'
        '}\n'
        "Return only valid JSON. No markdown fences."
    )

    log.info("AI image generate: provider=%s model=%s (override=%s)", provider, effective_model, model_override or "<none>")

    result = _dispatch_llm(cfg, provider, effective_model, system, prompt)

    return {
        "image_prompt": result.get("image_prompt", prompt),
        "style": result.get("style", "photo-realistic"),
        "aspect_ratio": result.get("aspect_ratio", "1:1"),
        "notes": result.get("notes", "Review the prompt before generating."),
    }


def _is_gpt_image_model(model: str) -> bool:
    """Return True for OpenAI GPT-image family models (gpt-image-1, gpt-image-2, etc.)."""
    return model.startswith("gpt-image")


_DALLE_QUALITY_TO_GPT = {"standard": "medium", "hd": "high"}
_DALLE_SIZE_TO_GPT = {"1792x1024": "1536x1024", "1024x1792": "1024x1536"}


def _build_image_gen_body(model: str, prompt: str, size: str, quality: str) -> dict:
    """Build the JSON body for /images/generations, adapting for model family."""
    if _is_gpt_image_model(model):
        mapped_quality = _DALLE_QUALITY_TO_GPT.get(quality, quality)
        if mapped_quality not in ("low", "medium", "high", "auto"):
            mapped_quality = "auto"
        mapped_size = _DALLE_SIZE_TO_GPT.get(size, size)
        return {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": mapped_size,
            "quality": mapped_quality,
        }

    return {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "response_format": "b64_json",
    }


def _generate_image_openrouter(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    size: str,
    quality: str,
) -> dict:
    """Generate an image via OpenRouter's chat/completions with image modalities."""
    effective_base = base_url or OPENROUTER_DEFAULT_BASE
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bricopro.ca",
        "X-Title": "Bricopro HQ",
    }

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image"],
        "max_tokens": 4096,
    }

    log.info("AI image generation (OpenRouter chat): model=%s size=%s", model, size)

    try:
        r = httpx.post(
            f"{effective_base.rstrip('/')}/chat/completions",
            json=body,
            headers=headers,
            timeout=180,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.error("OpenRouter image gen HTTP %s: %s", exc.response.status_code, exc.response.text[:500])
        raise AIError(f"Image generation HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
    except httpx.RequestError as exc:
        log.error("OpenRouter image gen request failed: %s", exc)
        raise AIError(f"Image generation request failed: {exc}") from exc

    try:
        data = r.json()
        choices = data.get("choices", [])
        if not choices:
            raise AIError("OpenRouter returned no choices for image generation.")

        message = choices[0].get("message", {})
        content = message.get("content")

        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    image_url = part.get("image_url", {})
                    url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
                    if url.startswith("data:image/"):
                        import base64 as _b64
                        b64_data = url.split(",", 1)[1] if "," in url else ""
                        return {
                            "image_b64": b64_data,
                            "image_url": "",
                            "revised_prompt": prompt,
                            "model": model,
                            "size": size,
                        }
                    return {
                        "image_b64": "",
                        "image_url": url,
                        "revised_prompt": prompt,
                        "model": model,
                        "size": size,
                    }

        raise AIError(
            "OpenRouter image generation did not return image data. "
            "Make sure the model supports image output (check OpenRouter docs for image-capable models)."
        )
    except AIError:
        raise
    except Exception as exc:
        raise AIError(f"Unexpected OpenRouter image response: {exc}") from exc


def generate_image_dall_e(prompt: str, social_cfg: dict, db: Session, size: str = "1024x1024", quality: str = "standard") -> dict:
    """
    Generate an image using the OpenAI Images API (or compatible endpoint).

    Supports dall-e-2, dall-e-3, gpt-image-1, gpt-image-2, and OpenRouter
    image models. Automatically maps parameters for each model family.
    """
    cfg = _get_settings(db)
    provider = cfg.get("ai_provider", "").strip()

    if not provider:
        raise AINotConfigured("No AI provider configured. Go to Settings → AI Provider.")

    api_key = cfg.get("ai_api_key", "").strip()
    base_url = cfg.get("ai_base_url", "").strip()

    if provider == "ollama":
        raise AIError("Ollama does not support image generation. Use OpenAI or OpenRouter with an image model.")

    if not api_key:
        raise AINotConfigured(f"API key not configured for {provider}. Go to Settings → AI Provider.")

    image_model = (social_cfg.get("image_generation_model") or "").strip()
    effective_model = image_model or "dall-e-3"

    log.info(
        "AI image generation: provider=%s model=%s size=%s quality=%s",
        provider, effective_model, size, quality,
    )

    if provider == "openrouter":
        return _generate_image_openrouter(api_key, base_url, effective_model, prompt, size, quality)

    effective_base = base_url or OPENAI_DEFAULT_BASE

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body = _build_image_gen_body(effective_model, prompt, size, quality)

    try:
        r = httpx.post(
            f"{effective_base.rstrip('/')}/images/generations",
            json=body,
            headers=headers,
            timeout=180,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.error(
            "Image generation HTTP %s from %s: %s",
            exc.response.status_code, provider, exc.response.text[:500],
        )
        raise AIError(f"Image generation HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
    except httpx.RequestError as exc:
        log.error("Image generation request to %s failed: %s", provider, exc)
        raise AIError(f"Image generation request failed: {exc}") from exc

    try:
        data = r.json()["data"][0]
        return {
            "image_b64": data.get("b64_json", ""),
            "image_url": data.get("url", ""),
            "revised_prompt": data.get("revised_prompt", prompt),
            "model": effective_model,
            "size": size,
        }
    except (KeyError, IndexError) as exc:
        log.error("Unexpected image generation response from %s: %s", provider, exc)
        raise AIError(f"Unexpected image generation response format: {exc}") from exc


def test_connection(db: Session) -> dict:
    """Send a minimal prompt to verify the provider is reachable and the key works."""
    cfg = _get_settings(db)
    provider = cfg.get("ai_provider", "").strip()

    if not provider:
        raise AINotConfigured("No AI provider configured.")

    effective_model = _resolve_model(cfg, provider)
    ping_prompt = 'Reply with exactly this JSON: {"ok": true, "message": "Bricopro HQ connection test successful"}'

    result = _dispatch_llm(cfg, provider, effective_model, "You are a helpful assistant.", ping_prompt)

    return {"ok": True, "message": result.get("message", "Connection successful"), "provider": provider, "model": effective_model}
