# ============================================================
# E.D.I.T.H. — Command Router  (Agentic v2.0)
# All commands go through the ReAct agent.
# Fast-path for trivial commands (greetings, time, etc.)
# to avoid unnecessary AI round-trips.
# ============================================================

import re
from datetime import datetime
from utils.logger import get_logger

log = get_logger("router")


def route(cmd: str, notify_fn=None) -> str:
    """
    Route command to agent or fast-path handler.
    notify_fn: optional callable(str) to push agent step updates to HUD.
    """
    c = cmd.lower().strip()
    log.info(f"Routing: {cmd[:80]}")

    # ── Fast-path: greetings (no AI needed) ───────────────────
    if re.match(r"^(hi|hello|hey|yo|greetings|what'?s up)[\s!?.]*$", c):
        return "E.D.I.T.H. online. All systems nominal. How may I assist, Sir?"

    if re.search(r"who are you|what are you|your name|introduce yourself", c):
        return ("I am E.D.I.T.H. — Even Dead I'm The Hero. "
                "Kamalesh's advanced agentic AI. "
                "I can search the web, run code, read/write files, "
                "build projects, and reason through complex tasks autonomously.")

    # ── Unified control: confirmation and capability discovery ─────
    confirmation = re.fullmatch(r"(?:confirm|approve|proceed)\s+([a-f0-9]{8})[\s.!?]*", c)
    if confirmation:
        from plugins.universal_control import confirm
        return confirm(confirmation.group(1))

    if re.search(r"\b(?:what can you control|control capabilities|supported (?:apps|websites|actions))\b", c):
        from plugins.universal_control import capabilities
        return capabilities()

    # ── Fast-path: time / date ─────────────────────────────────
    if re.match(r"^(what.*(time|date)|time|date|today|current time)[\s?]*$", c):
        now = datetime.now()
        return (f"🕐 {now:%I:%M:%S %p}  —  {now:%A, %B %d, %Y}")

    # ── Fast-path: EDITH network node status ──────────────────
    node_match = re.search(r"edith\s+network\s+node:\s*([\w-]+)", c)
    if node_match:
        return _node_status(node_match.group(1).upper())

    # ── Fast-path: image GENERATION (must run before image search) ────
    _GEN_IMAGE = re.compile(
        r'\b(?:generate|create|draw|render|paint|make)\b\s+(?:me\s+)?(?:an?\s+)?'
        r'((?:image|picture|photo|art|logo|illustration|drawing|painting)\b.*)', re.I)
    m = _GEN_IMAGE.search(c)
    if m:
        prompt = m.group(1).strip() or cmd
        from plugins.all_phases import create_image
        return create_image(prompt)

    # ── Fast-path: video GENERATION ────────────────────────────────
    # FIX: "create a video" was being misclassified by classify_task()
    # as task_type="video" and sent into the TEXT-generation router,
    # which has no "video" chain — it failed instantly with a generic
    # "rate-limited or unavailable" message and never touched Kling at
    # all. Route it directly to the real video generator instead.
    # Matches the noun anywhere in the sentence (e.g. "create a boy
    # dancing video"), not just immediately after the verb.
    _GEN_VIDEO = re.compile(
        r'\b(?:generate|create|render|make)\b.*\b(?:video|clip|animation)\b', re.I)
    if _GEN_VIDEO.search(c):
        prompt = re.sub(r'^\s*(?:generate|create|render|make)\s+(?:me\s+)?(?:an?\s+)?',
                         '', cmd, flags=re.I).strip() or cmd
        from plugins.all_phases import create_video
        return create_video(prompt)

    # ── Fast-path: image search (handled by image system) ─────
    _IMAGE_INTENT = re.compile(
        r'\b(?:image|photo|picture|pic|visual|photograph)s?\b', re.I)
    _TOPIC_AFTER  = re.compile(
        r'\b(?:image|photo|picture|pic|visual|photograph)s?\b\s*'
        r'(?:that|which|where|of|about|with|showing|shows|for|:)?\s*'
        r'(?:a\s+|an\s+|the\s+)?'
        r'([\w][\w\s,.-]+)', re.I)
    _TOPIC_BEFORE = re.compile(
        r'(?:show|display|get|fetch)\s+(?:me\s+)?(?:the\s+|a\s+|an\s+)?'
        r'([\w][\w\s,.-]+?)\s+(?:image|photo|picture|pic)s?\s*$', re.I)
    _WHAT_LOOK = re.compile(
        r'(?:what\s+does\s+|how\s+does\s+)([\w][\w\s,.-]+?)\s+look\s+like', re.I)

    if _IMAGE_INTENT.search(c):
        topic = None
        m = _TOPIC_BEFORE.search(c)
        if m: topic = m.group(1).strip()
        if not topic:
            m = _TOPIC_AFTER.search(c)
            if m: topic = m.group(1).strip()
        if topic:
            topic = re.sub(r'\s+(?:please|now|today|sir)\s*$', '', topic, flags=re.I).strip()
            topic = re.sub(r'^(?:a|an|the)\s+', '', topic, flags=re.I).strip()
        if topic and len(topic) > 1:
            from plugins.all_phases import fetch_topic_image
            return fetch_topic_image(topic)

    if _WHAT_LOOK.search(c):
        m = _WHAT_LOOK.search(c)
        topic = m.group(1).strip() if m else None
        if topic:
            from plugins.all_phases import fetch_topic_image
            return fetch_topic_image(topic)

    # ── Fast-path: map focus ───────────────────────────────────
    map_intent = re.search(
        r'(?:show|locate|find|map|zoom\s+to|navigate\s+to).*'
        r'(?:on|in)\s+(?:the\s+)?(?:map|satellite)|map\s+of\s+\w',
        c
    )
    if map_intent:
        place = re.sub(
            r'^(?:show|locate|find|map\s+of|zoom\s+to|navigate\s+to)\s*', '',
            cmd, flags=re.I).strip()
        place = re.sub(r'\s+on\s+(?:the\s+)?(?:map|satellite)\s*$', '',
                       place, flags=re.I).strip()
        if place:
            try:
                from hud.server import socketio
                socketio.emit('map_focus', {'query': place, 'label': place})
            except Exception:
                pass
            return f"🗺️ Locating '{place}' on satellite map, Sir."

    # ── Fast-path: WhatsApp (Phase 2) ────────────────────────
    if re.search(r'whatsapp|send.*whatsapp|message (mom|dad|mum|mother|papa|bhai|sis)|text (mom|dad)', c):
        from plugins.all_phases import send_whatsapp
        result = send_whatsapp(cmd)
        if result:
            return result

    # ── Fast-path: Word Document (styled, Phase 1-EXT) ─────────
    if re.search(r'\b(create|write|draft|generate|make)\b.*\bpdf\b', c):
        from plugins.all_phases import write_pdf
        return write_pdf(cmd)

    if re.search(r'(write|create|draft|generate|make)[ ]+(a[ ]+)?(styled|formatted|professional|formal)[ ]+word', c) or        re.search(r'word[ ]+(doc|document|report|file)', c):
        from plugins.all_phases import write_word_doc
        return write_word_doc(cmd)

    # ── Fast-path: Excel Spreadsheet (Phase 1-EXT) ───────────
    if re.search(r'(create|make|build|generate)[ ]+.*(excel|spreadsheet|xlsx|workbook|sheet)', c) or        re.search(r'excel[ ]+(for|about|with|table|tracker|report|budget)', c):
        from plugins.all_phases import write_excel
        return write_excel(cmd)

    # ── Fast-path: Dataset Creator (Phase 1-EXT) ─────────────
    if re.search(r'(create|make|build|generate)[ ]+.*(dataset|data set|csv|data file)', c) or        re.search(r'dataset[ ]+(of|about|with|for)', c):
        from plugins.all_phases import create_dataset
        return create_dataset(cmd)

    # ── Fast-path: Word document (Phase 3 legacy) ────────────
    if re.search(r'(write|create|draft|generate)[ ]+(a[ ]+)?(document|report|letter|essay|doc|word[ ]+file)', c):
        from plugins.all_phases import write_document
        return write_document(cmd)

    # ── Fast-path: website search/open and Windows control ───
    web_search_match = re.match(
        r"^(?:search|find|look up)\s+(?:on\s+)?"
        r"(google|youtube|github|wikipedia|amazon|reddit|linkedin)\s+(?:for\s+)?(.+)$",
        c,
    )
    if web_search_match:
        from plugins.universal_control import search_website
        return search_website(web_search_match.group(1), web_search_match.group(2))

    open_target = re.match(r"^(?:open|go to|visit)\s+(.+?)[\s.!?]*$", cmd.strip(), re.I)
    if open_target:
        destination = open_target.group(1).strip()
        from plugins.universal_control import SITE_URLS, open_website
        supplied_scheme = re.match(r"^([a-z][a-z0-9+.-]*):", destination, re.I)
        if supplied_scheme and supplied_scheme.group(1).lower() not in {"http", "https"}:
            return "BLOCKED: E.D.I.T.H. only opens http/https web addresses."
        looks_web = (
            destination.lower() in SITE_URLS
            or bool(re.match(r"https?://", destination, re.I))
            or bool(re.fullmatch(r"[\w.-]+\.[a-zA-Z]{2,}(?:/\S*)?", destination))
        )
        if looks_web:
            return open_website(destination)

    browser_actions = {
        "browser back": ("hotkey", "alt+left"),
        "go back": ("hotkey", "alt+left"),
        "browser forward": ("hotkey", "alt+right"),
        "go forward": ("hotkey", "alt+right"),
        "refresh page": ("hotkey", "ctrl+r"),
        "reload page": ("hotkey", "ctrl+r"),
        "new tab": ("hotkey", "ctrl+t"),
        "close tab": ("hotkey", "ctrl+w"),
        "reopen tab": ("hotkey", "ctrl+shift+t"),
        "take screenshot": ("screenshot", ""),
        "capture screen": ("screenshot", ""),
    }
    normalized_control = re.sub(r"[\s.!?]+$", "", c)
    if normalized_control in browser_actions:
        from plugins.universal_control import control
        action, target = browser_actions[normalized_control]
        return control(action, target=target)

    type_match = re.match(r"^(?:type|enter text)\s+(.+)$", cmd.strip(), re.I | re.S)
    if type_match:
        from plugins.universal_control import control
        return control("type_text", text=type_match.group(1))

    # ── Fast-path: Open app (Phase 4) ────────────────────────
    if re.search(r'^(open|launch|start|run)[ ]+[\w]', c):
        from plugins.all_phases import open_app
        result = open_app(cmd)
        if result:
            return result

    # ── Fast-path: Close app (Phase 4) ───────────────────────
    if re.search(r'^(close|exit|quit|kill|shutdown)[ ]+[\w]', c):
        from plugins.universal_control import control
        app_name = re.sub(r'^(?:close|exit|quit|kill|shutdown)\s+', '', cmd,
                          flags=re.I).strip()
        return control("close_app", target=app_name)

    # ── Fast-path: Check inbox (Phase 9) ─────────────────────
    if re.search(r'check[ ]+(my[ ]+)?(email|inbox|mail|gmail)', c):
        from plugins.all_phases import check_inbox
        return check_inbox()

    # ── Fast-path: diagnose / self-heal manual trigger ────────
    if re.search(r'diagnose|self.heal|run diagnostic|health check', c):
        from brain.self_healing import run_now
        return run_now()

    # ── Fast-path: project creator (bypass agent for speed) ───
    if re.search(r'create.*project|build.*project|generate.*project|'
                 r'new.*project|make.*project|build.*app|create.*app', c):
        from brain.project_agent import create_project_async
        from hud.server import send_project_notify
        desc = re.sub(r'(create|build|generate|new|make).*(project|app|tool|system)[:\s]*',
                      '', cmd, flags=re.I).strip()
        if not desc or len(desc) < 6:
            return ('Tell me what to build, Sir. Example: '
                    '"build a Flask API that tracks expenses"')

        def _stream(event, data):
            try:
                from hud.server import socketio
                if event == 'stream_start':
                    socketio.emit('code_stream_start', {
                        'filename': data.get('file', 'unknown'),
                        'file_num': data.get('num', 0),
                        'total':    data.get('total', 0),
                        'lang':     data.get('lang', 'text'),
                    })
                elif event == 'stream_chunk':
                    socketio.emit('code_stream_chunk', {
                        'filename': data.get('file', 'unknown'),
                        'lines':    data.get('chunk', '').split('\n'),
                        'done':     False,
                    })
                elif event == 'stream_end':
                    socketio.emit('code_stream_end', {
                        'filename': data.get('file', 'unknown'),
                        'lines':    data.get('lines', 0),
                    })
            except Exception as _e:
                log.debug(f'stream_fn emit error: {_e}')

        return create_project_async(desc,
                                    notify_fn=send_project_notify,
                                    stream_fn=_stream)

    # ── Evidence-grounded factual answers ─────────────────────
    # Factual queries must never be answered from model memory alone. The
    # verification pipeline retrieves real sources and only exposes supported
    # claims; creative and operational requests continue to the agent below.
    from brain.verification import get_pipeline
    verification = get_pipeline().run(cmd)
    if verification.requires_verification:
        from utils.memory import Memory
        mem = Memory()
        mem.save("user", cmd, origin="USER_PROVIDED", verification_status="UNVERIFIED")
        mem.save("assistant", verification.answer, origin="VERIFIED_PIPELINE",
                 verification_status="VERIFIED" if verification.valid else "UNVERIFIED",
                 sources=[source.url for source in verification.sources])
        return verification.answer

    # ── Full agentic ReAct loop (everything else) ──────────────
    from brain.agent import run_agent
    from utils.memory import Memory
    mem  = Memory()
    hist = mem.get_history()
    mem.save("user", cmd, origin="USER_PROVIDED", verification_status="NOT_APPLICABLE")

    def _agent_notify(msg: str):
        """Forward agent step updates to the HUD project panel."""
        try:
            from hud.server import send_project_notify
            send_project_notify(msg)
        except Exception:
            pass
        if notify_fn:
            try:
                notify_fn(msg)
            except Exception:
                pass

    response = run_agent(cmd, history=hist, notify_fn=_agent_notify)
    mem.save("assistant", response, origin="GENERATED", verification_status="NOT_APPLICABLE")
    return response


def _node_status(node: str) -> str:
    import psutil
    from datetime import timedelta
    if node == "EDITH-CORE":
        cpu  = psutil.cpu_percent(interval=None)
        ram  = psutil.virtual_memory()
        boot = datetime.fromtimestamp(psutil.boot_time())
        up   = timedelta(seconds=int((datetime.now()-boot).total_seconds()))
        return (f"🟢 EDITH-CORE — ACTIVE\n"
                f"CPU: {cpu:.1f}%  |  RAM: {ram.percent:.1f}% used\n"
                f"Uptime: {up}")
    if node == "CLOUD-CHAIN":
        from brain.ai_engine import get_active_model
        info = get_active_model()
        cooldowns = info.get("cooldowns", {})
        lines = [f"{'🔴' if down else '🟢'} {name}" for name, down in cooldowns.items()]
        return ("🟢 CLOUD-CHAIN — ACTIVE\n"
                f"First available: {info.get('active')}\n"
                f"Chain order: {' -> '.join(info.get('chain', []))}\n" +
                "\n".join(lines))
    if node == "MEMORY-BANK":
        m = psutil.virtual_memory()
        return (f"🟢 MEMORY-BANK — SYNCED\n"
                f"RAM: {m.percent:.1f}% ({m.used//1024**3:.1f}GB / "
                f"{m.total//1024**3:.1f}GB)\n"
                f"Available: {m.available//1024**3:.1f}GB")
    if node == "CLOUD-RELAY":
        from brain.ai_engine import is_gemini_available, get_active_model, GEMINI_MODEL
        info = get_active_model()
        avail = is_gemini_available()
        return (f"{'🟢' if avail else '🔴'} CLOUD-RELAY — "
                f"{'ONLINE' if avail else 'OFFLINE'}\n"
                f"Model: {GEMINI_MODEL}\nAPI key: {info.get('gemini_api_key','unknown')}")
    return f"⚠️ Unknown network node: {node}"
