"""Permission-aware website and Windows control for E.D.I.T.H.

This module deliberately exposes a small, auditable action vocabulary instead
of arbitrary shell execution.  Both typed and spoken commands reach it through
the normal router/agent path.
"""

from __future__ import annotations

import re
import time
import uuid
import webbrowser
from dataclasses import dataclass, field
from threading import Lock
from urllib.parse import quote_plus, urlparse


SITE_URLS = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "linkedin": "https://www.linkedin.com",
    "whatsapp": "https://web.whatsapp.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://www.wikipedia.org",
    "amazon": "https://www.amazon.in",
    "drive": "https://drive.google.com",
    "calendar": "https://calendar.google.com",
    "maps": "https://maps.google.com",
}

SEARCH_URLS = {
    "google": "https://www.google.com/search?q={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "github": "https://github.com/search?q={query}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={query}",
    "amazon": "https://www.amazon.in/s?k={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={query}",
}

SAFE_KEYS = {
    "backspace", "down", "end", "enter", "esc", "home", "left",
    "pagedown", "pageup", "right", "space", "tab", "up",
    "volumeup", "volumedown", "volumemute", "playpause",
}
SAFE_HOTKEYS = {
    ("ctrl", "a"), ("ctrl", "c"), ("ctrl", "f"), ("ctrl", "l"),
    ("ctrl", "n"), ("ctrl", "r"), ("ctrl", "t"), ("ctrl", "v"),
    ("ctrl", "w"), ("ctrl", "shift", "t"), ("alt", "left"),
    ("alt", "right"), ("alt", "tab"), ("win", "d"),
}
HIGH_IMPACT_WORDS = re.compile(
    r"\b(delete|remove|purchase|buy|pay|transfer|submit|send|publish|post|"
    r"shutdown|restart|format|password|credential|api[ _-]?key)\b", re.I
)

# Patterns that suggest the text to be typed is a credential or secret.
# These are checked *regardless* of HIGH_IMPACT_WORDS so that even
# "low-impact" type_text actions are blocked when the content looks sensitive.
CREDENTIAL_PATTERNS = re.compile(
    r"(?i)(?:password|passwd|secret|api[ _-]?key|bearer\s|token|auth|gsk_|sk-|AQ\.|AKIA)"
)


@dataclass
class PendingAction:
    action: str
    args: dict
    created_at: float
    expected_window: str = field(default="")  # lower-cased active window title at queue time


_pending: dict[str, PendingAction] = {}
_pending_lock = Lock()
_PENDING_TTL = 300


def capabilities() -> str:
    return (
        "E.D.I.T.H. unified control is online. Supported: open named Windows "
        "apps; open any valid http/https website; search Google, YouTube, "
        "GitHub, Wikipedia, Amazon, Reddit and LinkedIn; browser back, forward, "
        "refresh, new/close/reopen tab; safe keyboard shortcuts; type text; "
        "media/volume keys; and take screenshots. High-impact actions require "
        "an explicit confirmation. Unsupported sites can still be opened by URL."
    )


def _clean_url(value: str) -> str | None:
    value = value.strip()
    key = value.lower().removeprefix("www.").rstrip("/")
    if key in SITE_URLS:
        return SITE_URLS[key]
    if re.fullmatch(r"[\w.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?", value):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def open_website(destination: str) -> str:
    url = _clean_url(destination)
    if not url:
        return (
            "ERROR: Give a website name (for example YouTube) or a complete "
            "http/https URL. Search requests should use search_website."
        )
    opened = webbrowser.open(url, new=2)
    return f"SUCCESS: Opened {url}" if opened else f"ERROR: Browser did not accept {url}"


def search_website(site: str, query: str) -> str:
    site_key = (site or "google").strip().lower()
    query = query.strip()
    if not query:
        return "ERROR: Search query is empty."
    template = SEARCH_URLS.get(site_key)
    if not template:
        return f"ERROR: Search integration '{site}' is unsupported. Available: {', '.join(SEARCH_URLS)}"
    url = template.format(query=quote_plus(query))
    opened = webbrowser.open(url, new=2)
    return f"SUCCESS: Searching {site_key} for '{query}'" if opened else "ERROR: Browser did not accept the search URL."


def _get_active_window_title() -> str:
    """Return the title of the currently focused window, lower-cased.

    Returns an empty string if pyautogui is not available or the platform
    does not support getActiveWindowTitle.
    """
    try:
        import pyautogui
        title = pyautogui.getActiveWindowTitle()
        return (title or "").lower()
    except Exception:
        return ""


def _pyautogui():
    try:
        import pyautogui
        pyautogui.PAUSE = 0.08
        pyautogui.FAILSAFE = True
        return pyautogui
    except Exception as exc:
        raise RuntimeError(f"Windows automation is unavailable: {exc}") from exc


def _execute(action: str, target: str = "", text: str = "", keys=None) -> str:
    action = action.strip().lower().replace(" ", "_")
    target = target.strip()
    keys = [str(k).lower().strip() for k in (keys or []) if str(k).strip()]

    if action == "open_app":
        from plugins.all_phases import open_app
        return open_app(f"open {target}") or f"ERROR: Unknown application '{target}'."
    if action == "close_app":
        from plugins.all_phases import close_app
        return close_app(f"close {target}") or f"ERROR: Unknown application '{target}'."
    if action == "open_website":
        return open_website(target)
    if action == "search_website":
        return search_website(target or "google", text)

    gui = _pyautogui()
    if action == "type_text":
        if not text:
            return "ERROR: No text supplied."
        # ── Block credential-like content regardless of the intended target ──
        if CREDENTIAL_PATTERNS.search(text):
            return (
                "BLOCKED: The text to be typed appears to contain a credential, "
                "secret, or API key. EDITH will not type sensitive credentials "
                "into any application."
            )
        # ── Verify the focused window matches the expected target ──
        if target:
            active = _get_active_window_title()
            if active and target.lower() not in active:
                return (
                    f"BLOCKED: Active window ('{active}') does not match the "
                    f"expected target ('{target}'). Focus the correct window first."
                )
        gui.write(text, interval=0.015)
        return f"SUCCESS: Typed {len(text)} characters into the focused control."
    if action == "press_key":
        key = (target or (keys[0] if keys else "")).lower()
        if key not in SAFE_KEYS:
            return f"BLOCKED: Key '{key}' is outside the safe key allowlist."
        gui.press(key)
        return f"SUCCESS: Pressed {key}."
    if action == "hotkey":
        combo = tuple(keys or [k.strip().lower() for k in target.split("+") if k.strip()])
        if combo not in SAFE_HOTKEYS:
            return f"BLOCKED: Shortcut '{'+'.join(combo)}' is outside the safe shortcut allowlist."
        gui.hotkey(*combo)
        return f"SUCCESS: Pressed {'+'.join(combo)}."
    if action == "screenshot":
        from pathlib import Path
        from datetime import datetime
        folder = Path.home() / "Pictures" / "EDITH"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"edith_capture_{datetime.now():%Y%m%d_%H%M%S}.png"
        gui.screenshot(str(path))
        return f"SUCCESS: Screenshot saved to {path}"
    return f"ERROR: Unknown control action '{action}'."


def control(action: str, target: str = "", text: str = "", keys=None, **kwargs) -> str:
    """Execute an allowlisted action, confirmation-gating high-impact intent."""
    description = " ".join([action, target, text, " ".join(keys or [])])
    needs_confirmation = action.lower() in {"close_app"} or bool(HIGH_IMPACT_WORDS.search(description))
    # Client-supplied approval flags (e.g. confirmed=True) are strictly forbidden
    # from bypassing authorization. High-impact operations must be approved via confirm(token).
    if needs_confirmation:
        token = uuid.uuid4().hex[:8].upper()
        with _pending_lock:
            now = time.time()
            for old_token in list(_pending):
                if now - _pending[old_token].created_at > _PENDING_TTL:
                    _pending.pop(old_token, None)
            _pending[token] = PendingAction(
                action,
                {"target": target, "text": text, "keys": keys},
                now,
                expected_window=_get_active_window_title(),
            )
        return (
            f"CONFIRMATION_REQUIRED [{token}]: This action may change external state: "
            f"{action} {target}. Say or type 'confirm {token}' within 5 minutes to continue."
        )
    return _execute(action, target=target, text=text, keys=keys)


def confirm(token: str) -> str:
    token = token.strip().upper()
    with _pending_lock:
        item = _pending.pop(token, None)
    if not item:
        return "ERROR: Confirmation token is invalid or has already been used."
    if time.time() - item.created_at > _PENDING_TTL:
        return "ERROR: Confirmation expired. Please request the action again."

    # ── Focus-drift check: verify the active window has not changed to something
    # unrelated since the action was queued.  An empty expected_window means
    # the window title was not available when the action was queued (e.g. no
    # pyautogui on CI), so we skip the check rather than blocking legitimate use.
    if item.expected_window:
        current = _get_active_window_title()
        if current and item.expected_window not in current and current not in item.expected_window:
            return (
                f"BLOCKED: The active window has changed from '{item.expected_window}' to "
                f"'{current}' since the action was approved. To prevent accidental input "
                f"into the wrong application, the action has been cancelled. "
                f"Please re-request the action with the correct window focused."
            )

    return _execute(item.action, **item.args)


def cancel(token: str) -> str:
    """Cancel a pending confirmation token without executing the action."""
    token = token.strip().upper()
    with _pending_lock:
        item = _pending.pop(token, None)
    if not item:
        return "ERROR: Confirmation token is invalid or has already been used."
    return f"CANCELLED: Action '{item.action}' has been cancelled and will not be executed."
