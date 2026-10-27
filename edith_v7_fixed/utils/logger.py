import logging, sys, os, re
from logging.handlers import RotatingFileHandler
from config.settings import LOG_LEVEL, LOG_FILE

# Patterns to scrub from logs
_SECRET_PATTERNS = [
    (re.compile(r"gsk_[A-Za-z0-9_-]{16,}"), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"sk-or-v1-[A-Za-z0-9_-]{16,}"), "[REDACTED_OPENROUTER_KEY]"),
    (re.compile(r"sk-[A-Za-z0-9_-]{16,}"), "[REDACTED_API_KEY]"),
    # Pollinations uses sk_ (underscore) prefix — distinct from sk- above
    (re.compile(r"sk_[A-Za-z0-9_-]{16,}"), "[REDACTED_POLLINATIONS_KEY]"),
    (re.compile(r"hf_[A-Za-z0-9_-]{16,}"), "[REDACTED_HF_TOKEN]"),
    (re.compile(r"AQ\.[A-Za-z0-9_-]{16,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"api-key-kling-[A-Za-z0-9_-]+"), "[REDACTED_KLING_KEY]"),
    # Mistral keys: 32-char alphanumeric with no distinctive prefix —
    # match when associated with the Authorization header or key= patterns.
    (re.compile(r"(?i)(mistral[_-]?key|MISTRAL_API_KEY)[=:\s]+([A-Za-z0-9]{20,})"), r"\1=[REDACTED_MISTRAL_KEY]"),
    (re.compile(r"(?i)Bearer\s+([A-Za-z0-9_.-]{10,})"), r"Bearer [REDACTED]"),
    (re.compile(r"(?i)(key|password|token|secret|pass)=([A-Za-z0-9_-]{8,})"), r"\1=[REDACTED]"),
    (re.compile(r"\b\d{10}\b"), "[REDACTED_PHONE]"),
]

def redact_secrets(text: str) -> str:
    """Scrub sensitive credentials, tokens, and personal details from log text."""
    if not isinstance(text, str):
        text = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SecretRedactingFormatter(logging.Formatter):
    """Custom logging formatter that automatically redacts API keys and secrets."""
    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_secrets(original)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    fmt = SecretRedactingFormatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")

    sh = logging.StreamHandler(sys.stdout)
    try:
        sh.stream = open(sys.stdout.fileno(), 'w', encoding='utf-8', closefd=False)
    except Exception:
        pass
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if LOG_FILE:
        try:
            # Rotate at 5MB, keep 3 backup copies
            fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            pass

    return logger
