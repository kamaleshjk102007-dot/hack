#!/usr/bin/env python3
# ============================================================
# E.D.I.T.H. — Main Entry Point  (v5 — Self-Healing)
# AI: Gemini 2.5 Flash (primary) → phi3:mini (fallback)
# Self-Healing: monitors + auto-fixes all subsystems
# ============================================================

import os, sys, time, threading
sys.path.insert(0, os.path.dirname(__file__))

# ── Clear stale .pyc cache so updated router/plugins always load fresh ──
import shutil
for _root, _dirs, _files in os.walk(os.path.dirname(__file__) or '.'):
    for _d in _dirs:
        if _d == '__pycache__':
            shutil.rmtree(os.path.join(_root, _d), ignore_errors=True)

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


from config.settings import GMAIL_USER, GEMINI_MODEL
from utils.logger import get_logger
from brain.router import route
from hud.server import start_hud_server, get_command, send_response, send_project_notify

log = get_logger("edith")


def _build_banner():
    from brain.ai_engine import get_active_model, is_gemini_available, is_groq_available
    status   = get_active_model()
    chain    = " -> ".join(status.get("chain", []))
    g_ok     = "✅ ACTIVE" if is_gemini_available() else "⚠️  NO KEY"
    grq_ok   = "✅ ACTIVE" if is_groq_available()   else "⚠️  NO KEY"
    email    = GMAIL_USER or "Not configured"
    return f"""
╔══════════════════════════════════════════════════════════════╗
║        E.D.I.T.H. — Kamalesh Intelligence Framework         ║
║              Even Dead, I'm The Hero  v9.4.0                ║
╠══════════════════════════════════════════════════════════════╣
║  CLOUD CHAIN : {chain:<44} ║
║  Groq        : {grq_ok:<44} ║
║  Gemini      : {g_ok:<44} ║
║  Email       : {email:<44} ║
║  HUD         : http://localhost:5000                         ║
╠══════════════════════════════════════════════════════════════╣
║  Self-Healing: ACTIVE  (30s sweeps — auto-fix all systems)  ║
║  Phases: AI · WhatsApp · Docs · Apps · Agent                ║
║          Monitor · Search · Weather · Email · Proactive      ║
║  Mode: 100% CLOUD — no local inference (no Ollama)            ║
╚══════════════════════════════════════════════════════════════╝
"""


def check_engines():
    from brain.ai_engine import is_groq_available, is_gemini_available
    from config.settings import GOOGLE_API_KEY, GROQ_API_KEY
    print("── AI Engine Check ──────────────────────────────────")
    print("  Cloud chain: Groq -> Mistral -> Gemini Flash -> Gemini Pro -> OpenRouter")
    if not GROQ_API_KEY:
        print("  ⚠️  Groq: GROQ_API_KEY not set")
    elif is_groq_available():
        print("  ✅ Groq: ready (priority 1)")
    if not GOOGLE_API_KEY:
        print("  ⚠️  Gemini: GOOGLE_API_KEY not set")
    elif is_gemini_available():
        print(f"  ✅ Gemini: {GEMINI_MODEL} — ready")
    print("─────────────────────────────────────────────────────")


def _speak_proactive(text: str):
    """Callback for Phase 10 + self-healer → push alert to HUD + TTS."""
    try:
        send_response(f"[ALERT] {text}", "__background__")
    except Exception:
        pass
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception:
        pass


def hud_loop():
    log.info("Command loop started")
    print("\n[EDITH] HUD active → http://localhost:5000")
    print("[EDITH] Awaiting commands...\n")
    while True:
        cmd = get_command()
        if cmd:
            log.info(f"Processing: {cmd}")
            try:
                response = route(cmd, notify_fn=send_project_notify)
            except Exception as e:
                log.error(f"Route error: {e}")
                response = f"Error processing command: {e}"
            log.info(f"Response: {response[:80]}...")
            send_response(response, cmd)
            time.sleep(0.1)
        else:
            time.sleep(0.4)


def main():
    print(_build_banner())
    check_engines()

    # Start HUD server
    hud_t = threading.Thread(target=start_hud_server, daemon=True, name="HUD-Server")
    hud_t.start()
    time.sleep(1.5)

    # Phase 10 — Proactive background agent
    try:
        from plugins.all_phases import start_background_agent
        start_background_agent(speak_fn=_speak_proactive)
        print("✅ Phase 10: Proactive agent started")
    except Exception as e:
        log.warning(f"Phase 10 failed: {e}")

    # Self-Healing Agent — must start AFTER HUD so it can push alerts
    try:
        from brain.self_healing import start as start_healer
        start_healer(notify_fn=send_response)
        print("✅ Self-Healing Agent: ONLINE (30s sweeps)")
    except Exception as e:
        log.warning(f"Self-healer failed to start: {e}")

    try:
        hud_loop()
    except KeyboardInterrupt:
        print("\n\n[EDITH] Shutdown initiated. Goodbye, Sir.")
        from brain.self_healing import stop
        stop()


if __name__ == "__main__":
    main()
