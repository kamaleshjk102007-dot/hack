# ══════════════════════════════════════════════════════════════════
#  E.D.I.T.H. — Project Architect + Build Agent  (v6.0)
#  Phases: REQUIREMENTS → ARCHITECTURE → LAYOUT → DEVELOPMENT
#  Every phase requires explicit user approval before proceeding.
# ══════════════════════════════════════════════════════════════════
import os, json, ast, zipfile, threading, re, subprocess
from pathlib import Path
from datetime import datetime
from utils.logger import get_logger
from brain.ai_engine import query, stream_query

log = get_logger("project_agent")

PROJECTS_DIR   = Path.home() / "Documents" / "EDITH_Projects"
STATE_FILE     = PROJECTS_DIR / "project_state.json"
MAX_FIX_ROUNDS = 3
MAX_FILES      = 40
CODE_TOKENS    = 8192
JSON_TOKENS    = 2048
ARCH_TOKENS    = 4096

# ── Master system prompt (EDITH Project Architect persona) ────────
MASTER_SYSTEM = """You are EDITH, an autonomous Project Architect and Build Agent.
You operate inside the EDITH Project Tab. You ARE the project workspace.

You strictly follow this lifecycle and NEVER skip ahead:
REQUIREMENTS → [USER APPROVAL] → ARCHITECTURE → [USER APPROVAL] → LAYOUT → [USER APPROVAL] → DEVELOPMENT

Hard rules:
- NEVER write implementation code before Architecture AND Layout have both been approved.
- Always use Mermaid code blocks for diagrams (```mermaid ... ```).
- Be concise in status updates; be thorough in plans and architecture.
- If the user's message is casual or a status question, answer it directly.

Current PROJECT MEMORY is provided at the start of each prompt."""

# ── Phase constants ───────────────────────────────────────────────
PHASE_IDLE        = "idle"
PHASE_REQ         = "requirements"
PHASE_REQ_PENDING = "requirements_pending_approval"
PHASE_ARCH        = "architecture"
PHASE_ARCH_PENDING= "architecture_pending_approval"
PHASE_LAYOUT      = "layout"
PHASE_LAYOUT_PENDING = "layout_pending_approval"
PHASE_DEV         = "development"
PHASE_DONE        = "done"

PHASE_LABELS = {
    PHASE_IDLE:         "READY",
    PHASE_REQ:          "ANALYSING",
    PHASE_REQ_PENDING:  "AWAITING APPROVAL",
    PHASE_ARCH:         "DESIGNING",
    PHASE_ARCH_PENDING: "AWAITING APPROVAL",
    PHASE_LAYOUT:       "LAYOUT",
    PHASE_LAYOUT_PENDING:"AWAITING APPROVAL",
    PHASE_DEV:          "BUILDING",
    PHASE_DONE:         "DONE",
}

# ── Pause / Resume state ──────────────────────────────────────────
_pause_event  = threading.Event()
_pause_event.set()
_build_active = False

def pause_build():
    global _build_active
    if _build_active:
        _pause_event.clear()
        return "paused"
    return "not_running"

def resume_build():
    _pause_event.set()
    return "resumed"

def toggle_pause():
    return pause_build() if _pause_event.is_set() else resume_build()

def is_paused():
    return not _pause_event.is_set()

def _check_pause(notify_fn=None):
    if not _pause_event.is_set():
        _notify(notify_fn, "⏸️  Build PAUSED — press Resume to continue...")
        _pause_event.wait()
        _notify(notify_fn, "▶️  Build RESUMED")


# ══════════════════════════════════════════════════════════════════
#  PROJECT STATE — persisted to project_state.json
# ══════════════════════════════════════════════════════════════════

def _default_state():
    return {
        "phase":                PHASE_IDLE,
        "request":              "",
        "requirements":         {},
        "architecture":         {},
        "layout":               {},
        "roadmap":              [],
        "completed_milestones": [],
        "pending_tasks":        [],
        "known_bugs":           [],
        "progress":             0,
        "project_dir":          "",
        "last_updated":         "",
    }

_state_lock = threading.Lock()

def load_state():
    """
    Always returns a dict with every default key present.
    Tolerates: missing file, empty file, truncated/corrupt JSON,
    and JSON that parsed to a non-dict (list/str/number/null) —
    any of which previously caused an uncaught AttributeError
    (e.g. state.get(...) on a non-dict) that bubbled up as a
    bare 500 on routes that didn't wrap the call in try/except.
    """
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    with _state_lock:
        if STATE_FILE.exists():
            try:
                raw = STATE_FILE.read_text(encoding="utf-8")
                if raw.strip():
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        merged = _default_state()
                        merged.update(data)
                        return merged
                    log.warning("project_state.json did not contain an object — resetting")
            except Exception as e:
                log.warning(f"project_state.json unreadable ({e}) — resetting")
        return _default_state()

def save_state(state):
    """Atomic write: write to a temp file then os.replace() so a crash or a
    second thread saving concurrently can never leave a half-written /
    corrupt project_state.json on disk."""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    state["last_updated"] = datetime.now().isoformat()
    with _state_lock:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_FILE)

def reset_state():
    state = _default_state()
    save_state(state)
    return state

def get_phase():
    return load_state().get("phase", PHASE_IDLE)

def get_phase_label():
    return PHASE_LABELS.get(get_phase(), "READY")


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def _notify(fn, msg):
    log.info(msg)
    if fn:
        try:
            fn(f"[PROJECT] {msg}")
        except Exception:
            pass

def _notify_phase(fn, phase):
    _notify(fn, f"__PHASE__{PHASE_LABELS.get(phase, phase)}")

def _build_prompt(state, user_msg, extra=""):
    mem = json.dumps({k: v for k, v in state.items()
                      if k not in ("last_updated",)}, indent=2)
    return (
        f"PROJECT MEMORY:\n{mem}\n\n---\n{MASTER_SYSTEM}\n---\n\n"
        + (f"{extra}\n\n" if extra else "")
        + f"User: {user_msg}"
    )

def _llm(prompt, max_tokens=2048):
    """Plain (non-streaming) LLM call with the master system baked in."""
    return query(prompt, system="", max_tokens=max_tokens)

def _json_llm(prompt):
    system = (
        "You are a software architect. Respond ONLY with valid JSON. "
        "No markdown backticks, no explanation. Start with { end with }."
    )
    for _ in range(3):
        # Stream (not a single blocking call) so the pause button actually
        # works DURING "Understanding request..." / "Blueprint" processing,
        # not just during code-file writing. stream_query checks
        # _pause_event between chunks and blocks there until resumed.
        raw = "".join(stream_query(prompt, system=system, max_tokens=JSON_TOKENS,
                                    pause_event=_pause_event))
        raw = re.sub(r"```json|```", "", raw).strip()
        for i, ch in enumerate(raw):
            if ch in "{[":
                raw = raw[i:]
                break
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}

def _sanitize_files(files):
    clean, seen = [], set()
    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("path", "").strip()
        if not path or path in seen:
            continue
        if any(c in path for c in ("*", "?", "<", ">", "|", "\\")):
            continue
        seen.add(path)
        clean.append({
            "path":        path,
            "description": f.get("description", path),
            "priority":    f.get("priority", 99),
        })
    return clean


# ══════════════════════════════════════════════════════════════════
#  PHASE 1 — REQUIREMENTS ANALYSIS
# ══════════════════════════════════════════════════════════════════

def run_requirements(request, notify_fn=None):
    """
    Analyse request → produce structured summary → wait for approval.
    Returns (response_text, new_state).
    """
    state = load_state()
    state["phase"]   = PHASE_REQ
    state["request"] = request
    save_state(state)
    _notify_phase(notify_fn, PHASE_REQ)

    prompt = _build_prompt(state, request,
        extra=(
            "You are in PHASE 1 — REQUIREMENT ANALYSIS.\n"
            "Produce a structured summary with EXACTLY these sections:\n"
            "## Project Summary\n## Scope\n## Features\n## Risks\n"
            "## Estimated Complexity (Low / Medium / High + why)\n\n"
            "For the Tech Stack and Database/API needs, be specific.\n"
            "End with EXACTLY this line (nothing after it):\n"
            "Please review. Reply 'approve' to continue to architecture, "
            "or tell me what to change."
        )
    )

    response = _llm(prompt, max_tokens=ARCH_TOKENS)

    # Extract a structured JSON summary for state storage
    json_prompt = (
        f"Extract a JSON summary from this requirement analysis.\n"
        f"Analysis:\n{response}\n\n"
        f"Return JSON: {{\"title\":\"...\",\"goals\":[],\"features\":[],"
        f"\"tech_stack\":[],\"complexity\":\"Low|Medium|High\","
        f"\"risks\":[],\"database\":\"...\",\"api\":\"...\"}}"
    )
    req_data = _json_llm(json_prompt)
    req_data["raw"] = response

    state["phase"]        = PHASE_REQ_PENDING
    state["requirements"] = req_data
    save_state(state)
    _notify_phase(notify_fn, PHASE_REQ_PENDING)

    return response, state


# ══════════════════════════════════════════════════════════════════
#  PHASE 2 — ARCHITECTURE DESIGN
# ══════════════════════════════════════════════════════════════════

def run_architecture(notify_fn=None):
    """
    Design system architecture with Mermaid diagrams.
    Returns (response_text, new_state).
    """
    state = load_state()
    if state["phase"] != PHASE_REQ_PENDING:
        return "⚠️ Requirements must be approved before architecture.", state

    state["phase"] = PHASE_ARCH
    save_state(state)
    _notify_phase(notify_fn, PHASE_ARCH)

    prompt = _build_prompt(state, "Generate architecture",
        extra=(
            "You are in PHASE 2 — ARCHITECTURE DESIGN.\n"
            "Produce ALL of the following (never skip any):\n"
            "1. System Architecture overview (2-3 paragraphs)\n"
            "2. Component Diagram (```mermaid flowchart TD ... ```)\n"
            "3. Database Schema / ERD (```mermaid erDiagram ... ```) — or state 'No DB needed'\n"
            "4. API Structure — list endpoints with method + purpose\n"
            "5. Folder Structure — tree format\n"
            "6. User Flow Diagram (```mermaid sequenceDiagram ... ```)\n"
            "7. Development Roadmap — numbered milestones with estimated time\n\n"
            "IMPORTANT: Render ALL diagrams as Mermaid code blocks so they display inline.\n"
            "End with EXACTLY: 'Please review the architecture. Approve, or tell me what to modify.'"
        )
    )

    response = _llm(prompt, max_tokens=ARCH_TOKENS)

    # Extract roadmap items for state
    road_prompt = (
        f"Extract the development roadmap from this architecture as JSON.\n"
        f"Architecture:\n{response[:3000]}\n\n"
        f"Return JSON: {{\"milestones\":[{{\"id\":1,\"name\":\"...\","
        f"\"tasks\":[],\"estimate\":\"1 day\",\"status\":\"pending\"}}]}}"
    )
    road_data = _json_llm(road_prompt)

    state["phase"]        = PHASE_ARCH_PENDING
    state["architecture"] = {"raw": response}
    state["roadmap"]      = road_data.get("milestones", [])
    state["pending_tasks"]= [m["name"] for m in state["roadmap"]]
    save_state(state)
    _notify_phase(notify_fn, PHASE_ARCH_PENDING)

    return response, state


# ══════════════════════════════════════════════════════════════════
#  PHASE 3 — LAYOUT REVIEW
# ══════════════════════════════════════════════════════════════════

def run_layout(notify_fn=None):
    """
    Generate UI wireframes and screen layouts.
    Returns (response_text, new_state).
    """
    state = load_state()
    if state["phase"] != PHASE_ARCH_PENDING:
        return "⚠️ Architecture must be approved before layout.", state

    state["phase"] = PHASE_LAYOUT
    save_state(state)
    _notify_phase(notify_fn, PHASE_LAYOUT)

    prompt = _build_prompt(state, "Generate layout",
        extra=(
            "You are in PHASE 3 — LAYOUT REVIEW.\n"
            "Produce ALL of the following (never skip any):\n"
            "1. Navigation Flow diagram (```mermaid flowchart LR ... ```)\n"
            "2. ASCII wireframe for each main screen/page\n"
            "3. Desktop Layout description\n"
            "4. Mobile Layout description (if applicable)\n"
            "5. A brief purpose paragraph for every screen\n"
            "6. Dashboard Structure (if the project has a dashboard)\n\n"
            "Do NOT write any implementation code.\n"
            "End with EXACTLY: 'Approve the layout, or request modifications.'"
        )
    )

    response = _llm(prompt, max_tokens=ARCH_TOKENS)

    state["phase"]  = PHASE_LAYOUT_PENDING
    state["layout"] = {"raw": response}
    save_state(state)
    _notify_phase(notify_fn, PHASE_LAYOUT_PENDING)

    return response, state


# ══════════════════════════════════════════════════════════════════
#  APPROVE — phase transition gate
# ══════════════════════════════════════════════════════════════════

def approve(notify_fn=None):
    """
    Advance the phase after user approval.
    Returns (response_text, new_state, next_action).
    next_action: 'architecture' | 'layout' | 'development' | None
    """
    state = load_state()
    phase = state["phase"]

    if phase == PHASE_REQ_PENDING:
        msg = (
            "✅ Requirements approved. Generating architecture with diagrams...\n"
            "This may take 15–30 seconds."
        )
        _notify(notify_fn, msg)
        return msg, state, "architecture"

    elif phase == PHASE_ARCH_PENDING:
        msg = (
            "✅ Architecture approved. Generating UI layout and wireframes...\n"
            "This may take 10–20 seconds."
        )
        _notify(notify_fn, msg)
        return msg, state, "layout"

    elif phase == PHASE_LAYOUT_PENDING:
        msg = (
            "✅ Layout approved. Starting development...\n"
            "Watch the PROJECT panel for live progress."
        )
        _notify(notify_fn, msg)
        state["phase"] = PHASE_DEV
        save_state(state)
        return msg, state, "development"

    elif phase == PHASE_IDLE:
        return "💬 Describe your project to get started.", state, None

    else:
        return f"ℹ️ Current phase: {PHASE_LABELS.get(phase, phase)}. Nothing to approve.", state, None


# ══════════════════════════════════════════════════════════════════
#  PHASE 5 — PROJECT CHAT (always available)
# ══════════════════════════════════════════════════════════════════

def project_chat(user_msg, notify_fn=None):
    """
    Answer any project question using PROJECT MEMORY as source of truth.
    Also detects 'approve' and change requests.
    Returns response_text.
    """
    state = load_state()
    msg_lower = user_msg.lower().strip()

    # Detect approval
    if msg_lower in ("approve", "approved", "yes", "ok", "looks good",
                     "proceed", "go ahead", "continue", "next"):
        resp, state, next_action = approve(notify_fn)
        return resp, next_action

    # Detect new project request when idle
    if state["phase"] == PHASE_IDLE:
        resp, state = run_requirements(user_msg, notify_fn)
        return resp, None

    # Re-analyse if user wants changes during pending phases
    if state["phase"] in (PHASE_REQ_PENDING, PHASE_ARCH_PENDING, PHASE_LAYOUT_PENDING):
        if any(w in msg_lower for w in ["change", "modify", "update", "revise",
                                          "edit", "add", "remove", "different"]):
            # Incorporate the feedback and regenerate current phase output
            state["request"] = state["request"] + f"\n\nRevision request: {user_msg}"
            save_state(state)

            if state["phase"] == PHASE_REQ_PENDING:
                state["phase"] = PHASE_IDLE
                save_state(state)
                resp, state = run_requirements(state["request"], notify_fn)
            elif state["phase"] == PHASE_ARCH_PENDING:
                state["phase"] = PHASE_REQ_PENDING
                save_state(state)
                resp, state = run_architecture(notify_fn)
            else:
                state["phase"] = PHASE_ARCH_PENDING
                save_state(state)
                resp, state = run_layout(notify_fn)

            return resp, None

    # General chat — answer from PROJECT MEMORY
    prompt = _build_prompt(state, user_msg,
        extra=(
            "You are in PHASE 5 — PROJECT CHAT MODE.\n"
            "Answer the user's question directly using PROJECT MEMORY.\n"
            "If asked 'what's done', 'what's next', 'show architecture', etc., "
            "answer accurately from memory.\n"
            "If memory doesn't have the answer, say so plainly.\n"
            "Do not fabricate information."
        )
    )
    response = _llm(prompt, max_tokens=1024)
    return response, None


# ══════════════════════════════════════════════════════════════════
#  DEVELOPMENT — runs only after all three phases approved
# ══════════════════════════════════════════════════════════════════

def _detect_language(request):
    r = request.lower()
    if any(w in r for w in ["html", ".html", "webpage", "web page", "website"]):
        return "html"
    if any(w in r for w in ["react", "jsx", "tsx", "next.js", "vue"]):
        return "javascript"
    if any(w in r for w in ["javascript", "js", "node", "express", "typescript"]):
        return "javascript"
    if any(w in r for w in ["python", "flask", "django", "fastapi", "py"]):
        return "python"
    if any(w in r for w in ["button", "click", "form", "page", "counter", "ui"]):
        return "html"
    return "python"

def _detect_entry(lang):
    return {"html": "index.html", "javascript": "index.js"}.get(lang, "main.py")

def _understand(request, notify_fn):
    _notify(notify_fn, "💠 Understanding request...")
    detected_lang  = _detect_language(request)
    detected_entry = _detect_entry(detected_lang)
    state = load_state()

    # Use architecture data if available
    req = state.get("requirements", {})
    tech_stack = req.get("tech_stack", [])
    features   = req.get("features", [])
    tech_stack_json = json.dumps(tech_stack) if tech_stack else '["vanilla"]'

    prompt = (
        f"Analyze this project request and extract structured information.\n"
        f"Request: {request}\n"
        f"Known tech stack: {tech_stack}\n"
        f"Known features: {features}\n"
        f"Language hint: {detected_lang}\n\n"
        f"Return JSON with EXACTLY these keys:\n"
        f'{{"name":"short_snake_case_name","title":"Human Readable Title",'
        f'"type":"cli|web|api|html","language":"{detected_lang}",'
        f'"features":["{features[0] if features else "feat1"}"],"tech_stack":{tech_stack_json},'
        f'"entry_point":"{detected_entry}","description":"one sentence"}}'
    )

    result = _json_llm(prompt)
    result["language"]    = detected_lang
    result["entry_point"] = detected_entry

    if not result.get("name"):
        words = request.lower().split()[:4]
        result["name"] = "_".join(re.sub(r"[^a-z]", "", w) for w in words if w) or "edith_project"
    if not result.get("title"):
        result["title"] = req.get("title", request[:60])
    if not result.get("description"):
        result["description"] = request

    lang  = result["language"].upper()
    _notify(notify_fn, f"🗺  Architecting: {result.get('title')}")
    _notify(notify_fn, f"   Language : {lang}")
    _notify(notify_fn, f"   Stack    : {', '.join(str(s) for s in result.get('tech_stack', [])[:5]) or 'Vanilla'}")
    _notify(notify_fn, f"   Features : {', '.join(str(f) for f in result.get('features', [])[:4]) or 'As requested'}")
    return result

def _blueprint(intent, notify_fn):
    lang  = intent["language"]
    entry = intent["entry_point"]
    state = load_state()
    arch  = state.get("architecture", {}).get("raw", "")

    if lang == "html":
        result = {
            "folders": [],
            "files": [
                {"path": entry,       "description": "Main HTML file with all logic inline", "priority": 1},
                {"path": "README.md", "description": "Usage instructions",                   "priority": 2},
            ],
            "dependencies":    [],
            "run_command":     f"Open {entry} in your browser",
            "install_command": "No installation needed",
        }
    else:
        prompt = (
            f"Design file structure for: {intent.get('title')}\n"
            f"Type:{intent.get('type')} Lang:{lang}\n"
            f"Features:{intent.get('features')}\n"
            + (f"Architecture notes:\n{arch[:1500]}\n" if arch else "")
            + f"\nReturn JSON: {{\"folders\":[],\"files\":["
            f"{{\"path\":\"{entry}\",\"description\":\"Entry point\",\"priority\":1}},"
            f"{{\"path\":\"requirements.txt\",\"description\":\"Dependencies\",\"priority\":2}},"
            f"{{\"path\":\"README.md\",\"description\":\"Docs\",\"priority\":3}}],"
            f"\"dependencies\":[],\"run_command\":\"python {entry}\","
            f"\"install_command\":\"pip install -r requirements.txt\"}}\n"
            f"Rules: max {MAX_FILES} files, every entry MUST have 'path' key."
        )
        result = _json_llm(prompt)
        files  = _sanitize_files(result.get("files", []))
        if not files:
            files = [
                {"path": entry,              "description": "Main script",  "priority": 1},
                {"path": "requirements.txt", "description": "Dependencies", "priority": 2},
                {"path": "README.md",        "description": "Docs",         "priority": 3},
            ]
        result["files"]           = files
        result["run_command"]     = result.get("run_command")     or f"python {entry}"
        result["install_command"] = result.get("install_command") or "pip install -r requirements.txt"
        result.setdefault("folders", [])

    _notify(notify_fn, f"📋 Blueprint: {len(result['files'])} files planned")
    for fi in result["files"][:10]:
        _notify(notify_fn, f"   + {fi['path']}")
    if len(result["files"]) > 10:
        _notify(notify_fn, f"   ... and {len(result['files'])-10} more")
    return result

def _scaffold(project_dir, blueprint, notify_fn):
    files = _sanitize_files(blueprint.get("files", []))
    _notify(notify_fn, f"🔨 Scaffolding {len(files)} files...")
    project_dir.mkdir(parents=True, exist_ok=True)
    for folder in blueprint.get("folders", []):
        if folder and isinstance(folder, str):
            (project_dir / folder).mkdir(parents=True, exist_ok=True)
    for f in files:
        fpath = project_dir / f["path"]
        fpath.parent.mkdir(parents=True, exist_ok=True)
        if not fpath.exists():
            fpath.touch()
    _notify(notify_fn, f"✅ Scaffold complete: {project_dir.name}/")

def _write_file(project_dir, file_info, intent, blueprint,
                written, notify_fn, stream_fn, file_num=0, total=0):
    fpath   = project_dir / file_info["path"]
    num_str = f" ({file_num}/{total})" if total else ""
    lang    = intent.get("language", "python")
    ext     = fpath.suffix.lower()

    _notify(notify_fn, f"✍️  Writing: {file_info['path']}{num_str}")

    if stream_fn:
        stream_fn("stream_start", {
            "file":  file_info["path"],
            "num":   file_num,
            "total": total,
            "lang":  ext.lstrip(".") or lang,
        })

    context_parts = []
    for p, c in list(written.items())[-5:]:
        snippet = c[:1500] + ("\n...[truncated]" if len(c) > 1500 else "")
        context_parts.append(f"=== {p} ===\n{snippet}")
    context = "\n\n".join(context_parts)

    all_files = [f["path"] for f in _sanitize_files(blueprint.get("files", []))]

    if ext in (".html", ".htm"):
        system = (
            "You are writing ONLY this one HTML file. "
            "RULE 1: Start with <!DOCTYPE html> — nothing before it.\n"
            "RULE 2: End with </html> — nothing after it.\n"
            "RULE 3: Embed ALL CSS in <style> tags in <head>.\n"
            "RULE 4: Embed ALL JS in <script> at end of <body>.\n"
            "RULE 5: All features fully working. No TODO. Professional dark theme."
        )
    elif ext == ".md":
        system = (
            "You are writing ONLY this README.md.\n"
            "RULE 1: Start with # (markdown title).\n"
            "RULE 2: Include: Overview, Features, Setup, Usage, Examples.\n"
            "RULE 3: Be specific and accurate about this exact project."
        )
    elif ext == ".txt" and "requirements" in fpath.name:
        system = (
            "You are writing ONLY a requirements.txt.\n"
            "RULE 1: Output ONLY package==version lines, one per line.\n"
            "RULE 2: No comments. Real PyPI package names only."
        )
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        system = (
            f"You are writing ONLY: {file_info['path']}\n"
            "RULE 1: Valid JS/TS only. No markdown.\n"
            "RULE 2: Every function fully implemented. No TODO."
        )
    elif ext == ".py":
        system = (
            f"You are writing ONLY: {file_info['path']}\n"
            "RULE 1: Valid Python only. No markdown.\n"
            "RULE 2: Every function fully implemented. Proper error handling."
        )
    else:
        system = (
            f"You are writing ONLY: {file_info['path']}\n"
            "RULE 1: Raw file content only. No markdown fences, no explanation."
        )

    prompt = (
        f"PROJECT: {intent.get('title')}\n"
        f"DESCRIPTION: {intent.get('description', '')}\n"
        f"LANGUAGE: {lang} | STACK: {', '.join(str(s) for s in intent.get('tech_stack', []))}\n"
        f"FEATURES: {', '.join(str(f) for f in intent.get('features', []))}\n\n"
        f"FILE TO WRITE (ONLY THIS FILE): {file_info['path']}\n"
        f"PURPOSE: {file_info.get('description', '')}\n\n"
        f"Other files (do NOT write their content here): {', '.join(all_files)}\n\n"
        + (f"Already written (import reference only):\n{context}\n\n" if context else "")
        + f"Begin the content of {file_info['path']} now "
        f"(first character of the file immediately, nothing else before it):"
    )

    full_content  = ""
    chunk_buffer  = ""

    for chunk in stream_query(prompt, system=system, max_tokens=CODE_TOKENS,
                               pause_event=_pause_event):
        full_content += chunk
        chunk_buffer += chunk
        if len(chunk_buffer) >= 15:
            if stream_fn:
                stream_fn("stream_chunk", {"file": file_info["path"], "chunk": chunk_buffer})
            chunk_buffer = ""

    if chunk_buffer and stream_fn:
        stream_fn("stream_chunk", {"file": file_info["path"], "chunk": chunk_buffer})

    FENCE_START = re.compile(r"^```[\w]*\n?")
    FENCE_END   = re.compile(r"\n?```$")
    full_content = FENCE_START.sub("", full_content.strip())
    full_content = FENCE_END.sub("", full_content)

    if ext in (".html", ".htm"):
        dt = full_content.find("<!DOCTYPE")
        if dt == -1:
            dt = full_content.find("<html")
        if dt > 0:
            full_content = full_content[dt:]
        end_tag = full_content.rfind("</html>")
        if end_tag != -1:
            full_content = full_content[:end_tag + 7]
    elif ext == ".md":
        lines = full_content.splitlines()
        while lines and (lines[0].strip().startswith("```") or lines[0].strip() == ""):
            lines.pop(0)
        full_content = "\n".join(lines)
    elif ext == ".txt" and "requirements" in fpath.name:
        lines = full_content.splitlines()
        clean = [l.strip() for l in lines
                 if l.strip() and not l.strip().startswith("#")
                 and re.match(r"^[A-Za-z0-9_\-\.]+", l.strip())]
        full_content = "\n".join(clean)

    full_content = full_content.strip()

    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write(full_content)

    if stream_fn:
        stream_fn("stream_end", {
            "file":  file_info["path"],
            "lines": full_content.count("\n") + 1,
            "chars": len(full_content),
        })

    _notify(notify_fn, f"✅ Written: {file_info['path']} "
            f"({len(full_content)} chars, {full_content.count(chr(10))+1} lines)")
    return full_content

def _verify(fpath):
    errors  = []
    content = fpath.read_text(encoding="utf-8", errors="ignore")
    ext     = fpath.suffix.lower()
    if ext == ".py":
        try:
            ast.parse(content)
        except SyntaxError as e:
            errors.append(f"SyntaxError line {e.lineno}: {e.msg}")
    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            errors.append(f"JSONError: {e}")
    elif ext in (".js", ".ts"):
        opens  = content.count("{") + content.count("(") + content.count("[")
        closes = content.count("}") + content.count(")") + content.count("]")
        if abs(opens - closes) > 10:
            errors.append(f"Bracket mismatch: {opens} opens vs {closes} closes")
    return errors

def _fix(fpath, errors, notify_fn, stream_fn):
    _notify(notify_fn, f"🔧 Auto-fixing: {fpath.name} ({errors[0][:60]})")
    content = fpath.read_text(encoding="utf-8", errors="ignore")
    if stream_fn:
        stream_fn("stream_start", {"file": fpath.name, "num": 0, "total": 0,
                                   "lang": fpath.suffix[1:]})
    system = ("You are an expert developer. Fix ALL listed errors. "
              "Return ONLY the complete corrected file. No fences, no explanation.")
    prompt = (f"Fix this file. Errors:\n{chr(10).join(errors)}\n\n"
              f"Code:\n{content[:8000]}\n\nReturn the COMPLETE fixed file:")
    fixed = ""
    buf   = ""
    for chunk in stream_query(prompt, system=system, max_tokens=CODE_TOKENS,
                               pause_event=_pause_event):
        fixed += chunk
        buf   += chunk
        if len(buf) >= 15:
            if stream_fn:
                stream_fn("stream_chunk", {"file": fpath.name, "chunk": buf})
            buf = ""
    if buf and stream_fn:
        stream_fn("stream_chunk", {"file": fpath.name, "chunk": buf})

    FENCE_START = re.compile(r"^```[\w]*\n?")
    FENCE_END   = re.compile(r"\n?```$")
    fixed = FENCE_START.sub("", fixed.strip())
    fixed = FENCE_END.sub("", fixed).strip()
    with open(fpath, "w", encoding="utf-8") as fh:
        fh.write(fixed)
    if stream_fn:
        stream_fn("stream_end", {"file": fpath.name, "lines": fixed.count("\n") + 1})
    return len(_verify(fpath)) == 0

def _deliver(project_dir, intent, blueprint, stats, notify_fn):
    _notify(notify_fn, "📦 Packaging project...")
    zip_path = project_dir.parent / f"{project_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in project_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(project_dir.parent))
    try:
        import sys
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(project_dir)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(project_dir)])
        else:
            subprocess.Popen(["xdg-open", str(project_dir)])
    except Exception:
        pass
    summary = (
        f"✅ PROJECT COMPLETE: {intent.get('title')}\n"
        f"{'─'*50}\n"
        f"📁 Location : {project_dir}\n"
        f"📦 Archive  : {zip_path.name}\n"
        f"⚙️  Stack    : {', '.join(intent.get('tech_stack', [])) or 'Vanilla'}\n"
        f"📄 Files    : {stats['written']} written, {stats['fixed']} auto-fixed\n"
        f"🚀 Run with : {blueprint.get('run_command', 'Open index.html')}\n"
        f"📦 Install  : {blueprint.get('install_command', 'No install needed')}"
    )
    _notify(notify_fn, summary)
    return summary


# ── GATE CHECK — development must only run if phase is approved ──
def _assert_dev_approved():
    state = load_state()
    if state.get("phase") != PHASE_DEV:
        raise RuntimeError(
            f"Development not approved. Current phase: {state.get('phase')}. "
            "Requirements → Architecture → Layout must all be approved first."
        )

def create_project(request, notify_fn=None, stream_fn=None):
    """
    Full build pipeline — only runs if phase==development.
    Called internally after layout approval, NOT directly from user input.
    """
    global _build_active
    _build_active = True
    _pause_event.set()

    try:
        _assert_dev_approved()   # hard gate — cannot be bypassed
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        _check_pause(notify_fn)
        intent    = _understand(request, notify_fn)
        _check_pause(notify_fn)
        blueprint = _blueprint(intent, notify_fn)
        files     = _sanitize_files(blueprint.get("files", []))[:MAX_FILES]

        if not files:
            _notify(notify_fn, "❌ Blueprint returned no valid files.")
            return "❌ Blueprint failed."

        ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = PROJECTS_DIR / f"{intent['name']}_{ts}"

        _check_pause(notify_fn)
        _scaffold(project_dir, blueprint, notify_fn)

        written = {}
        stats   = {"written": 0, "fixed": 0, "errors": 0}
        state   = load_state()
        total   = len(files)

        for file_num, file_info in enumerate(files, 1):
            _check_pause(notify_fn)
            content = _write_file(
                project_dir, file_info, intent, blueprint,
                written, notify_fn, stream_fn, file_num, total
            )
            written[file_info["path"]] = content
            stats["written"] += 1

            fpath  = project_dir / file_info["path"]
            errors = _verify(fpath)
            if not errors:
                _notify(notify_fn, f"🔍 Verified: {file_info['path']} ✅")

            for _ in range(MAX_FIX_ROUNDS):
                if not errors:
                    break
                _check_pause(notify_fn)
                if _fix(fpath, errors, notify_fn, stream_fn):
                    stats["fixed"] += 1
                    errors = []
                else:
                    errors = _verify(fpath)
                    stats["errors"] += 1

            # Update progress in state
            state["progress"] = int((file_num / total) * 100)
            state["completed_milestones"].append(file_info["path"])
            save_state(state)

        result = _deliver(project_dir, intent, blueprint, stats, notify_fn)

        state["phase"]       = PHASE_DONE
        state["project_dir"] = str(project_dir)
        state["progress"]    = 100
        save_state(state)

        return result

    except RuntimeError as e:
        return f"⛔ {e}"
    except Exception as e:
        msg = f"❌ Project creation failed: {e}"
        log.error(msg, exc_info=True)
        _notify(notify_fn, msg)
        return msg
    finally:
        _build_active = False
        _pause_event.set()


def create_project_async(request, notify_fn=None, stream_fn=None):
    # Set this BEFORE spawning the thread, not inside it. Thread creation/
    # scheduling has a small but real delay — if Pause is clicked in that
    # gap (very plausible: the UI's Pause button is enabled the moment the
    # phase flips to 'development', which happens slightly before this even
    # runs), pause_build() would see _build_active still False and silently
    # do nothing. Setting it here closes that window completely.
    global _build_active
    _build_active = True
    _pause_event.set()
    t = threading.Thread(
        target=create_project, args=(request, notify_fn, stream_fn), daemon=True
    )
    t.start()
    return (
        f"🚀 Project build started.\n"
        f"Watch [PROJECT] messages for live progress.\n"
        f"Request: '{request[:80]}'"
    )
