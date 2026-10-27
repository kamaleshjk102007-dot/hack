# ============================================================
# E.D.I.T.H. — Cloud Multi-Provider Task Router  (v7)
#
# Classifies each incoming request by task type, then walks that
# task's priority list top to bottom. On error / timeout / 429 it
# logs the failure, puts that provider on cooldown, and retries the
# SAME request on the next model in the list automatically — no
# user prompt, no giving up after one failure. Only surfaces an
# error once every model for that task type has failed.
#
# Task types: code, project, search, agent, safety, vision,
#             stt, tts, image, video
# ============================================================

import re
import time
import threading
import requests

# ── Pooled HTTP session (connection reuse) ─────────────────────
# One Session per process instead of creating a fresh TCP/TLS
# connection on every provider call — cuts handshake latency on
# back-to-back requests to the same host (Gemini/Groq/OpenRouter).
_SHARED_HTTP_SESSION = requests.Session()
_SHARED_HTTP_SESSION.trust_env = False
_adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
_SHARED_HTTP_SESSION.mount('https://', _adapter)
_SHARED_HTTP_SESSION.mount('http://', _adapter)

from config.settings import (
    GROQ_API_KEY, GROQ_MODEL_CODE, GROQ_MODEL_LLAMA33,
    GROQ_MODEL_VISION, GROQ_MODEL_QWEN, GROQ_MODEL_SAFETY,
    GROQ_MODEL_WHISPER_TURBO, GROQ_MODEL_WHISPER,
    GROQ_MODEL_TTS_EN, GROQ_MODEL_TTS_AR,
    MISTRAL_API_KEY, MISTRAL_MODEL,
    GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_PRO_MODEL, GEMINI_API_URL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
    HF_API_KEY, HF_IMAGE_MODELS, HF_VIDEO_MODELS,
    POLLINATIONS_API_KEY, POLLINATIONS_VIDEO_MODEL,
    KLING_API_KEY, KLING_API_URL,
    TEMPERATURE,
)
from utils.logger import get_logger

log = get_logger("cloud_router")

CHAT_MAX_TOKENS = 3072
CODE_MAX_TOKENS = 8192

# ── Safety net for the Groq gpt-oss reasoning-leak bug ────────────
# Groq has an acknowledged, intermittent bug (community.groq.com/t/670)
# where even reasoning_format="hidden" occasionally fails to strip the
# model's internal "analysis" channel out of the response, so it shows
# up glued onto — or in front of — the real answer. If Harmony-style
# channel control tokens are present we cut everything up to the last
# "final" channel marker; otherwise we leave the text alone, since we
# never want to guess-truncate a normal answer.
_HARMONY_FINAL_MARKERS = (
    "<|start|>assistant<|channel|>final<|message|>",
    "<|channel|>final<|message|>",
    "assistantfinal",
)
_HARMONY_TOKEN_RE = re.compile(r"<\|[a-z_]+\|>")


def _strip_reasoning_leak(text: str) -> str:
    if not text:
        return text
    for marker in _HARMONY_FINAL_MARKERS:
        idx = text.rfind(marker)
        if idx != -1:
            text = text[idx + len(marker):]
    text = _HARMONY_TOKEN_RE.sub("", text)
    return text.strip()

# Reset-tier cooldowns. "Minutes" tier providers come back into
# rotation after a short cooldown within the same session instead
# of being permanently blacklisted.
_COOLDOWN_SECONDS = {
    "groq":       90,    # minutes-tier
    "mistral":    90,    # minutes-tier
    "gemini":     90,    # minutes-tier (Flash)
    "gemini_pro": 3600,  # daily-tier — small RPD cap, recovers slowly
    "openrouter": 1800,  # daily-tier overflow
    "hf_flux_schnell": 120,  # free-tier retry windows, shown in the HUD
    "hf_sd35_turbo": 120,
    "hf_wan_video": 180,
    "hf_ltx_video": 180,
    "pollinations_video": 180,
    "pollinations": 60,
    "kling": 1800,
}

_cooldown_until = {}
_lock = threading.RLock()
_failure_log = []   # rolling log of (timestamp, task_type, provider, reason)
_FAILURE_LOG_MAX = 200

# ── Usage tracking (real token counts vs. known free-tier limits) ──
# BUG (fixed): this used to add a flat "+1" per successful call regardless
# of how many tokens that call actually used, so the bars stayed at ~0%
# almost forever (e.g. 1 request against a 1000-request cap = 0.1% -> "0%"
# after rounding) even when the account's real free-tier TOKEN quota was
# being burned through quickly. Every provider below already returns a
# token count in its response (`usage.total_tokens` for the OpenAI-style
# APIs, `usageMetadata.totalTokenCount` for Gemini) — we now read that and
# accumulate real tokens instead of a per-request tally.
# Two windows are tracked per model, same as the reference UI:
#   SESSION — resets when this EDITH process restarts (0% on fresh boot)
#   WEEKLY  — rolling 7-day window with a "resets in Xd Yh" countdown
_session_count = {}   # label -> int tokens used, since process start
_weekly_count  = {}   # label -> int tokens used, current weekly window
_weekly_start  = {}   # label -> epoch seconds when weekly window began

WEEKLY_PERIOD_SECONDS = 7 * 86400

# (session_limit, weekly_limit) per model label, in TOKENS — approximate
# free-tier caps (session = generous single-run budget, weekly = published
# TPD-style cap x 7).
_USAGE_LIMITS = {
    "groq":          (200_000,   200_000 * 7),   # GPT OSS 120B
    "groq_llama33":  (200_000,   200_000 * 7),
    "groq_scout":    (200_000,   200_000 * 7),
    "groq_qwen":     (200_000,   200_000 * 7),
    "groq_safety":   (200_000,   200_000 * 7),
    "mistral":       (50_000,    100_000 * 7),
    "gemini":        (250_000,   1_000_000 * 7),
    "gemini_pro":    (25_000,    50_000 * 7),      # Pro free tier — tiny daily cap
    "openrouter":    (50_000,    100_000 * 7),
    # Image/video providers are recorded per-call (see generate_image /
    # generate_video below), not per-token, so their limits stay as
    # request counts rather than token counts.
    "hf_flux_schnell": (150,    300 * 7),
    "hf_sd35_turbo":  (100,    200 * 7),
    "hf_wan_video":   (20,      40 * 7),
    "hf_ltx_video":   (20,      40 * 7),
    "pollinations_video": (20,   40 * 7),
    "pollinations":  (None,      None),            # effectively unlimited, no key
    "kling":         (50,        100 * 7),
}


def _record_usage(label, tokens=1):
    """Accumulate real token usage for `label`. `tokens` should come from
    the provider's own response (see _extract_*_tokens helpers below).
    Falls back to 1 only if a caller genuinely has no token count."""
    now = time.time()
    tokens = max(1, int(tokens or 1))
    with _lock:
        _session_count[label] = _session_count.get(label, 0) + tokens

        start = _weekly_start.get(label)
        if start is None or now - start > WEEKLY_PERIOD_SECONDS:
            _weekly_start[label] = now
            _weekly_count[label] = 0
        _weekly_count[label] = _weekly_count.get(label, 0) + tokens


_last_used = {"label": None, "task_type": None, "time": None}


def _mark_live(label, task_type):
    with _lock:
        _last_used["label"] = label
        _last_used["task_type"] = task_type
        _last_used["time"] = time.time()


def record_external_usage(label, tokens=1, task_type="agent"):
    """Record successful provider work performed outside ``chat_completion``."""
    _record_usage(label, tokens)
    _mark_live(label, task_type)


def get_live_model():
    """Returns the most recently successful (label, task_type, seconds_ago) or None."""
    with _lock:
        if _last_used["label"] is None:
            return None
        return {
            "label": _last_used["label"],
            "task_type": _last_used["task_type"],
            "seconds_ago": round(time.time() - _last_used["time"]),
        }


def _format_resets_in(seconds_left):
    seconds_left = max(0, int(seconds_left))
    days = seconds_left // 86400
    hours = (seconds_left % 86400) // 3600
    return f"{days}d {hours}h"


def _format_cooldown(seconds_left):
    seconds_left = max(0, int(seconds_left))
    minutes, seconds = divmod(seconds_left, 60)
    return f"{minutes}m {seconds:02d}s"


def get_model_usage():
    """
    Returns per-model usage stats matching the Session%/Weekly% UI:
    {label: {session_percent, weekly_percent, weekly_resets_in, on_cooldown, is_live}}
    """
    now = time.time()
    live = get_live_model()
    out = {}
    with _lock:
        for label, (session_limit, weekly_limit) in _USAGE_LIMITS.items():
            session_used = _session_count.get(label, 0)
            start = _weekly_start.get(label)
            weekly_used = _weekly_count.get(label, 0)
            if start is not None and now - start > WEEKLY_PERIOD_SECONDS:
                weekly_used = 0
                start = now

            if session_limit is None:
                session_pct = 0
            else:
                session_pct = min(100, round((session_used / session_limit) * 100, 2)) if session_limit else 0

            if weekly_limit is None:
                weekly_pct = 0
                resets_in = "n/a"
            else:
                weekly_pct = min(100, round((weekly_used / weekly_limit) * 100, 2)) if weekly_limit else 0
                if start is None:
                    resets_in = _format_resets_in(WEEKLY_PERIOD_SECONDS)
                else:
                    resets_in = _format_resets_in(WEEKLY_PERIOD_SECONDS - (now - start))

            out[label] = {
                "session_used": session_used,
                "session_limit": session_limit,
                "session_percent": session_pct,
                "weekly_used": weekly_used,
                "weekly_limit": weekly_limit,
                "weekly_percent": weekly_pct,
                "weekly_resets_in": resets_in,
                "on_cooldown": _on_cooldown_label(label),
                "cooldown_resets_in": _format_cooldown(
                    _cooldown_until.get(label, now) - now
                ) if _on_cooldown_label(label) else None,
                "is_live": bool(live and live["label"] == label),
            }
    return out


class ProviderError(Exception):
    """Raised when a provider fails for any reason (rate limit, HTTP error, timeout)."""
    def __init__(self, provider, reason):
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider}: {reason}")


def _on_cooldown(name):
    with _lock:
        until = _cooldown_until.get(name)
    return until is not None and time.time() < until


def _set_cooldown(name):
    with _lock:
        _cooldown_until[name] = time.time() + _COOLDOWN_SECONDS.get(name, 120)


def _clear_cooldown(name):
    with _lock:
        _cooldown_until.pop(name, None)


def _log_failure(task_type, provider, reason):
    """Record why a model failed, so failures can be tracked over time."""
    entry = (time.time(), task_type, provider, reason)
    with _lock:
        _failure_log.append(entry)
        if len(_failure_log) > _FAILURE_LOG_MAX:
            _failure_log.pop(0)
    log.warning(f"[{task_type}] ❌ {provider} failed: {reason}")


def get_failure_log(limit=50):
    with _lock:
        return list(_failure_log[-limit:])


# ── Task classification ─────────────────────────────────────────

_TASK_PATTERNS = [
    ("video",   re.compile(r"\b(generate|create|make|render)\b.*\bvideo\b|\btext.to.video\b", re.I)),
    ("image",   re.compile(r"\b(generate|create|draw|render|paint)\b.*\b(image|picture|photo|art|logo|illustration)\b", re.I)),
    ("tts",     re.compile(r"\btext.to.speech\b|\bspeak\b|\bread.*aloud\b|\bsay this\b|\bvoice.?over\b", re.I)),
    ("stt",     re.compile(r"\btranscrib|\bspeech.to.text\b|\baudio.*transcript\b", re.I)),
    ("vision",  re.compile(r"\b(analy[sz]e|describe|what'?s in|look at)\b.*\b(image|photo|picture|screenshot)\b", re.I)),
    ("safety",  re.compile(r"\b(moderate|moderation|is this (safe|offensive|harmful))\b|\bcontent\s+polic", re.I)),
    ("project", re.compile(r"\b(create|build|generate|scaffold|new|make)\b.*\b(project|app|application|repo|repository)\b", re.I)),
    ("search",  re.compile(r"\b(latest|today|current|recent|news|update[sd]?)\b", re.I)),
    ("code",    re.compile(r"\b(code|function|script|bug|debug|error|stack\s*trace|refactor|implement|class\s|def\s)\b", re.I)),
]


def classify_task(text: str) -> str:
    """
    Classify a request into one of:
    code, project, search, agent, safety, vision, stt, tts, image, video.
    Falls back to "agent" (general tool-use / multi-step) if nothing matches.
    """
    if not text:
        return "agent"
    for task_type, pattern in _TASK_PATTERNS:
        if pattern.search(text):
            return task_type
    return "agent"


# ── Provider: Groq (generic chat — model passed in) ──────────────

def _groq_chat(messages, system, max_tokens, model):
    if not GROQ_API_KEY:
        raise ProviderError("groq", "GROQ_API_KEY not set")
    session = _SHARED_HTTP_SESSION
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
    }
    # gpt-oss models burn hidden reasoning tokens against max_tokens before
    # producing visible content — left at default ("high") this regularly
    # exhausts the budget and returns empty content. Capping it low keeps
    # tokens available for the actual answer.
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "low"
        # Without this, Groq can leak the model's internal reasoning
        # ("The user asks... according to policy...") straight into the
        # visible `content` field, duplicated alongside the real answer.
        # "hidden" tells Groq to drop reasoning tokens entirely instead
        # of merging them into content.
        payload["reasoning_format"] = "hidden"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    # Groq's gpt-oss models have an acknowledged intermittent bug where a
    # call returns finish_reason="stop" with a completely empty `content`
    # even though nothing was actually wrong with the request (see comment
    # above). Previously a single empty response would immediately raise
    # ProviderError, which put the WHOLE groq model on a 90s cooldown and
    # fell back to a weaker provider for one transient glitch. Since it's
    # documented as intermittent, retry the exact same request in place
    # (bumping max_tokens a bit as extra headroom for reasoning) before
    # giving up — this fixes the false "empty/null response" cooldowns.
    last_finish_reason = None
    for attempt in range(2):
        attempt_payload = dict(payload)
        if attempt > 0:
            attempt_payload["max_tokens"] = int(max_tokens * 1.5)
            log.warning(f"[groq] empty response on attempt {attempt}, retrying with "
                        f"max_tokens={attempt_payload['max_tokens']}")
        resp = session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=attempt_payload, headers=headers, timeout=60,
        )
        if resp.status_code == 429:
            raise ProviderError("groq", f"rate limited: {resp.text[:100]}")
        if resp.status_code != 200:
            raise ProviderError("groq", f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        raw = data["choices"][0]["message"].get("content")
        text = (raw or "").strip()
        last_finish_reason = data["choices"][0].get("finish_reason")
        if text:
            text = _strip_reasoning_leak(text)
            tokens = data.get("usage", {}).get("total_tokens", 0)
            return text, tokens

    raise ProviderError("groq", f"empty/null response after retry (finish_reason={last_finish_reason})")


# ── Provider: Mistral ────────────────────────────────────────────

def _mistral_chat(messages, system, max_tokens):
    if not MISTRAL_API_KEY:
        raise ProviderError("mistral", "MISTRAL_API_KEY not set")
    session = _SHARED_HTTP_SESSION
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    resp = session.post(
        "https://api.mistral.ai/v1/chat/completions",
        json=payload, headers=headers, timeout=60,
    )
    if resp.status_code == 429:
        raise ProviderError("mistral", f"rate limited: {resp.text[:100]}")
    if resp.status_code != 200:
        raise ProviderError("mistral", f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    raw = data["choices"][0]["message"].get("content")
    text = (raw or "").strip()
    if not text:
        raise ProviderError("mistral", f"empty/null response (finish_reason={data['choices'][0].get('finish_reason')})")
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return text, tokens


# ── Provider: Gemini (Flash / Pro share the same key, different model) ──

def _gemini_chat(messages, system, max_tokens, model, search_grounding=False):
    if not GOOGLE_API_KEY:
        raise ProviderError("gemini", "GOOGLE_API_KEY not set")
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": max_tokens},
    }
    if search_grounding:
        payload["tools"] = [{"google_search": {}}]
    session = _SHARED_HTTP_SESSION
    url = f"{GEMINI_API_URL}/{model}:generateContent?key={GOOGLE_API_KEY}"
    resp = session.post(url, json=payload, timeout=120)

    label = "gemini_pro" if model == GEMINI_PRO_MODEL else "gemini"
    if resp.status_code == 429:
        raise ProviderError(label, f"rate limited: {resp.text[:100]}")
    if resp.status_code == 503:
        raise ProviderError(label, f"overloaded: {resp.text[:100]}")
    if resp.status_code != 200:
        raise ProviderError(label, f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text:
            raise ProviderError(label, "empty response")
        tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
        return text, tokens
    except (KeyError, IndexError):
        finish = data.get("candidates", [{}])[0].get("finishReason", "")
        raise ProviderError(label, f"unexpected structure / finish={finish}")


# ── Provider: OpenRouter (free router) ────────────────────────────

def _openrouter_chat(messages, system, max_tokens):
    if not OPENROUTER_API_KEY:
        raise ProviderError("openrouter", "OPENROUTER_API_KEY not set")
    session = _SHARED_HTTP_SESSION
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    resp = session.post(
        "https://openrouter.ai/api/v1/chat/completions",
        json=payload, headers=headers, timeout=90,
    )
    if resp.status_code == 429:
        raise ProviderError("openrouter", f"rate limited: {resp.text[:100]}")
    if resp.status_code != 200:
        raise ProviderError("openrouter", f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    raw = data["choices"][0]["message"].get("content")
    text = (raw or "").strip()
    if not text:
        raise ProviderError("openrouter", f"empty/null response (finish_reason={data['choices'][0].get('finish_reason')})")
    tokens = data.get("usage", {}).get("total_tokens", 0)
    return text, tokens


# ── Provider: Hugging Face (image generation) ─────────────────────

def _hf_image(prompt, model="black-forest-labs/FLUX.1-schnell"):
    if not HF_API_KEY:
        raise ProviderError("huggingface", "HF_API_KEY not set")
    session = _SHARED_HTTP_SESSION
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    resp = session.post(
        f"https://api-inference.huggingface.co/models/{model}",
        headers=headers, json={"inputs": prompt}, timeout=120,
    )
    if resp.status_code == 429:
        raise ProviderError("huggingface", f"rate limited: {resp.text[:100]}")
    if resp.status_code != 200:
        raise ProviderError("huggingface", f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.content  # raw image bytes


def _pollinations_image_url(prompt):
    # No key required — direct GET returns image bytes.
    import urllib.parse
    return f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"


def _pollinations_video(prompt):
    if not POLLINATIONS_API_KEY:
        raise ProviderError("pollinations_video", "POLLINATIONS_API_KEY not set")
    import urllib.parse
    url = ("https://gen.pollinations.ai/video/"
           f"{urllib.parse.quote(prompt)}?model={urllib.parse.quote(POLLINATIONS_VIDEO_MODEL)}")
    response = _SHARED_HTTP_SESSION.get(
        url, headers={"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}, timeout=300
    )
    if response.status_code in (429, 503):
        raise ProviderError("pollinations_video", f"temporarily busy (HTTP {response.status_code})")
    if response.status_code != 200:
        raise ProviderError("pollinations_video", f"HTTP {response.status_code}: {response.text[:160]}")
    if not response.content:
        raise ProviderError("pollinations_video", "empty video response")
    return response.content


# ── Provider: Kling (video generation) ─────────────────────────────

def _kling_video(prompt):
    if not KLING_API_KEY:
        raise ProviderError("kling", "KLING_API_KEY not set")
    session = _SHARED_HTTP_SESSION
    headers = {"Authorization": f"Bearer {KLING_API_KEY}"}
    resp = session.post(
        f"{KLING_API_URL}/v1/videos/text2video",
        headers=headers, json={"prompt": prompt}, timeout=120,
    )
    if resp.status_code == 429:
        raise ProviderError("kling", f"rate limited: {resp.text[:100]}")
    if resp.status_code != 200:
        raise ProviderError("kling", f"HTTP {resp.status_code}: {resp.text[:200]}")
    return resp.json()


# ── Per-task-type priority chains ──────────────────────────────────
# Each entry: (provider_label, callable(messages, system, max_tokens))
# Order matters — index 0 is priority 1.

_CHAINS = {
    "code": [
        ("groq",       lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_CODE)),
        ("groq_llama33", lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_LLAMA33)),
        ("mistral",    lambda m, s, t: _mistral_chat(m, s, t)),
        ("gemini",     lambda m, s, t: _gemini_chat(m, s, t, GEMINI_MODEL)),
        ("gemini_pro", lambda m, s, t: _gemini_chat(m, s, t, GEMINI_PRO_MODEL)),
    ],
    "project": [
        ("groq",       lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_CODE)),
        ("gemini",     lambda m, s, t: _gemini_chat(m, s, t, GEMINI_MODEL)),
        ("gemini_pro", lambda m, s, t: _gemini_chat(m, s, t, GEMINI_PRO_MODEL)),
    ],
    "search": [
        ("gemini",     lambda m, s, t: _gemini_chat(m, s, t, GEMINI_MODEL, search_grounding=True)),
        ("groq",       lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_CODE)),
        ("openrouter", lambda m, s, t: _openrouter_chat(m, s, t)),
    ],
    "agent": [
        ("gemini",       lambda m, s, t: _gemini_chat(m, s, t, GEMINI_MODEL)),
        ("gemini_pro",   lambda m, s, t: _gemini_chat(m, s, t, GEMINI_PRO_MODEL)),
        ("groq",         lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_CODE)),
        ("groq_scout",   lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_VISION)),
        ("openrouter",   lambda m, s, t: _openrouter_chat(m, s, t)),
    ],
    "safety": [
        ("groq_safety", lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_SAFETY)),
    ],
    "vision": [
        ("groq_scout", lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_VISION)),
        ("groq_qwen",  lambda m, s, t: _groq_chat(m, s, t, GROQ_MODEL_QWEN)),
    ],
}

# Per-model cooldown duration lookup (falls back to provider's base
# tier if a specific label isn't listed). Groq's different models
# have independent rate-limit buckets, so each gets its own cooldown
# instead of being collapsed under one shared "groq" cooldown.
def _cooldown_seconds_for(label):
    if label in _COOLDOWN_SECONDS:
        return _COOLDOWN_SECONDS[label]
    return _COOLDOWN_SECONDS.get(label.split("_")[0], 120)


def _on_cooldown_label(label):
    return _on_cooldown(label)


def _set_cooldown_label(label):
    with _lock:
        _cooldown_until[label] = time.time() + _cooldown_seconds_for(label)


def _clear_cooldown_label(label):
    _clear_cooldown(label)


# ── Unified dispatcher for text-based task types ───────────────────

def route_task(task_type, messages, system, max_tokens=None):
    """
    Try each provider in the given task type's priority chain in order.
    On rate limit / error / timeout: log it, cooldown that provider,
    and automatically retry the SAME request on the next one — never
    asks the user, never stops early. Raises RuntimeError only once
    every provider for this task type has failed.
    Returns (response_text, provider_name_used).
    """
    chain = _CHAINS.get(task_type)
    if not chain:
        raise RuntimeError(f"No provider chain configured for task type '{task_type}'")

    if max_tokens is None:
        max_tokens = CODE_MAX_TOKENS if task_type in ("code", "project") else CHAT_MAX_TOKENS

    last_err = None
    for label, fn in chain:
        if _on_cooldown_label(label):
            log.info(f"[{task_type}] skipping {label} (on cooldown)")
            continue
        try:
            result = fn(messages, system, max_tokens)
            # Provider functions return (text, tokens_used); tolerate a bare
            # string too in case a custom/legacy provider fn only returns text.
            if isinstance(result, tuple):
                text, tokens_used = result
            else:
                text, tokens_used = result, 0
            log.info(f"[{task_type}] ✅ {label} ({len(text)} chars, {tokens_used} tokens)")
            _clear_cooldown_label(label)
            _record_usage(label, tokens_used)
            _mark_live(label, task_type)
            return text, label
        except ProviderError as e:
            _log_failure(task_type, label, e.reason)
            _set_cooldown_label(label)
            last_err = e
        except requests.exceptions.Timeout:
            _log_failure(task_type, label, "timeout")
            _set_cooldown_label(label)
            last_err = ProviderError(label, "timeout")
        except Exception as e:
            _log_failure(task_type, label, str(e))
            _set_cooldown_label(label)
            last_err = ProviderError(label, str(e))

    raise RuntimeError(
        f"All available models for {task_type} are currently rate-limited "
        f"or unavailable. Please try again shortly. (Last error: {last_err})"
    )


def chat_completion(messages, system, max_tokens=CHAT_MAX_TOKENS, task_type="agent"):
    """Backward-compatible entry point — defaults to the 'agent' chain."""
    return route_task(task_type, messages, system, max_tokens)


# ── Image / Video dispatch (separate request shape — no chat messages) ──

def generate_image(prompt):
    """
    IMAGE priority: Hugging Face FLUX/SDXL -> Gemini image-out -> Pollinations.
    Returns (image_bytes_or_url, provider_name_used).
    """
    image_labels = ("hf_flux_schnell", "hf_sd35_turbo")
    for label, model in zip(image_labels, HF_IMAGE_MODELS):
        if not HF_API_KEY or _on_cooldown_label(label):
            continue
        try:
            data = _hf_image(prompt, model=model)
            _clear_cooldown_label(label)
            _record_usage(label)
            _mark_live(label, "image")
            return data, label
        except Exception as e:
            _log_failure("image", label, str(e))
            _set_cooldown_label(label)

    # Gemini image-out is account-eligibility gated; skipped automatically
    # if not configured for image output — falls through to Pollinations.

    if not _on_cooldown_label("pollinations"):
        try:
            url = _pollinations_image_url(prompt)
            _record_usage("pollinations")
            _mark_live("pollinations", "image")
            return url, "pollinations"
        except Exception as e:
            _log_failure("image", "pollinations", str(e))
            _set_cooldown_label("pollinations")

    raise RuntimeError(
        "All available models for image are currently rate-limited or "
        "unavailable. Please try again shortly."
    )


def _hf_video(prompt, model):
    """Hugging Face free-tier text-to-video. Quality is low (few seconds,
    low-res) compared to Kling, but it's free and gives a fallback instead
    of a dead end. HF free-tier models are frequently 'cold' — the first
    call returns 503 while it spins up, so we retry once after a short wait."""
    if not HF_API_KEY:
        raise ProviderError("huggingface_video", "HF_API_KEY not set")
    session = _SHARED_HTTP_SESSION
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    for attempt in range(2):
        resp = session.post(
            f"https://api-inference.huggingface.co/models/{model}",
            headers=headers, json={"inputs": prompt}, timeout=120,
        )
        if resp.status_code == 503 and attempt == 0:
            log.warning("[huggingface_video] model cold-starting (503), waiting 8s then retrying")
            time.sleep(8)
            continue
        if resp.status_code == 429:
            raise ProviderError("huggingface_video", f"rate limited: {resp.text[:100]}")
        if resp.status_code != 200:
            raise ProviderError("huggingface_video", f"HTTP {resp.status_code}: {resp.text[:200]}")
        return resp.content  # raw video bytes (mp4)
    raise ProviderError("huggingface_video", "model still loading after retry, try again shortly")


def generate_video(prompt):
    """
    VIDEO priority: Veo 3.1 -> Kling 3.0 -> Hugging Face (free fallback).
    Veo is not yet wired (requires Vertex AI video endpoint, not the
    Gemini text API) — falls straight to Kling.
    Hugging Face's free text-to-video models are low quality (short,
    low-res clips) but cost nothing, so they're a last-resort fallback
    when Kling is on cooldown/unconfigured rather than failing outright.
    """
    if POLLINATIONS_API_KEY and not _on_cooldown_label("pollinations_video"):
        try:
            data = _pollinations_video(prompt)
            _clear_cooldown_label("pollinations_video")
            _record_usage("pollinations_video")
            _mark_live("pollinations_video", "video")
            return data, "pollinations_video"
        except Exception as e:
            _log_failure("video", "pollinations_video", str(e))
            _set_cooldown_label("pollinations_video")
            # A valid key with no available pollen returns 402. Do not hide
            # that actionable billing status behind a generic provider error.
            if "HTTP 402" in str(e) or "PAYMENT_REQUIRED" in str(e):
                raise RuntimeError(
                    "Pollinations accepted the API key, but its account balance "
                    "is too low for this video. Add pollen/credits, then try again."
                ) from e
            if "HTTP 401" in str(e) or "UNAUTHORIZED" in str(e):
                raise RuntimeError(
                    "Pollinations rejected POLLINATIONS_API_KEY. Create a new "
                    "server key and update .env, then restart E.D.I.T.H."
                ) from e

    if not _on_cooldown_label("kling"):
        try:
            data = _kling_video(prompt)
            _clear_cooldown_label("kling")
            _record_usage("kling")
            _mark_live("kling", "video")
            return data, "kling"
        except Exception as e:
            _log_failure("video", "kling", str(e))
            _set_cooldown_label("kling")

    video_labels = ("hf_wan_video", "hf_ltx_video")
    for label, model in zip(video_labels, HF_VIDEO_MODELS):
        if not HF_API_KEY or _on_cooldown_label(label):
            continue
        try:
            data = _hf_video(prompt, model=model)
            _clear_cooldown_label(label)
            _record_usage(label)
            _mark_live(label, "video")
            return data, label
        except Exception as e:
            _log_failure("video", label, str(e))
            _set_cooldown_label(label)

    raise RuntimeError(
        "All available models for video are currently rate-limited or "
        "unavailable. Please try again shortly."
    )


def get_chain_status():
    """Returns provider -> on_cooldown bool, for HUD display (no keys/secrets exposed)."""
    all_labels = {label for chain in _CHAINS.values() for label, _ in chain}
    all_labels |= {"hf_flux_schnell", "hf_sd35_turbo", "hf_wan_video", "hf_ltx_video", "pollinations", "pollinations_video", "kling"}
    return {label: _on_cooldown_label(label) for label in sorted(all_labels)}
