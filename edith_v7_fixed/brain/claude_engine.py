# ============================================================
# E.D.I.T.H. — Claude Code Engine  (v5 UPGRADE)
# Uses Anthropic Claude API for all project/code generation
# This is what makes EDITH write code like Claude does:
#   - Full files, no placeholders, no TODOs, no ellipsis
#   - Proper imports, error handling, working logic
#   - Same quality as Claude.ai artifacts
# ============================================================

import os
import re
import requests
from utils.logger import get_logger

log = get_logger("claude_engine")

CLAUDE_API_URL   = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL     = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 8192   # Full files — never truncated

# ── Read API key from .env / environment ──────────────────────
def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        # Try reading from .env directly
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        env_path = os.path.abspath(env_path)
        if os.path.exists(env_path):
            for line in open(env_path).read().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    return key


def is_available() -> bool:
    """Check if Claude API key is configured."""
    return bool(_get_api_key())


def code_query(prompt: str, system: str = "", max_tokens: int = CLAUDE_MAX_TOKENS) -> str:
    """
    Query Claude for code generation.
    Returns raw content — strips markdown fences automatically.
    This is the engine that makes project files identical to Claude-written code.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to your .env file:\n"
            "ANTHROPIC_API_KEY=sk-ant-..."
        )

    if not system:
        system = (
            "You are an expert software developer writing production-quality code. "
            "Return ONLY the file content — no explanations, no markdown fences, "
            "no preamble, no apologies. Write complete, working code with proper "
            "imports, error handling, and real logic. Never use placeholders, "
            "TODOs, or ellipsis (...). Every function must be fully implemented."
        )

    headers = {
        "Content-Type":      "application/json",
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
    }

    payload = {
        "model":      CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system":     system,
        "messages":   [{"role": "user", "content": prompt}],
    }

    try:
        resp = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=120)
    except requests.exceptions.Timeout:
        raise RuntimeError("Claude API timed out after 120s — check your network")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"Cannot reach Claude API: {e}")

    if resp.status_code == 401:
        raise RuntimeError("Invalid ANTHROPIC_API_KEY — check your .env")
    if resp.status_code == 429:
        raise RuntimeError("Claude API rate-limited — wait a moment and retry")
    if resp.status_code == 529:
        raise RuntimeError("Claude API overloaded — retry in a few seconds")
    if resp.status_code != 200:
        raise RuntimeError(f"Claude API HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    try:
        content = data["content"][0]["text"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Unexpected Claude response structure: {data}")

    # Strip any markdown fences Claude might add despite instructions
    content = re.sub(r"^```[\w]*\n?", "", content)
    content = re.sub(r"\n?```$", "", content)

    log.info(f"[Claude] ✅ Response: {len(content)} chars")
    return content


def json_query(prompt: str, system: str = "") -> dict:
    """
    Query Claude expecting a JSON response.
    Handles stripping fences and parsing safely.
    """
    import json
    if not system:
        system = (
            "You are a software architect. "
            "Respond ONLY with valid JSON. No markdown backticks, no explanation, "
            "no preamble. Start your response with { and end with }."
        )
    for attempt in range(2):
        try:
            raw = code_query(prompt, system)
            raw = re.sub(r"```json|```", "", raw).strip()
            # Find first { or [ to trim any accidental preamble
            for i, ch in enumerate(raw):
                if ch in "{[":
                    raw = raw[i:]
                    break
            return json.loads(raw)
        except Exception as e:
            log.warning(f"[Claude] JSON parse attempt {attempt+1} failed: {e}")
    return {}


def get_status() -> dict:
    """Return engine status for HUD."""
    available = is_available()
    return {
        "active":    CLAUDE_MODEL if available else "unavailable",
        "model":     CLAUDE_MODEL,
        "available": available,
        "api_key":   "set" if available else "missing — add ANTHROPIC_API_KEY to .env",
    }
