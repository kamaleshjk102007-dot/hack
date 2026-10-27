# ============================================================
# E.D.I.T.H. — Settings
# ============================================================

import os
from pathlib import Path

# Load .env file
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

def _get(key, default=""): return os.getenv(key, default)

# ── Identity ──────────────────────────────────────────────────
ASSISTANT_NAME = "E.D.I.T.H."
USER_TITLE     = "Sir"
VERSION        = "9.4.0"

# ── User Location ─────────────────────────────────────────────
USER_CITY    = _get("EDITH_CITY",    "Bangarmau")
USER_STATE   = _get("EDITH_STATE",   "Uttar Pradesh")
USER_COUNTRY = _get("EDITH_COUNTRY", "India")
USER_LAT     = _get("EDITH_LAT",     "27.6833")
USER_LON     = _get("EDITH_LON",     "80.2167")

# ── AI Backend ────────────────────────────────────────────────
# "cloud" = multi-provider cloud chain (Groq -> Mistral -> Gemini Flash
#           -> Gemini Pro -> OpenRouter). No local inference, no Ollama.
AI_BACKEND = _get("EDITH_AI_BACKEND", "cloud").lower()

# Google Gemini (Flash + Pro share one key; model name picks the tier)
GOOGLE_API_KEY    = _get("GOOGLE_API_KEY", "")
GEMINI_MODEL      = _get("EDITH_GEMINI_MODEL",     "gemini-2.5-flash")
GEMINI_PRO_MODEL  = _get("EDITH_GEMINI_PRO_MODEL", "gemini-2.5-pro")
GEMINI_API_URL    = "https://generativelanguage.googleapis.com/v1beta/models"

# Groq (code / agent / vision / speech / safety — see brain/cloud_router.py)
GROQ_API_KEY        = _get("GROQ_API_KEY", "")
GROQ_MODEL_CODE     = _get("EDITH_GROQ_MODEL_CODE",     "openai/gpt-oss-120b")
GROQ_MODEL_LLAMA33  = _get("EDITH_GROQ_MODEL_LLAMA33",  "llama-3.3-70b-versatile")
GROQ_MODEL_VISION   = _get("EDITH_GROQ_MODEL_VISION",   "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_MODEL_QWEN     = _get("EDITH_GROQ_MODEL_QWEN",     "qwen/qwen3-32b")
GROQ_MODEL_SAFETY   = _get("EDITH_GROQ_MODEL_SAFETY",   "openai/gpt-oss-20b")
GROQ_MODEL_WHISPER_TURBO = _get("EDITH_GROQ_MODEL_WHISPER_TURBO", "whisper-large-v3-turbo")
GROQ_MODEL_WHISPER       = _get("EDITH_GROQ_MODEL_WHISPER",       "whisper-large-v3")
GROQ_MODEL_TTS_EN   = _get("EDITH_GROQ_MODEL_TTS_EN",   "playai-tts")
GROQ_MODEL_TTS_AR   = _get("EDITH_GROQ_MODEL_TTS_AR",   "playai-tts-arabic")

# Mistral (Codestral / Mistral Small)
MISTRAL_API_KEY = _get("MISTRAL_API_KEY", "")
MISTRAL_MODEL   = _get("EDITH_MISTRAL_MODEL", "codestral-latest")

# OpenRouter (daily-tier overflow / free router)
OPENROUTER_API_KEY = _get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = _get("EDITH_OPENROUTER_MODEL", "openrouter/free")

# Hugging Face Inference Providers (free-tier image / video generation).
# Comma-separated overrides let you change models without editing source.
HF_API_KEY = _get("HF_API_KEY", "")
HF_IMAGE_MODELS = tuple(x.strip() for x in _get(
    "EDITH_HF_IMAGE_MODELS",
    "black-forest-labs/FLUX.1-schnell,stabilityai/stable-diffusion-3.5-large-turbo",
).split(",") if x.strip())
HF_VIDEO_MODELS = tuple(x.strip() for x in _get(
    "EDITH_HF_VIDEO_MODELS",
    "Wan-AI/Wan2.1-T2V-1.3B,Lightricks/LTX-Video",
).split(",") if x.strip())

POLLINATIONS_API_KEY = _get("POLLINATIONS_API_KEY", "")
POLLINATIONS_VIDEO_MODEL = _get("EDITH_POLLINATIONS_VIDEO_MODEL", "wan-fast")

# Kling (video generation)
KLING_API_KEY = _get("KLING_API_KEY", "")
KLING_API_URL = _get("EDITH_KLING_API_URL", "https://api-singapore.klingai.com")

TEMPERATURE = float(_get("EDITH_TEMPERATURE", "0.3"))
MAX_TOKENS  = int(_get("EDITH_MAX_TOKENS",    "2048"))

# Legacy / unused — kept only so older modules that still import these
# names don't crash. The cloud chain (brain/cloud_router.py) does not
# use Ollama at all.
OLLAMA_URL   = ""
OLLAMA_MODEL = "disabled (cloud-only build)"

# ── Voice ─────────────────────────────────────────────────────
TTS_ENGINE = _get("EDITH_TTS_ENGINE", "pyttsx3").lower()
STT_ENGINE = _get("EDITH_STT_ENGINE", "none").lower()

# ── Email (Phase 9) ───────────────────────────────────────────
GMAIL_USER = _get("GMAIL_USER")
GMAIL_PASS = _get("GMAIL_PASSWORD")
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 587
IMAP_HOST  = "imap.gmail.com"
IMAP_PORT  = 993

# ── WhatsApp Contacts ─────────────────────────────────────────
WHATSAPP_CONTACTS = {
    "mom":    "+916385116517",
    "mum":    "+916385116517",
    "mama":   "+916385116517",
    "mother": "+916385116517",
    "dad":    "+919876543210",
    "me":     "+9163116517",
}

# ── HUD Server ────────────────────────────────────────────────
HUD_PORT = int(_get("EDITH_HUD_PORT", "5000"))
HUD_HOST = _get("EDITH_HUD_HOST", "0.0.0.0")

# ── Logging ───────────────────────────────────────────────────
LOG_LEVEL = _get("EDITH_LOG_LEVEL", "INFO")
LOG_FILE  = _get("EDITH_LOG_FILE",  "edith.log")

# ── Memory ────────────────────────────────────────────────────
MEMORY_FILE = _get("EDITH_MEMORY_FILE", "memory.json")
MEMORY_MAX  = int(_get("EDITH_MEMORY_MAX", "50"))

# ── App Maps (Phase 4) ────────────────────────────────────────
WEBSITES = {
    "youtube":   "https://youtube.com",  "google":    "https://google.com",
    "gmail":     "https://gmail.com",    "github":    "https://github.com",
    "chatgpt":   "https://chatgpt.com",  "claude":    "https://claude.ai",
    "twitter":   "https://twitter.com",  "facebook":  "https://facebook.com",
    "linkedin":  "https://linkedin.com", "reddit":    "https://reddit.com",
    "amazon":    "https://amazon.com",   "wikipedia": "https://wikipedia.org",
}
DESKTOP_APPS = {
    "notepad":   "notepad",  "calculator": "calc",
    "vs code":   "code",     "vscode":     "code",
    "chrome":    "chrome",   "firefox":    "firefox",
    "edge":      "msedge",   "word":       "winword",
    "excel":     "excel",    "outlook":    "outlook",
    "paint":     "mspaint",  "explorer":   "explorer",
}
