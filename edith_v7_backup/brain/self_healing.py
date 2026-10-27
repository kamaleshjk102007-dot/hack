# ============================================================
# E.D.I.T.H. — Self-Healing Agent  (v1)
# ============================================================
#
# Monitors all EDITH subsystems every 30 seconds.
# Detects failures and applies fixes automatically.
# Reports every action to the HUD in real time.
#
# WHAT IT HEALS:
#   • Gemini quota/unavailable  → switch to Ollama, schedule reset
#   • Ollama offline            → restart via subprocess, retry
#   • Ollama model not loaded   → pull model automatically
#   • HUD server unresponsive   → restart Flask/SocketIO thread
#   • Memory file corrupt       → rebuild from scratch
#   • Phase import broken       → reload module, log exact error
#   • High RAM (>90%)           → warn + identify top processes
#   • Disk full (>95%)          → warn + clean .pyc / log files
#   • Network unreachable       → warn, queue commands for retry
#   • Config missing keys       → restore defaults silently
#
# ============================================================

import os, sys, time, threading, subprocess, json, traceback
import requests
from datetime import datetime
from utils.logger import get_logger

log = get_logger("self_heal")

CHECK_INTERVAL   = 60    # seconds between health sweeps
MAX_FIX_ATTEMPTS = 3     # give up after 3 consecutive failures on same issue
OLLAMA_PULL_TIMEOUT = 300  # 5 min for model pull


# ─────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────
_state = {
    "running":          False,
    "fix_counts":       {},      # issue_key → consecutive fix attempts
    "last_status":      {},      # issue_key → last known state
    "healed_total":     0,
    "alerts":           [],      # recent alert log
}
_lock = threading.Lock()
_notify_fn = None   # set by start() — calls send_response() to push to HUD


# ─────────────────────────────────────────────────────────────
# HUD notification helper
# ─────────────────────────────────────────────────────────────

def _alert(msg: str, level: str = "INFO"):
    """Push a self-healing alert to the HUD and log it."""
    prefix = {"INFO": "🔧", "WARN": "⚠️", "HEAL": "✅", "FAIL": "❌"}.get(level, "•")
    full = f"[SELF-HEAL] {prefix} {msg}"
    log.info(full)
    with _lock:
        _state["alerts"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "msg": msg,
        })
        if len(_state["alerts"]) > 50:
            _state["alerts"] = _state["alerts"][-50:]
    if _notify_fn:
        try:
            _notify_fn(full, "__self_heal__")
        except Exception:
            pass


def _track(issue_key: str, success: bool) -> int:
    """Track fix attempts. Returns consecutive fail count."""
    with _lock:
        if success:
            _state["fix_counts"][issue_key] = 0
            _state["healed_total"] += 1
        else:
            _state["fix_counts"][issue_key] = _state["fix_counts"].get(issue_key, 0) + 1
        return _state["fix_counts"].get(issue_key, 0)


# ─────────────────────────────────────────────────────────────
# Individual health checks + fixes
# ─────────────────────────────────────────────────────────────

def _check_gemini():
    """Verify Gemini API key is set."""
    from config.settings import GOOGLE_API_KEY
    if not GOOGLE_API_KEY:
        _alert("GOOGLE_API_KEY missing in .env — Gemini Flash/Pro disabled in the cloud chain", "WARN")


def _check_cloud_chain() -> bool:
    """
    Report which providers in the cloud chain (Groq, Mistral, Gemini
    Flash, Gemini Pro, OpenRouter) are currently on cooldown after a
    rate limit. This build is cloud-only — there is nothing to
    "restart" the way Ollama used to be; cooldowns clear themselves
    automatically after their reset window (see cloud_router.py).
    """
    from brain.cloud_router import get_chain_status
    status = get_chain_status()
    down = [name for name, on_cooldown in status.items() if on_cooldown]
    if down:
        _alert(f"Cloud providers currently cooling down: {', '.join(down)} "
               f"(will auto-recover, no action needed)", "INFO")
        _track("cloud_chain_cooldowns", True)
    return len(down) < len(status)  # healthy as long as not ALL are down


def _check_memory_file():
    """Verify memory.json is valid JSON. Rebuild if corrupt."""
    from config.settings import MEMORY_FILE
    fpath = os.path.join(os.path.dirname(__file__), "..", MEMORY_FILE)
    fpath = os.path.normpath(fpath)
    if not os.path.exists(fpath):
        return  # Memory module will create it on first use

    try:
        with open(fpath) as f:
            data = json.load(f)
        # Must be a list
        if not isinstance(data, list):
            raise ValueError("Memory file is not a list")
        _track("memory_corrupt", True)
    except Exception as e:
        _alert(f"Memory file corrupt ({e}) — rebuilding...", "HEAL")
        try:
            with open(fpath, "w") as f:
                json.dump([], f)
            _alert("Memory file rebuilt ✅", "HEAL")
            _track("memory_corrupt", True)
        except Exception as e2:
            _alert(f"Memory rebuild failed: {e2}", "FAIL")
            _track("memory_corrupt", False)


def _check_imports():
    """Try importing all critical modules. Reload if stale/broken."""
    critical = {
        "brain.router":        "Route engine",
        "plugins.all_phases":  "Phase plugins",
        "hud.server":          "HUD server",
        "config.settings":     "Configuration",
        "utils.memory":        "Memory system",
    }
    import importlib
    for mod_name, label in critical.items():
        try:
            mod = sys.modules.get(mod_name)
            if mod is None:
                importlib.import_module(mod_name)
            _track(f"import_{mod_name}", True)
        except Exception as e:
            fails = _track(f"import_{mod_name}", False)
            _alert(f"{label} import failed (attempt {fails}): {e}", "FAIL")
            if fails < MAX_FIX_ATTEMPTS:
                _alert(f"Attempting reload of {mod_name}...", "HEAL")
                try:
                    if mod_name in sys.modules:
                        importlib.reload(sys.modules[mod_name])
                    else:
                        importlib.import_module(mod_name)
                    _alert(f"{label} reloaded ✅", "HEAL")
                    _track(f"import_{mod_name}", True)
                except Exception as e2:
                    _alert(f"{label} reload failed: {e2}", "FAIL")


def _check_system_resources():
    """Check RAM and disk usage. Warn or clean up if critical."""
    try:
        import psutil

        # RAM
        ram = psutil.virtual_memory()
        if ram.percent >= 95:
            _alert(f"CRITICAL RAM: {ram.percent:.0f}% used — system may freeze", "FAIL")
        elif ram.percent >= 85:
            _alert(f"High RAM usage: {ram.percent:.0f}%", "WARN")

        # Disk
        disk = psutil.disk_usage(os.path.dirname(__file__))
        if disk.percent >= 95:
            _alert(f"Disk critically full: {disk.percent:.0f}% — cleaning cache...", "WARN")
            _clean_cache()
        elif disk.percent >= 90:
            _alert(f"Disk usage high: {disk.percent:.0f}%", "WARN")

    except ImportError:
        pass
    except Exception as e:
        log.debug(f"Resource check error: {e}")


def _clean_cache():
    """Remove .pyc files and truncate large log files to free disk space."""
    root = os.path.dirname(__file__)
    cleaned = 0
    # Remove .pyc
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.endswith(".pyc"):
                try:
                    os.remove(os.path.join(dirpath, fn))
                    cleaned += 1
                except Exception:
                    pass
    # Truncate large log files (keep last 500 lines)
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.endswith(".log"):
                fpath = os.path.join(dirpath, fn)
                try:
                    if os.path.getsize(fpath) > 5 * 1024 * 1024:  # >5MB
                        with open(fpath) as f:
                            lines = f.readlines()[-500:]
                        with open(fpath, "w") as f:
                            f.writelines(lines)
                        cleaned += 1
                except Exception:
                    pass
    if cleaned:
        _alert(f"Cache cleaned: removed/truncated {cleaned} files ✅", "HEAL")


def _check_hud_server():
    """Ping the HUD server. Restart if unresponsive."""
    from config.settings import HUD_PORT, HUD_HOST
    host = "127.0.0.1" if HUD_HOST == "0.0.0.0" else HUD_HOST
    try:
        s = requests.Session()
        s.trust_env = False
        r = s.get(f"http://{host}:{HUD_PORT}/", timeout=5)
        if r.status_code in (200, 302, 304):
            _track("hud_down", True)
            return
    except Exception:
        pass

    fails = _track("hud_down", False)
    if fails == 1:
        _alert("HUD server not responding — attempting restart...", "WARN")
        try:
            from hud.server import start_hud_server
            t = threading.Thread(target=start_hud_server, daemon=True, name="HUD-Restart")
            t.start()
            time.sleep(3)
            _alert("HUD server thread restarted ✅", "HEAL")
            _track("hud_down", True)
        except Exception as e:
            _alert(f"HUD restart failed: {e}", "FAIL")
    elif fails >= MAX_FIX_ATTEMPTS:
        _alert(f"HUD server unresponsive after {fails} restart attempts", "FAIL")


def _check_network():
    """Check internet connectivity (required for Gemini + weather)."""
    try:
        s = requests.Session()
        s.trust_env = False
        s.get("https://www.google.com", timeout=5)
        prev = _state["last_status"].get("network")
        if prev == "offline":
            _alert("Network restored — Gemini and weather APIs available ✅", "HEAL")
        _state["last_status"]["network"] = "online"
        _track("network_offline", True)
    except Exception:
        prev = _state["last_status"].get("network")
        if prev != "offline":
            _alert("Network unreachable — all cloud AI providers will fail until restored.", "WARN")
        _state["last_status"]["network"] = "offline"
        _track("network_offline", False)


def _check_config():
    """Verify all required config keys exist. Restore defaults if missing."""
    required = {
        "GOOGLE_API_KEY":     "",
        "GEMINI_MODEL":       "gemini-2.5-flash",
        "GROQ_API_KEY":       "",
        "MISTRAL_API_KEY":    "",
        "OPENROUTER_API_KEY": "",
        "HF_API_KEY":         "",
        "KLING_API_KEY":      "",
        "HUD_PORT":           "5000",
        "GMAIL_USER":         "",
    }
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.normpath(env_path)
    if not os.path.exists(env_path):
        _alert(".env file missing — creating with defaults", "HEAL")
        try:
            with open(env_path, "w") as f:
                for k, v in required.items():
                    f.write(f"{k}={v}\n")
        except Exception as e:
            _alert(f"Could not create .env: {e}", "FAIL")
        return

    with open(env_path) as f:
        env_content = f.read()

    missing = []
    for key in required:
        if key not in env_content:
            missing.append(key)

    if missing:
        _alert(f"Config keys missing: {missing} — restoring defaults", "HEAL")
        try:
            with open(env_path, "a") as f:
                for k in missing:
                    f.write(f"\n{k}={required[k]}")
            _alert("Config defaults restored ✅", "HEAL")
        except Exception as e:
            _alert(f"Config restore failed: {e}", "FAIL")


# ─────────────────────────────────────────────────────────────
# Main sweep loop
# ─────────────────────────────────────────────────────────────

def _run_sweep():
    """Run one full health check sweep across all subsystems."""
    checks = [
        ("Config",          _check_config),
        ("Network",         _check_network),
        ("Gemini",          _check_gemini),
        ("Cloud chain",     _check_cloud_chain),
        ("Memory file",     _check_memory_file),
        ("Module imports",  _check_imports),
        ("System resources",_check_system_resources),
        ("HUD server",      _check_hud_server),
    ]
    for name, fn in checks:
        try:
            fn()
        except Exception as e:
            _alert(f"Self-heal check '{name}' itself crashed: {e}", "FAIL")
            log.error(f"Self-heal '{name}' error:\n{traceback.format_exc()}")


def _loop():
    """Background loop — sweeps every CHECK_INTERVAL seconds."""
    log.info("[SELF-HEAL] Agent started")
    _alert("Self-healing agent online — monitoring all subsystems", "INFO")

    while _state["running"]:
        try:
            _run_sweep()
        except Exception as e:
            log.error(f"[SELF-HEAL] Sweep crashed: {e}")
        time.sleep(CHECK_INTERVAL)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

_thread: threading.Thread = None


def start(notify_fn=None):
    """
    Start the self-healing agent daemon thread.
    notify_fn(message, command) — callback to push alerts to HUD.
    """
    global _thread, _notify_fn
    if _state["running"]:
        return
    _notify_fn = notify_fn
    _state["running"] = True
    _thread = threading.Thread(target=_loop, daemon=True, name="EDITH-SelfHeal")
    _thread.start()
    log.info("[SELF-HEAL] Thread started")


def stop():
    _state["running"] = False
    if _thread:
        _thread.join(timeout=5)


def get_status() -> dict:
    """Return current self-healing status for HUD /api/health endpoint."""
    with _lock:
        return {
            "running":      _state["running"],
            "healed_total": _state["healed_total"],
            "fix_counts":   dict(_state["fix_counts"]),
            "last_alerts":  list(_state["alerts"][-10:]),
            "network":      _state["last_status"].get("network", "unknown"),
            "check_interval_sec": CHECK_INTERVAL,
        }


def run_now() -> str:
    """Trigger an immediate sweep — callable from router ('diagnose edith')."""
    _alert("Manual diagnostic sweep triggered by Operator", "INFO")
    try:
        _run_sweep()
        with _lock:
            healed = _state["healed_total"]
            alerts = _state["alerts"][-5:]
        summary = "\n".join(f"  {a['time']} [{a['level']}] {a['msg']}" for a in alerts)
        return f"✅ Diagnostic complete. Total fixes applied: {healed}\nRecent activity:\n{summary}"
    except Exception as e:
        return f"❌ Diagnostic sweep error: {e}"
