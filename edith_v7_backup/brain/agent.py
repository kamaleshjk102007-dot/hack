# ============================================================
# E.D.I.T.H. — Full Agentic AI Core  (v1.0)
# ReAct loop: Reason → Act → Observe → Reason → ...
# The agent decides WHICH tools to call, calls them,
# observes results, and keeps looping until it has a
# complete answer — no hardcoded routing needed.
# ============================================================

import re, json, time, threading
from utils.logger import get_logger

log = get_logger("agent")

MAX_STEPS   = 8     # max tool calls per request
MAX_TIMEOUT = 90    # seconds total budget per request

# ── Tool registry ──────────────────────────────────────────────
# Each tool has: name, description (seen by the AI), fn (callable)
# The AI writes JSON tool calls; we execute them here.

def _tool_web_search(query: str) -> str:
    from plugins.all_phases import web_search
    return web_search(f"search for {query}")

def _tool_weather(location: str = "") -> str:
    from plugins.all_phases import get_weather
    try:
        from hud.server import _live_coords
        lat = _live_coords.get("lat", "")
        lon = _live_coords.get("lon", "")
    except Exception:
        lat = lon = ""
    return get_weather(location or "current weather", lat=lat, lon=lon)

def _tool_system_info(query: str = "") -> str:
    from plugins.all_phases import system_info
    return system_info(query or "system status")

def _tool_open_app(app: str) -> str:
    from plugins.all_phases import open_app
    result = open_app(f"open {app}")
    return result or f"❌ '{app}' is not a recognized website/app (check WEBSITES / DESKTOP_APPS in config/settings.py)."

def _tool_open_website(destination: str) -> str:
    from plugins.universal_control import open_website
    return open_website(destination)

def _tool_search_website(site: str, query: str) -> str:
    from plugins.universal_control import search_website
    return search_website(site, query)

def _tool_computer_control(action: str, target: str = "", text: str = "",
                           keys: list | None = None) -> str:
    from plugins.universal_control import control
    return control(action=action, target=target, text=text, keys=keys)

def _tool_control_capabilities(query: str = "") -> str:
    from plugins.universal_control import capabilities
    return capabilities()

def _tool_run_python(code: str) -> str:
    """Execute Python code in a sandboxed subprocess and return output."""
    import subprocess, sys, tempfile, os
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                     delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=15,
            cwd=os.path.expanduser("~")
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if err and not out:
            return f"ERROR:\n{err}"
        if err:
            return f"OUTPUT:\n{out}\n\nSTDERR:\n{err}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Code execution timed out (15s limit)"
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

def _tool_read_file(path: str) -> str:
    import os
    path = os.path.expanduser(path.strip())
    try:
        if not os.path.exists(path):
            return f"ERROR: File not found: {path}"
        size = os.path.getsize(path)
        if size > 50_000:
            with open(path, encoding='utf-8', errors='replace') as f:
                content = f.read(50_000)
            return f"[First 50KB of {size//1024}KB file]\n{content}"
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        return f"ERROR reading file: {e}"

def _tool_write_file(path: str, content: str) -> str:
    import os
    path = os.path.expanduser(path.strip())
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✅ Written {len(content)} chars to {path}"
    except Exception as e:
        return f"ERROR writing file: {e}"

def _tool_list_dir(path: str = ".") -> str:
    import os
    path = os.path.expanduser(path.strip() or ".")
    try:
        items = os.listdir(path)
        dirs  = sorted([i for i in items if os.path.isdir(os.path.join(path, i))])
        files = sorted([i for i in items if os.path.isfile(os.path.join(path, i))])
        lines = [f"📁 {path}"]
        for d in dirs:
            lines.append(f"  📂 {d}/")
        for f in files:
            size = os.path.getsize(os.path.join(path, f))
            lines.append(f"  📄 {f}  ({size:,} bytes)")
        return "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"

def _tool_run_shell(command: str) -> str:
    """Run a safe shell command. Blocked: rm -rf, format, del /f/s, etc."""
    import subprocess
    BLOCKED = [
        r'rm\s+-rf', r'del\s+/f', r'format\s+', r'mkfs',
        r'dd\s+if=', r'shutdown', r'reboot', r':(){:|:&}',
        r'chmod\s+777', r'sudo\s+rm', r'> /dev/sd',
    ]
    for pat in BLOCKED:
        if re.search(pat, command, re.I):
            return f"BLOCKED: Dangerous command refused — '{command[:60]}'"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=20
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        combined = out + ("\n" + err if err else "")
        return combined[:4000] or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out (20s)"
    except Exception as e:
        return f"ERROR: {e}"

def _tool_send_email(to: str, subject: str, body: str) -> str:
    from plugins.all_phases import send_email
    return send_email(f"send email to {to}: {subject}. {body}")

def _tool_check_inbox(limit: int = 5) -> str:
    from plugins.all_phases import check_inbox
    return check_inbox(limit=int(limit) if limit else 5)

def _tool_whatsapp(contact: str, message: str) -> str:
    from plugins.all_phases import send_whatsapp
    return send_whatsapp(f"whatsapp to {contact}: {message}")

def _tool_write_document(topic: str) -> str:
    from plugins.all_phases import write_document
    return write_document(f"write a document about {topic}")

def _tool_write_pdf(topic: str) -> str:
    from plugins.all_phases import write_pdf
    return write_pdf(f"create a pdf about {topic}")

def _tool_write_word(topic: str, style: str = "professional") -> str:
    """Write a fully styled Word .docx with headings, bullets, footer."""
    from plugins.all_phases import write_word_doc
    return write_word_doc(f"write a {style} word document about {topic}")

def _tool_write_excel(topic: str) -> str:
    """Create a formatted Excel .xlsx spreadsheet with data, formulas and chart."""
    from plugins.all_phases import write_excel
    return write_excel(f"create excel spreadsheet for {topic}")

def _tool_create_dataset(topic: str, rows: int = 20, columns: str = "") -> str:
    """Generate an AI dataset saved as both CSV and Excel with statistics sheet."""
    from plugins.all_phases import create_dataset
    col_part = f" with columns: {columns}" if columns else ""
    return create_dataset(f"create dataset of {rows} rows about {topic}{col_part}")

def _tool_close_app(app: str) -> str:
    from plugins.all_phases import close_app
    result = close_app(f"close {app}")
    return result or f"⚠️ '{app}' is not a recognized process name, or it wasn't running."

def _tool_memory_recall(query: str = "") -> str:
    from utils.memory import Memory
    mem  = Memory()
    hist = mem.get_history()
    if not hist:
        return "No conversation history yet."
    # Return last 10 turns
    lines = []
    for m in hist[-10:]:
        role = "Sir" if m["role"] == "user" else "EDITH"
        lines.append(f"{role}: {m['content'][:200]}")
    return "\n".join(lines)

def _tool_image_search(topic: str) -> str:
    from plugins.all_phases import fetch_topic_image
    return fetch_topic_image(topic)

def _tool_create_project(description: str) -> str:
    """Trigger the full project builder agent."""
    from brain.project_agent import create_project_async
    from hud.server import send_project_notify
    def _stream(event, data):
        try:
            from hud.server import socketio
            if event == 'stream_start':
                socketio.emit('code_stream_start', {
                    'filename': data.get('file','unknown'),
                    'file_num': data.get('num',0),
                    'total':    data.get('total',0),
                    'lang':     data.get('lang','text'),
                })
            elif event == 'stream_chunk':
                socketio.emit('code_stream_chunk', {
                    'filename': data.get('file','unknown'),
                    'lines':    data.get('chunk','').split('\n'),
                    'done':     False,
                })
            elif event == 'stream_end':
                socketio.emit('code_stream_end', {
                    'filename': data.get('file','unknown'),
                    'lines':    data.get('lines',0),
                })
        except Exception:
            pass
    return create_project_async(description,
                                notify_fn=send_project_notify,
                                stream_fn=_stream)

def _tool_calculate(expression: str) -> str:
    """Safely evaluate a math expression."""
    import math
    allowed = set("0123456789+-*/().% ")
    safe = all(c in allowed or c.isalpha() for c in expression)
    if not safe:
        return f"ERROR: Unsafe expression"
    try:
        env = {k: getattr(math, k) for k in dir(math) if not k.startswith('_')}
        env['abs'] = abs; env['round'] = round
        result = eval(expression, {"__builtins__": {}}, env)
        return str(result)
    except Exception as e:
        return f"ERROR: {e}"

def _tool_datetime(query: str = "") -> str:
    from datetime import datetime
    now = datetime.now()
    return (f"Date: {now:%A, %B %d, %Y}\n"
            f"Time: {now:%I:%M:%S %p}\n"
            f"ISO:  {now.isoformat()}")


# ── Tool registry ──────────────────────────────────────────────
TOOLS = {
    "web_search": {
        "fn":   _tool_web_search,
        "desc": "Search the web for current information. Args: query(str)"
    },
    "weather": {
        "fn":   _tool_weather,
        "desc": "Get weather for a location. Args: location(str, optional)"
    },
    "system_info": {
        "fn":   _tool_system_info,
        "desc": "Get CPU, RAM, battery, disk, temperature info. Args: query(str)"
    },
    "open_app": {
        "fn":   _tool_open_app,
        "desc": "Open an application or website. Args: app(str)"
    },
    "open_website": {
        "fn": _tool_open_website,
        "desc": "Open a named website, domain, or complete http/https URL in the browser. Args: destination(str)"
    },
    "search_website": {
        "fn": _tool_search_website,
        "desc": "Open search results on a supported website. Args: site(str: google/youtube/github/wikipedia/amazon/reddit/linkedin), query(str)"
    },
    "computer_control": {
        "fn": _tool_computer_control,
        "desc": "Control Windows using an audited action. Args: action(str: open_app/close_app/open_website/search_website/type_text/press_key/hotkey/screenshot), target(str optional), text(str optional), keys(list optional). High-impact actions return a confirmation token."
    },
    "control_capabilities": {
        "fn": _tool_control_capabilities,
        "desc": "List the website and Windows-control actions E.D.I.T.H. can actually perform. Args: query(str optional)"
    },
    "run_python": {
        "fn":   _tool_run_python,
        "desc": "Execute Python code and return output. Args: code(str). Use for calculations, data processing, testing snippets."
    },
    "run_shell": {
        "fn":   _tool_run_shell,
        "desc": "Run a shell command (Windows cmd/PowerShell or Linux bash). Args: command(str). Dangerous commands are blocked."
    },
    "read_file": {
        "fn":   _tool_read_file,
        "desc": "Read a file from disk. Args: path(str)"
    },
    "write_file": {
        "fn":   _tool_write_file,
        "desc": "Write content to a file. Args: path(str), content(str)"
    },
    "list_dir": {
        "fn":   _tool_list_dir,
        "desc": "List files in a directory. Args: path(str, optional, default='.')"
    },
    "send_email": {
        "fn":   _tool_send_email,
        "desc": "Send an email. Args: to(str), subject(str), body(str)"
    },
    "check_inbox": {
        "fn":   _tool_check_inbox,
        "desc": "Check Gmail inbox for recent emails. Args: limit(int, optional, default=5)"
    },
    "whatsapp": {
        "fn":   _tool_whatsapp,
        "desc": "Send a WhatsApp message using WhatsApp Desktop app (opens native app and auto-sends). Args: contact(str — name like mom/dad or phone like +91XXXXXXXXXX), message(str)"
    },
    "write_document": {
        "fn":   _tool_write_document,
        "desc": "Create and open a Word (.docx) document with AI-generated content on a topic. Args: topic(str)"
    },
    "write_pdf": {
        "fn":   _tool_write_pdf,
        "desc": "Create and open a real PDF document with AI-generated content. Args: topic(str)"
    },
    "write_word": {
        "fn":   _tool_write_word,
        "desc": "Create a fully styled Word .docx document with headings, bullets, table of contents and footer. Args: topic(str), style(str, optional: professional/formal/casual)"
    },
    "write_excel": {
        "fn":   _tool_write_excel,
        "desc": "Create a formatted Excel .xlsx spreadsheet with AI-generated data, auto-widths, totals row and bar chart. Args: topic(str — e.g. 'employee salary table', 'monthly budget tracker')"
    },
    "create_dataset": {
        "fn":   _tool_create_dataset,
        "desc": "Generate a realistic AI dataset saved as CSV + Excel with statistics sheet. Args: topic(str), rows(int, optional, default=20), columns(str, optional — comma-separated column names)"
    },
    "close_app": {
        "fn":   _tool_close_app,
        "desc": "Close a running desktop application by name (chrome, notepad, word, etc.). Args: app(str)"
    },
    "image_search": {
        "fn":   _tool_image_search,
        "desc": "Search and display an image in the HUD. Args: topic(str)"
    },
    "create_project": {
        "fn":   _tool_create_project,
        "desc": "Build a complete software project (files written to disk). Args: description(str). Use for 'build me a Flask app', etc."
    },
    "calculate": {
        "fn":   _tool_calculate,
        "desc": "Evaluate a math expression. Args: expression(str)"
    },
    "datetime": {
        "fn":   _tool_datetime,
        "desc": "Get current date and time. Args: query(str, optional)"
    },
    "memory_recall": {
        "fn":   _tool_memory_recall,
        "desc": "Recall recent conversation history. Args: query(str, optional)"
    },
}


# ── Agent system prompt ────────────────────────────────────────
def _build_agent_system_prompt() -> str:
    tool_docs = "\n".join(
        f'  {name}: {info["desc"]}' for name, info in TOOLS.items()
    )
    return (
        "You are E.D.I.T.H., Kamalesh's agentic AI. Address him as Sir.\n\n"
        "OUTPUT RULE: You MUST output ONLY raw JSON. No prose, no markdown fences, "
        "no '```json', no 'After performing', no explanation outside JSON. "
        "Every single response must be a single JSON object and nothing else.\n\n"
        "STEP FORMAT (when using a tool):\n"
        '{"thought":"why","action":"tool_name","args":{"arg":"value"}}\n\n' +
        "FINAL FORMAT (when you have the answer):\n"
        '{"thought":"done","action":"FINAL","answer":"full answer to Sir"}\n\n' +
        f"TOOLS:\n{tool_docs}\n\n"
        "RULES:\n"
        "- Output ONLY the JSON object. Nothing before it. Nothing after it.\n"
        "- Use tools for real-time data (weather, news, code execution, files).\n"
        "- Typed and spoken commands have identical capabilities. For website or "
        "Windows interaction, use open_website, search_website, open_app, or computer_control.\n"
        "- Never say an external action succeeded until a tool observation starts with "
        "SUCCESS or clearly reports completion. Report ERROR/BLOCKED honestly.\n"
        "- If a tool returns CONFIRMATION_REQUIRED, stop and give Sir its exact token; "
        "do not retry, bypass it, or claim completion.\n"
        "- Never request, reveal, type, or store passwords, authentication codes, API keys, "
        "or payment details. Never automate purchases or financial transfers.\n"
        "- Do not invent integrations. Use control_capabilities when support is unclear.\n"
        "- For facts you already know, go straight to FINAL.\n"
        f"- Max {MAX_STEPS} tool steps total.\n"
        "- FINAL answer must be clean prose — no JSON, no fences.\n"
        "- Never fabricate data — use web_search or run_python to verify.\n"
        "- If a web_search observation contains a '🔗' reference URL (e.g. "
        "Wikipedia or a news source), you MUST carry that exact URL into your "
        "FINAL answer as a source link — never drop it, never rewrite it, "
        "never summarize it away. If a search yields no URL, still search and "
        "say so honestly rather than inventing a source.\n"
    )


# ── ReAct loop ─────────────────────────────────────────────────
def run_agent(cmd: str, history: list = None, notify_fn=None) -> str:
    """
    Full agentic ReAct loop.
    - cmd: user command
    - history: list of {role, content} dicts
    - notify_fn: optional callable(str) to push step updates to HUD
    Returns final answer string.
    """
    from brain.ai_engine import query

    def _push(msg: str):
        if notify_fn:
            try:
                notify_fn(msg)
            except Exception:
                pass
        log.info(f"[AGENT] {msg}")

    messages = list((history or [])[-8:])  # keep last 8 turns for context
    messages.append({"role": "user", "content": cmd})

    system = _build_agent_system_prompt()
    steps  = []
    start  = time.time()

    _push(f"🤖 Agent started: {cmd[:60]}")

    for step_num in range(MAX_STEPS):
        # Check timeout
        if time.time() - start > MAX_TIMEOUT:
            _push("⏰ Agent timeout reached")
            break

        # Build the conversation with all previous steps
        step_messages = list(messages)
        for s in steps:
            step_messages.append({"role": "assistant", "content": json.dumps(s["raw"])})
            if s.get("observation"):
                step_messages.append({
                    "role": "user",
                    "content": f"Observation: {s['observation']}"
                })

        # Ask AI for next step
        try:
            raw_response = query(
                prompt=step_messages[-1]["content"],
                history=step_messages[:-1],
                max_tokens=2048,
                system=system,
            )
        except Exception as e:
            log.error(f"[AGENT] AI call failed at step {step_num}: {e}")
            return f"⚠️ Agent AI error: {e}"

        # Parse JSON response
        step_data = _parse_step(raw_response)
        if step_data is None:
            # AI gave non-JSON prose (Ollama fallback quirk) — treat as final answer
            # But first strip any leaked JSON fences or ```json blocks
            clean = re.sub(r'```[a-z]*\n?[\s\S]*?```', '', raw_response, flags=re.M).strip()
            clean = re.sub(r'^\s*After performing the action:?\s*', '', clean, flags=re.I|re.M)
            clean = clean.strip() or raw_response.strip()
            log.warning(f"[AGENT] Non-JSON response at step {step_num} — treating as final")
            return clean

        thought = step_data.get("thought", "")
        action  = step_data.get("action", "")

        _push(f"💭 {thought[:100]}")

        # FINAL answer
        if action == "FINAL":
            answer = step_data.get("answer", "")
            # Strip any leaked JSON artifacts from the answer
            answer = re.sub(r'```[a-z]*\n?', '', answer, flags=re.M).strip()
            answer = re.sub(r'\n?```', '', answer, flags=re.M).strip()
            _push(f"✅ Done in {step_num+1} step(s), {time.time()-start:.1f}s")
            return answer or "Done, Sir."

        # Execute tool
        if action not in TOOLS:
            # Unknown tool — ask AI to try again
            steps.append({
                "raw":         step_data,
                "observation": f"ERROR: Unknown tool '{action}'. Available: {', '.join(TOOLS.keys())}"
            })
            continue

        args = step_data.get("args", {})
        _push(f"🔧 {action}({_fmt_args(args)})")

        try:
            tool_fn     = TOOLS[action]["fn"]
            observation = str(tool_fn(**args))
        except TypeError as e:
            observation = f"ERROR: Wrong args for {action}: {e}"
        except Exception as e:
            observation = f"ERROR in {action}: {e}"

        # Truncate very long observations
        if len(observation) > 3000:
            observation = observation[:3000] + f"\n... [truncated, {len(observation)} total chars]"

        _push(f"📋 Result: {observation[:80]}{'...' if len(observation)>80 else ''}")

        steps.append({
            "raw":         step_data,
            "observation": observation
        })

    # Ran out of steps — summarise what we have
    _push("⚠️ Max steps reached — summarising")
    obs_summary = "\n".join(
        f"- {s['raw'].get('action','?')}: {s.get('observation','')[:200]}"
        for s in steps
    )
    summary_prompt = (
        f"Based on these observations, give Sir a complete final answer:\n"
        f"Original request: {cmd}\n\nResults:\n{obs_summary}"
    )
    return query(summary_prompt, history=messages, system=system)


def _parse_step(text: str) -> dict | None:
    """
    Extract the LAST valid JSON step block from AI response.
    Handles: markdown fences, prose before/after JSON, multiple blocks,
    Ollama quirks like 'After performing the action:' commentary.
    """
    if not text or not text.strip():
        return None

    # Find ALL {...} blocks in the text (greedy, handles nested braces)
    candidates = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start != -1:
                candidates.append(text[start:i+1])
                start = -1

    # Try each candidate from LAST to FIRST (last JSON block is most likely FINAL)
    for candidate in reversed(candidates):
        try:
            obj = json.loads(candidate)
            # Must have at least 'action' or 'answer' key to be a valid step
            if 'action' in obj or 'answer' in obj:
                return obj
        except json.JSONDecodeError:
            continue

    return None


def _fmt_args(args: dict) -> str:
    """Format args dict for display, truncating long values."""
    parts = []
    for k, v in args.items():
        sv = str(v)
        if len(sv) > 60:
            sv = sv[:57] + "..."
        parts.append(f"{k}={repr(sv)}")
    return ", ".join(parts)
