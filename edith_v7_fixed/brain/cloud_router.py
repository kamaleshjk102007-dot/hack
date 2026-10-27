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
from utils.logger import get_logger, redact_secrets

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

import email.utils
import random

# Status codes
STATUS_CONFIGURED = "configured"
STATUS_AVAILABLE = "available"
STATUS_RATE_LIMITED = "rate_limited"
STATUS_UNAVAILABLE = "unavailable"
STATUS_AUTH_FAILURE = "auth_failure"
STATUS_NOT_CONFIGURED = "not_configured"

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
_provider_state = {}  # label -> status string (STATUS_*)
_lock = threading.RLock()
_failure_log = []   # rolling log of (timestamp, task_type, provider, reason)
_FAILURE_LOG_MAX = 200

MAX_RETRY_AFTER_SECONDS = 3600.0  # Cap rate-limit waits to 1 hour max

def _parse_retry_after(header_val: str, default: float = 90.0) -> float:
    """
    Parse HTTP Retry-After header (either integer seconds or HTTP-date).
    - Caps excessive delays to MAX_RETRY_AFTER_SECONDS (3600s) to keep cooldowns bounded.
    - Handles expired or non-positive dates by falling back to default backoff.
    - Handles invalid, empty, or negative values gracefully.
    """
    if not header_val:
        return min(MAX_RETRY_AFTER_SECONDS, max(1.0, float(default)))
    header_val = str(header_val).strip()
    try:
        # Check if integer/float seconds
        val = float(header_val)
        if val < 0:
            return min(MAX_RETRY_AFTER_SECONDS, max(1.0, float(default)))
        return min(MAX_RETRY_AFTER_SECONDS, max(1.0, val))
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(header_val)
        if dt:
            target_epoch = dt.timestamp()
            diff = target_epoch - time.time()
            if diff <= 0:
                # Expired HTTP-date — fall back to default cooldown rather than negative/immediate loop
                return min(MAX_RETRY_AFTER_SECONDS, max(1.0, float(default)))
            return min(MAX_RETRY_AFTER_SECONDS, max(1.0, diff))
    except Exception:
        pass
    return min(MAX_RETRY_AFTER_SECONDS, max(1.0, float(default)))

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


def _is_provider_configured(label: str) -> bool:
    """Check if the necessary API key for this provider is non-empty."""
    if label.startswith("groq"):
        return bool(GROQ_API_KEY)
    if label == "mistral":
        return bool(MISTRAL_API_KEY)
    if label.startswith("gemini"):
        return bool(GOOGLE_API_KEY)
    if label == "openrouter":
        return bool(OPENROUTER_API_KEY)
    if label.startswith("hf_"):
        return bool(HF_API_KEY)
    if label == "pollinations_video":
        return bool(POLLINATIONS_API_KEY)
    if label == "pollinations":
        return True  # No key required
    if label == "kling":
        return bool(KLING_API_KEY)
    return False


def get_provider_status(label: str) -> str:
    """
    Returns one of:
    - STATUS_NOT_CONFIGURED: Key is missing/empty
    - STATUS_AUTH_FAILURE: Observed 401/403
    - STATUS_RATE_LIMITED: Observed 429 and currently cooling down
    - STATUS_UNAVAILABLE: Observed 5xx/connection error/timeout and currently cooling down
    - STATUS_CONFIGURED: Configured, but never observed/verified live in this session
    - STATUS_AVAILABLE: Verified live or available without cooldown
    """
    if not _is_provider_configured(label):
        return STATUS_NOT_CONFIGURED
    with _lock:
        state = _provider_state.get(label)
        on_cool = _on_cooldown(label)
        if on_cool:
            if state == STATUS_AUTH_FAILURE:
                return STATUS_AUTH_FAILURE
            if state == STATUS_RATE_LIMITED:
                return STATUS_RATE_LIMITED
            return STATUS_UNAVAILABLE
        if state == STATUS_AUTH_FAILURE:
            return STATUS_AUTH_FAILURE
        # If not on cooldown and configured:
        # If recorded usage or live, it is verified available.
        if _session_count.get(label, 0) > 0 or (_last_used["label"] == label):
            return STATUS_AVAILABLE
        return STATUS_CONFIGURED


def get_model_usage():
    """
    Returns per-model usage stats matching the Session%/Weekly% UI:
    {label: {session_percent, weekly_percent, weekly_resets_in, on_cooldown, is_live, status}}
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

            status_str = get_provider_status(label)
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
                "status": status_str,
            }
    return out


class ProviderError(Exception):
    """Raised when a provider fails for any reason (rate limit, HTTP error, timeout, auth)."""
    def __init__(self, provider, reason, status=STATUS_UNAVAILABLE, retry_after=None):
        self.provider = provider
        self.reason = redact_secrets(str(reason))
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"{provider}: {self.reason}")


def _on_cooldown(name):
    with _lock:
        until = _cooldown_until.get(name)
    return until is not None and time.time() < until


def _cooldown_seconds_for(label):
    if label in _COOLDOWN_SECONDS:
        return _COOLDOWN_SECONDS[label]
    return _COOLDOWN_SECONDS.get(label.split("_")[0], 120)


def _set_cooldown(name, duration=None, status=STATUS_UNAVAILABLE):
    base_duration = duration if duration is not None else _cooldown_seconds_for(name)
    # Add proportional jitter (10%-20%) for transient errors to avoid thundering herds
    if status != STATUS_AUTH_FAILURE and base_duration > 5:
        jitter = random.uniform(0.05, 0.20) * base_duration
        final_duration = base_duration + jitter
    else:
        final_duration = base_duration

    with _lock:
        _cooldown_until[name] = time.time() + final_duration
        _provider_state[name] = status


def _clear_cooldown(name):
    with _lock:
        _cooldown_until.pop(name, None)
        _provider_state[name] = STATUS_AVAILABLE


def reset_provider_cooldown(label: str = None):
    """
    Allow controlled recovery when API credentials are fixed or rotated.
    If label is None, clears all cooldowns and sets configured providers back to available/configured.
    """
    with _lock:
        if label:
            _cooldown_until.pop(label, None)
            _provider_state[label] = STATUS_AVAILABLE if _is_provider_configured(label) else STATUS_NOT_CONFIGURED
        else:
            _cooldown_until.clear()
            for prov in list(_provider_state.keys()):
                _provider_state[prov] = STATUS_AVAILABLE if _is_provider_configured(prov) else STATUS_NOT_CONFIGURED


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


def _compute_timeout(connect_default: float, read_default: float, budget: float = None):
    """
    Calculate bounded connect/read timeout based on remaining time budget.
    Ensures neither connect nor read socket timeout exceeds the remaining overall budget.

    Boundary & Clamping rules:
    - If budget is None: returns (connect_default, read_default).
    - If budget <= 0: returns (0.0, 0.0) to prevent initiating/blocking requests.
    - If budget > 0:
        connect_t = min(connect_default, budget)
        read_t = min(read_default, budget)
      Neither timeout can exceed the remaining budget (e.g. For budget=0.2s, returns (0.2, 0.2)).
    - Note on deadlines: This implements best-effort cooperative deadline bounding
      at the socket I/O layer; it is not a preemptive hard real-time interrupt.
    """
    if budget is None:
        return (connect_default, read_default)
    if budget <= 0:
        return (0.0, 0.0)
    connect_t = min(float(connect_default), float(budget))
    read_t = min(float(read_default), float(budget))
    return (connect_t, read_t)


def _sanitize_messages(messages):
    """
    Sanitize messages list to standard OpenAI chat completion schema.
    Strips proprietary metadata fields (e.g. 'origin', 'verification_status', 'sources')
    that cause strict providers like Groq to reject requests with HTTP 400.
    """
    cleaned = []
    for msg in (messages or []):
        if not isinstance(msg, dict):
            continue
        if "role" not in msg and "content" not in msg:
            continue
        clean_msg = {
            "role": str(msg.get("role", "user")),
            "content": str(msg.get("content", "")),
        }
        if "name" in msg and msg["name"]:
            clean_msg["name"] = str(msg["name"])
        cleaned.append(clean_msg)
    return cleaned


# ── Provider: Groq (generic chat — model passed in) ──────────────

def _groq_chat(messages, system, max_tokens, model, timeout_budget=None):
    if not GROQ_API_KEY:
        raise ProviderError("groq", "GROQ_API_KEY not set", status=STATUS_NOT_CONFIGURED)
    messages = _sanitize_messages(messages)
    session = _SHARED_HTTP_SESSION
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
    }
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "low"
        payload["reasoning_format"] = "hidden"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    last_finish_reason = None
    for attempt in range(2):
        attempt_payload = dict(payload)
        if attempt > 0:
            attempt_payload["max_tokens"] = int(max_tokens * 1.5)
            log.warning(f"[groq] empty response on attempt {attempt}, retrying with "
                        f"max_tokens={attempt_payload['max_tokens']}")
        try:
            req_timeout = _compute_timeout(10, 60, timeout_budget)
            resp = session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=attempt_payload, headers=headers, timeout=req_timeout,
            )
        except requests.exceptions.Timeout:
            raise ProviderError("groq", "request timed out", status=STATUS_UNAVAILABLE)
        except requests.exceptions.RequestException as e:
            raise ProviderError("groq", f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

        if resp.status_code in (401, 403):
            clean_body = redact_secrets(resp.text[:100])
            raise ProviderError("groq", f"authentication failure ({resp.status_code}): {clean_body}",
                                status=STATUS_AUTH_FAILURE, retry_after=86400)
        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=_cooldown_seconds_for("groq"))
            clean_body = redact_secrets(resp.text[:100])
            raise ProviderError("groq", f"rate limited: {clean_body}",
                                status=STATUS_RATE_LIMITED, retry_after=retry_after)
        if resp.status_code >= 500:
            clean_body = redact_secrets(resp.text[:100])
            raise ProviderError("groq", f"server error (HTTP {resp.status_code}): {clean_body}",
                                status=STATUS_UNAVAILABLE)
        if resp.status_code != 200:
            clean_body = redact_secrets(resp.text[:100])
            raise ProviderError("groq", f"HTTP {resp.status_code}: {clean_body}", status=STATUS_UNAVAILABLE)

        try:
            data = resp.json()
            raw = data["choices"][0]["message"].get("content")
            text = (raw or "").strip()
            last_finish_reason = data["choices"][0].get("finish_reason")
            if text:
                text = _strip_reasoning_leak(text)
                tokens = data.get("usage", {}).get("total_tokens", 0)
                return text, tokens
        except Exception as e:
            if attempt == 1:
                raise ProviderError("groq", f"malformed response: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

    raise ProviderError("groq", f"empty/null response after retry (finish_reason={last_finish_reason})", status=STATUS_UNAVAILABLE)


# ── Provider: Mistral ────────────────────────────────────────────

def _mistral_chat(messages, system, max_tokens, timeout_budget=None):
    if not MISTRAL_API_KEY:
        raise ProviderError("mistral", "MISTRAL_API_KEY not set", status=STATUS_NOT_CONFIGURED)
    messages = _sanitize_messages(messages)
    session = _SHARED_HTTP_SESSION
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {MISTRAL_API_KEY}"}
    try:
        req_timeout = _compute_timeout(10, 60, timeout_budget)
        resp = session.post(
            "https://api.mistral.ai/v1/chat/completions",
            json=payload, headers=headers, timeout=req_timeout,
        )
    except requests.exceptions.Timeout:
        raise ProviderError("mistral", "request timed out", status=STATUS_UNAVAILABLE)
    except requests.exceptions.RequestException as e:
        raise ProviderError("mistral", f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

    if resp.status_code in (401, 403):
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("mistral", f"authentication failure ({resp.status_code}): {clean_body}",
                            status=STATUS_AUTH_FAILURE, retry_after=86400)
    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=_cooldown_seconds_for("mistral"))
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("mistral", f"rate limited: {clean_body}",
                            status=STATUS_RATE_LIMITED, retry_after=retry_after)
    if resp.status_code >= 500:
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("mistral", f"server error (HTTP {resp.status_code}): {clean_body}",
                            status=STATUS_UNAVAILABLE)
    if resp.status_code != 200:
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("mistral", f"HTTP {resp.status_code}: {clean_body}", status=STATUS_UNAVAILABLE)

    try:
        data = resp.json()
        raw = data["choices"][0]["message"].get("content")
        text = (raw or "").strip()
        if not text:
            raise ProviderError("mistral", f"empty/null response (finish_reason={data['choices'][0].get('finish_reason')})", status=STATUS_UNAVAILABLE)
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return text, tokens
    except KeyError:
        raise ProviderError("mistral", "malformed response structure", status=STATUS_UNAVAILABLE)
    except Exception as e:
        raise ProviderError("mistral", f"response decode error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)


# ── Provider: Gemini (Flash / Pro share the same key, different model) ──

def _gemini_chat(messages, system, max_tokens, model, search_grounding=False, timeout_budget=None):
    if not GOOGLE_API_KEY:
        raise ProviderError("gemini", "GOOGLE_API_KEY not set", status=STATUS_NOT_CONFIGURED)
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
    headers = {"x-goog-api-key": GOOGLE_API_KEY}
    url = f"{GEMINI_API_URL}/{model}:generateContent"

    label = "gemini_pro" if model == GEMINI_PRO_MODEL else "gemini"
    try:
        req_timeout = _compute_timeout(10, 120, timeout_budget)
        resp = session.post(url, headers=headers, json=payload, timeout=req_timeout)
    except requests.exceptions.Timeout:
        raise ProviderError(label, "request timed out", status=STATUS_UNAVAILABLE)
    except requests.exceptions.RequestException as e:
        raise ProviderError(label, f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

    if resp.status_code in (401, 403):
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError(label, f"authentication failure ({resp.status_code}): {clean_body}",
                            status=STATUS_AUTH_FAILURE, retry_after=86400)
    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=_cooldown_seconds_for(label))
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError(label, f"rate limited: {clean_body}",
                            status=STATUS_RATE_LIMITED, retry_after=retry_after)
    if resp.status_code in (500, 502, 503, 504):
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError(label, f"server unavailable (HTTP {resp.status_code}): {clean_body}",
                            status=STATUS_UNAVAILABLE)
    if resp.status_code != 200:
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError(label, f"HTTP {resp.status_code}: {clean_body}", status=STATUS_UNAVAILABLE)

    try:
        data = resp.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        non_thought = [p.get("text", "") for p in parts if not p.get("thought", False)]
        text = "\n".join(t for t in non_thought if t).strip()
        if not text:
            text = "\n".join(p.get("text", "") for p in parts if p.get("text")).strip()
        if not text:
            raise ProviderError(label, "empty response", status=STATUS_UNAVAILABLE)
        text = _strip_reasoning_leak(text)
        tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
        return text, tokens
    except KeyError:
        finish = data.get("candidates", [{}])[0].get("finishReason", "")
        raise ProviderError(label, f"unexpected structure / finish={finish}", status=STATUS_UNAVAILABLE)
    except Exception as e:
        raise ProviderError(label, f"response decode error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)


# ── Provider: OpenRouter (free router) ────────────────────────────

def _openrouter_chat(messages, system, max_tokens, timeout_budget=None):
    if not OPENROUTER_API_KEY:
        raise ProviderError("openrouter", "OPENROUTER_API_KEY not set", status=STATUS_NOT_CONFIGURED)
    messages = _sanitize_messages(messages)
    session = _SHARED_HTTP_SESSION
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "system", "content": system}] + messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    try:
        req_timeout = _compute_timeout(10, 90, timeout_budget)
        resp = session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload, headers=headers, timeout=req_timeout,
        )
    except requests.exceptions.Timeout:
        raise ProviderError("openrouter", "request timed out", status=STATUS_UNAVAILABLE)
    except requests.exceptions.RequestException as e:
        raise ProviderError("openrouter", f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

    if resp.status_code in (401, 403):
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("openrouter", f"authentication failure ({resp.status_code}): {clean_body}",
                            status=STATUS_AUTH_FAILURE, retry_after=86400)
    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=_cooldown_seconds_for("openrouter"))
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("openrouter", f"rate limited: {clean_body}",
                            status=STATUS_RATE_LIMITED, retry_after=retry_after)
    if resp.status_code >= 500:
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("openrouter", f"server error (HTTP {resp.status_code}): {clean_body}",
                            status=STATUS_UNAVAILABLE)
    if resp.status_code != 200:
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("openrouter", f"HTTP {resp.status_code}: {clean_body}", status=STATUS_UNAVAILABLE)

    try:
        data = resp.json()
        raw = data["choices"][0]["message"].get("content")
        text = (raw or "").strip()
        if not text:
            raise ProviderError("openrouter", f"empty/null response (finish_reason={data['choices'][0].get('finish_reason')})", status=STATUS_UNAVAILABLE)
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return text, tokens
    except KeyError:
        raise ProviderError("openrouter", "malformed response structure", status=STATUS_UNAVAILABLE)
    except Exception as e:
        raise ProviderError("openrouter", f"response decode error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)


# ── Provider: Hugging Face (image generation) ─────────────────────

def _hf_image(prompt, model="black-forest-labs/FLUX.1-schnell"):
    if not HF_API_KEY:
        raise ProviderError("huggingface", "HF_API_KEY not set", status=STATUS_NOT_CONFIGURED)
    session = _SHARED_HTTP_SESSION
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    try:
        resp = session.post(
            f"https://api-inference.huggingface.co/models/{model}",
            headers=headers, json={"inputs": prompt}, timeout=(10, 120),
        )
    except requests.exceptions.Timeout:
        raise ProviderError("huggingface", "request timed out", status=STATUS_UNAVAILABLE)
    except requests.exceptions.RequestException as e:
        raise ProviderError("huggingface", f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

    if resp.status_code in (401, 403):
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("huggingface", f"authentication failure ({resp.status_code}): {clean_body}",
                            status=STATUS_AUTH_FAILURE, retry_after=86400)
    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=_cooldown_seconds_for("hf_flux_schnell"))
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("huggingface", f"rate limited: {clean_body}",
                            status=STATUS_RATE_LIMITED, retry_after=retry_after)
    if resp.status_code >= 500:
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("huggingface", f"server error (HTTP {resp.status_code}): {clean_body}",
                            status=STATUS_UNAVAILABLE)
    if resp.status_code != 200:
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("huggingface", f"HTTP {resp.status_code}: {clean_body}", status=STATUS_UNAVAILABLE)

    if not resp.content:
        raise ProviderError("huggingface", "empty image response", status=STATUS_UNAVAILABLE)
    return resp.content  # raw image bytes


def _pollinations_image_url(prompt):
    # No key required — direct GET returns image bytes.
    import urllib.parse
    return f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}"


def _pollinations_video(prompt):
    if not POLLINATIONS_API_KEY:
        raise ProviderError("pollinations_video", "POLLINATIONS_API_KEY not set", status=STATUS_NOT_CONFIGURED)
    import urllib.parse
    url = ("https://gen.pollinations.ai/video/"
           f"{urllib.parse.quote(prompt)}?model={urllib.parse.quote(POLLINATIONS_VIDEO_MODEL)}")
    try:
        response = _SHARED_HTTP_SESSION.get(
            url, headers={"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}, timeout=(10, 300)
        )
    except requests.exceptions.Timeout:
        raise ProviderError("pollinations_video", "request timed out", status=STATUS_UNAVAILABLE)
    except requests.exceptions.RequestException as e:
        raise ProviderError("pollinations_video", f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

    if response.status_code in (401, 403):
        clean_body = redact_secrets(response.text[:100])
        raise ProviderError("pollinations_video", f"authentication failure ({response.status_code}): {clean_body}",
                            status=STATUS_AUTH_FAILURE, retry_after=86400)
    if response.status_code == 429:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"), default=_cooldown_seconds_for("pollinations_video"))
        raise ProviderError("pollinations_video", f"rate limited: {redact_secrets(response.text[:100])}",
                            status=STATUS_RATE_LIMITED, retry_after=retry_after)
    if response.status_code in (500, 502, 503, 504):
        raise ProviderError("pollinations_video", f"temporarily busy (HTTP {response.status_code})",
                            status=STATUS_UNAVAILABLE)
    if response.status_code != 200:
        raise ProviderError("pollinations_video", f"HTTP {response.status_code}: {redact_secrets(response.text[:160])}",
                            status=STATUS_UNAVAILABLE)
    if not response.content:
        raise ProviderError("pollinations_video", "empty video response", status=STATUS_UNAVAILABLE)
    return response.content


# ── Provider: Kling (video generation) ─────────────────────────────

def _kling_video(prompt):
    if not KLING_API_KEY:
        raise ProviderError("kling", "KLING_API_KEY not set", status=STATUS_NOT_CONFIGURED)
    session = _SHARED_HTTP_SESSION
    headers = {"Authorization": f"Bearer {KLING_API_KEY}"}
    try:
        resp = session.post(
            f"{KLING_API_URL}/v1/videos/text2video",
            headers=headers, json={"prompt": prompt}, timeout=(10, 120),
        )
    except requests.exceptions.Timeout:
        raise ProviderError("kling", "request timed out", status=STATUS_UNAVAILABLE)
    except requests.exceptions.RequestException as e:
        raise ProviderError("kling", f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

    if resp.status_code in (401, 403):
        clean_body = redact_secrets(resp.text[:100])
        raise ProviderError("kling", f"authentication failure ({resp.status_code}): {clean_body}",
                            status=STATUS_AUTH_FAILURE, retry_after=86400)
    if resp.status_code == 429:
        retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=_cooldown_seconds_for("kling"))
        raise ProviderError("kling", f"rate limited: {redact_secrets(resp.text[:100])}",
                            status=STATUS_RATE_LIMITED, retry_after=retry_after)
    if resp.status_code >= 500:
        raise ProviderError("kling", f"server error (HTTP {resp.status_code}): {redact_secrets(resp.text[:100])}",
                            status=STATUS_UNAVAILABLE)
    if resp.status_code != 200:
        raise ProviderError("kling", f"HTTP {resp.status_code}: {redact_secrets(resp.text[:200])}",
                            status=STATUS_UNAVAILABLE)
    try:
        return resp.json()
    except Exception as e:
        raise ProviderError("kling", f"response decode error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)


# ── Per-task-type priority chains ──────────────────────────────────
# Each entry: (provider_label, callable(messages, system, max_tokens))
# Order matters — index 0 is priority 1.

def _wrap_groq(model):
    return lambda m, s, t, b=None: _call_provider_safe(_groq_chat, m, s, t, model, timeout_budget=b)

def _wrap_mistral():
    return lambda m, s, t, b=None: _call_provider_safe(_mistral_chat, m, s, t, timeout_budget=b)

def _wrap_gemini(model, search=False):
    return lambda m, s, t, b=None: _call_provider_safe(_gemini_chat, m, s, t, model, search_grounding=search, timeout_budget=b)

def _wrap_openrouter():
    return lambda m, s, t, b=None: _call_provider_safe(_openrouter_chat, m, s, t, timeout_budget=b)

def _call_provider_safe(fn, *args, **kwargs):
    """
    Safely invoke a provider callable with optional kwargs (e.g. timeout_budget).
    Inspects signature to pass supported arguments without swallowing internal TypeErrors.
    Accurately unpacks mock objects and callable wrappers.
    """
    import inspect
    import traceback

    # Resolve target function if wrapped in mock or custom wrapper
    target_fn = fn
    if hasattr(fn, "side_effect") and fn.side_effect is not None:
        target_fn = fn.side_effect
    elif hasattr(fn, "_mock_wraps") and fn._mock_wraps is not None:
        target_fn = fn._mock_wraps
    elif hasattr(fn, "__wrapped__") and fn.__wrapped__ is not None:
        target_fn = fn.__wrapped__

    sig = None
    try:
        sig = inspect.signature(target_fn)
    except (ValueError, TypeError):
        sig = None

    if sig is not None:
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if not has_var_keyword:
            kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return fn(*args, **kwargs)

    # Fallback if signature inspection is unavailable or unhelpful
    try:
        return fn(*args, **kwargs)
    except TypeError as te:
        # Check if the TypeError occurred at the invocation boundary (not inside the target function)
        err_msg = str(te)
        tb_frames = traceback.extract_tb(te.__traceback__)
        is_invocation_error = (
            len(tb_frames) == 1
            or (len(tb_frames) > 1 and all("mock.py" in fr.filename or fr.name == "_call_provider_safe" for fr in tb_frames))
        )
        if is_invocation_error and any(phrase in err_msg for phrase in ("unexpected keyword", "keyword argument", "takes")):
            filtered = {k: v for k, v in kwargs.items() if k not in ("timeout_budget", "search_grounding")}
            return fn(*args, **filtered)
        raise

_CHAINS = {
    "code": [
        ("groq",       _wrap_groq(GROQ_MODEL_CODE)),
        ("groq_llama33", _wrap_groq(GROQ_MODEL_LLAMA33)),
        ("mistral",    _wrap_mistral()),
        ("gemini",     _wrap_gemini(GEMINI_MODEL)),
        ("gemini_pro", _wrap_gemini(GEMINI_PRO_MODEL)),
    ],
    "project": [
        ("groq",       _wrap_groq(GROQ_MODEL_CODE)),
        ("gemini",     _wrap_gemini(GEMINI_MODEL)),
        ("gemini_pro", _wrap_gemini(GEMINI_PRO_MODEL)),
    ],
    "search": [
        ("gemini",     _wrap_gemini(GEMINI_MODEL, search=True)),
        ("groq",       _wrap_groq(GROQ_MODEL_CODE)),
        ("openrouter", _wrap_openrouter()),
    ],
    "agent": [
        ("gemini",       _wrap_gemini(GEMINI_MODEL)),
        ("gemini_pro",   _wrap_gemini(GEMINI_PRO_MODEL)),
        ("groq",         _wrap_groq(GROQ_MODEL_CODE)),
        ("groq_scout",   _wrap_groq(GROQ_MODEL_VISION)),
        ("openrouter",   _wrap_openrouter()),
    ],
    "safety": [
        ("groq_safety", _wrap_groq(GROQ_MODEL_SAFETY)),
        ("gemini",      _wrap_gemini(GEMINI_MODEL)),
        ("openrouter",  _wrap_openrouter()),
    ],
    "vision": [
        ("groq_scout", _wrap_groq(GROQ_MODEL_VISION)),
        ("groq_qwen",  _wrap_groq(GROQ_MODEL_QWEN)),
    ],
}

# Per-model cooldown duration lookup (falls back to provider's base
# tier if a specific label isn't listed). Groq's different models
# have independent rate-limit buckets, so each gets its own cooldown
# instead of being collapsed under one shared "groq" cooldown.


def _on_cooldown_label(label):
    return _on_cooldown(label)


def _set_cooldown_label(label, duration=None, status=STATUS_UNAVAILABLE):
    _set_cooldown(label, duration=duration, status=status)


def _clear_cooldown_label(label):
    _clear_cooldown(label)


# ── Unified dispatcher for text-based task types ───────────────────

def route_task(task_type, messages, system, max_tokens=None, timeout_budget=None):
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

    messages = _sanitize_messages(messages)

    if max_tokens is None:
        max_tokens = CODE_MAX_TOKENS if task_type in ("code", "project") else CHAT_MAX_TOKENS

    last_err = None
    start_time = time.monotonic()
    # Enforce a bounded overall execution deadline across cascading retries
    TOTAL_ROUTING_DEADLINE_SECONDS = float(timeout_budget) if timeout_budget is not None else 180.0

    for label, fn in chain:
        elapsed = time.monotonic() - start_time
        remaining_budget = max(0.0, TOTAL_ROUTING_DEADLINE_SECONDS - elapsed)
        # Stop before initiating network I/O if budget is exhausted or too small for a meaningful request
        if remaining_budget <= 0.1:
            log.warning(f"[{task_type}] Total routing deadline ({TOTAL_ROUTING_DEADLINE_SECONDS}s) exhausted")
            break
        if _on_cooldown_label(label):
            log.info(f"[{task_type}] skipping {label} (on cooldown)")
            continue
        try:
            try:
                result = fn(messages, system, max_tokens, remaining_budget)
            except TypeError:
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
            _set_cooldown_label(label, duration=e.retry_after, status=e.status)
            last_err = e
        except requests.exceptions.Timeout:
            _log_failure(task_type, label, "timeout")
            _set_cooldown_label(label, status=STATUS_UNAVAILABLE)
            last_err = ProviderError(label, "timeout", status=STATUS_UNAVAILABLE)
        except requests.exceptions.ConnectionError as e:
            sanitized_msg = redact_secrets(str(e))
            _log_failure(task_type, label, f"connection error: {sanitized_msg[:120]}")
            _set_cooldown_label(label, status=STATUS_UNAVAILABLE)
            last_err = ProviderError(label, f"connection error: {sanitized_msg[:120]}", status=STATUS_UNAVAILABLE)
        except Exception as e:
            sanitized_msg = redact_secrets(str(e))
            _log_failure(task_type, label, sanitized_msg[:120])
            _set_cooldown_label(label, status=STATUS_UNAVAILABLE)
            last_err = ProviderError(label, sanitized_msg[:120], status=STATUS_UNAVAILABLE)

    raise RuntimeError(
        f"All available models for {task_type} are currently rate-limited "
        f"or unavailable. Please try again shortly. (Last error: {last_err})"
    )


def chat_completion(messages, system, max_tokens=CHAT_MAX_TOKENS, task_type="agent", timeout_budget=None):
    """Backward-compatible entry point — defaults to the 'agent' chain."""
    return route_task(task_type, messages, system, max_tokens, timeout_budget=timeout_budget)


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
        except ProviderError as e:
            _log_failure("image", label, e.reason)
            _set_cooldown_label(label, duration=e.retry_after, status=e.status)
        except Exception as e:
            msg = redact_secrets(str(e))
            _log_failure("image", label, msg)
            _set_cooldown_label(label, status=STATUS_UNAVAILABLE)

    # Gemini image-out is account-eligibility gated; skipped automatically
    # if not configured for image output — falls through to Pollinations.

    if not _on_cooldown_label("pollinations"):
        try:
            url = _pollinations_image_url(prompt)
            _record_usage("pollinations")
            _mark_live("pollinations", "image")
            return url, "pollinations"
        except Exception as e:
            msg = redact_secrets(str(e))
            _log_failure("image", "pollinations", msg)
            _set_cooldown_label("pollinations", status=STATUS_UNAVAILABLE)

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
        raise ProviderError("huggingface_video", "HF_API_KEY not set", status=STATUS_NOT_CONFIGURED)
    session = _SHARED_HTTP_SESSION
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    for attempt in range(2):
        try:
            resp = session.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers=headers, json={"inputs": prompt}, timeout=(10, 120),
            )
        except requests.exceptions.Timeout:
            raise ProviderError("huggingface_video", "request timed out", status=STATUS_UNAVAILABLE)
        except requests.exceptions.RequestException as e:
            raise ProviderError("huggingface_video", f"network error: {redact_secrets(str(e))[:100]}", status=STATUS_UNAVAILABLE)

        if resp.status_code in (401, 403):
            clean_body = redact_secrets(resp.text[:100])
            raise ProviderError("huggingface_video", f"authentication failure ({resp.status_code}): {clean_body}",
                                status=STATUS_AUTH_FAILURE, retry_after=86400)
        if resp.status_code == 503 and attempt == 0:
            log.warning("[huggingface_video] model cold-starting (503), waiting 8s then retrying")
            time.sleep(8)
            continue
        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"), default=_cooldown_seconds_for("hf_wan_video"))
            raise ProviderError("huggingface_video", f"rate limited: {redact_secrets(resp.text[:100])}",
                                status=STATUS_RATE_LIMITED, retry_after=retry_after)
        if resp.status_code != 200:
            raise ProviderError("huggingface_video", f"HTTP {resp.status_code}: {redact_secrets(resp.text[:200])}",
                                status=STATUS_UNAVAILABLE)
        if not resp.content:
            raise ProviderError("huggingface_video", "empty video response", status=STATUS_UNAVAILABLE)
        return resp.content  # raw video bytes (mp4)
    raise ProviderError("huggingface_video", "model still loading after retry, try again shortly", status=STATUS_UNAVAILABLE)


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
        except ProviderError as e:
            _log_failure("video", "pollinations_video", e.reason)
            _set_cooldown_label("pollinations_video", duration=e.retry_after, status=e.status)
            if "HTTP 402" in e.reason or "PAYMENT_REQUIRED" in e.reason:
                raise RuntimeError(
                    "Pollinations accepted the API key, but its account balance "
                    "is too low for this video. Add pollen/credits, then try again."
                ) from e
            if e.status == STATUS_AUTH_FAILURE or "HTTP 401" in e.reason or "UNAUTHORIZED" in e.reason:
                raise RuntimeError(
                    "Pollinations rejected POLLINATIONS_API_KEY. Create a new "
                    "server key and update .env, then restart E.D.I.T.H."
                ) from e
        except Exception as e:
            msg = redact_secrets(str(e))
            _log_failure("video", "pollinations_video", msg)
            _set_cooldown_label("pollinations_video", status=STATUS_UNAVAILABLE)

    if not _on_cooldown_label("kling"):
        try:
            data = _kling_video(prompt)
            _clear_cooldown_label("kling")
            _record_usage("kling")
            _mark_live("kling", "video")
            return data, "kling"
        except ProviderError as e:
            _log_failure("video", "kling", e.reason)
            _set_cooldown_label("kling", duration=e.retry_after, status=e.status)
        except Exception as e:
            msg = redact_secrets(str(e))
            _log_failure("video", "kling", msg)
            _set_cooldown_label("kling", status=STATUS_UNAVAILABLE)

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
        except ProviderError as e:
            _log_failure("video", label, e.reason)
            _set_cooldown_label(label, duration=e.retry_after, status=e.status)
        except Exception as e:
            msg = redact_secrets(str(e))
            _log_failure("video", label, msg)
            _set_cooldown_label(label, status=STATUS_UNAVAILABLE)

    raise RuntimeError(
        "All available models for video are currently rate-limited or "
        "unavailable. Please try again shortly."
    )


def get_chain_status():
    """Returns provider -> on_cooldown bool, for HUD display (no keys/secrets exposed)."""
    all_labels = {label for chain in _CHAINS.values() for label, _ in chain}
    all_labels |= {"hf_flux_schnell", "hf_sd35_turbo", "hf_wan_video", "hf_ltx_video", "pollinations", "pollinations_video", "kling"}
    return {label: _on_cooldown_label(label) for label in sorted(all_labels)}
