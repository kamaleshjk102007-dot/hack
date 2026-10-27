# ============================================================
# E.D.I.T.H. — Full Agentic AI Core  (v1.0)
# ReAct loop: Reason → Act → Observe → Reason → ...
# The agent decides WHICH tools to call, calls them,
# observes results, and keeps looping until it has a
# complete answer — no hardcoded routing needed.
# ============================================================

import os, sys, re, json, time, threading
from utils.logger import get_logger, redact_secrets

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

_SENSITIVE_FS_PATTERNS = [
    r"(?:^|[/\\])(?:system32|syswow64)\b",
    r"^[a-zA-Z]:[/\\]windows\b",
    r"^/(?:etc|bin|sbin|usr/bin|var/run|dev|proc|sys)\b",
    r"(?:/etc/(?:passwd|shadow|sudoers))",
    r"(?:^|[/\\])(?:\.ssh|\.aws|\.gnupg)\b",
    r"(?:^|[/\\])(?:id_rsa|id_ed25519|id_dsa|\.env)\b",
]

def _is_sensitive_path(path_str: str) -> bool:
    if not path_str or not isinstance(path_str, str):
        return False
    normalized = os.path.normpath(os.path.expanduser(path_str)).replace("\\", "/")
    for pat in _SENSITIVE_FS_PATTERNS:
        if re.search(pat, normalized, re.I):
            return True
    return False

def _sanitize_subprocess_env() -> dict:
    env = os.environ.copy()
    for k in list(env.keys()):
        if any(term in k.upper() for term in ("API_KEY", "SECRET", "TOKEN", "PASSWORD")):
            env.pop(k, None)
    return env


def _tool_run_python(code: str) -> str:
    """Execute Python code in a sandboxed subprocess and return output."""
    from utils.logger import redact_secrets
    import subprocess, sys, tempfile, os
    # Block patterns that could damage the system regardless of the
    # shell-level allowlist already enforced by _tool_run_shell.
    _PYTHON_DANGEROUS = [
        r"\bos\.system\s*\(",
        r"\bsubprocess\.(run|Popen|call|check_output)\s*\(",
        r"\bshutil\.(rmtree|move|copy)\s*\(",
        r"\bos\.(remove|unlink|rmdir|rename)\s*\(",
        r"\bopen\s*\([^,)]+[,)][^)]*['\"]w",  # file write
        r"\b(shutdown|reboot|format|mkfs)\b",
        r"\b__import__\s*\(",
        r"\beval\s*\(\s*(?!str|repr)",         # bare eval (allow eval(str(x)))
        r"\bexec\s*\(",
    ]
    for pat in _PYTHON_DANGEROUS:
        if re.search(pat, code, re.I):
            pat_repr = repr(pat)[:60]
            return (f"BLOCKED: Code contains a potentially dangerous pattern "
                    f"(matched: {pat_repr}). Use run_shell for filesystem/process ops.")
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py',
                                     delete=False, encoding='utf-8') as f:
        f.write(code)
        tmp = f.name
    try:
        clean_env = _sanitize_subprocess_env()
        result = subprocess.run(
            [sys.executable, tmp],
            capture_output=True, text=True, timeout=15,
            cwd=os.path.expanduser("~"),
            env=clean_env
        )
        out = redact_secrets(result.stdout.strip())
        err = redact_secrets(result.stderr.strip())
        if err and not out:
            return f"ERROR:\n{err}"
        if err:
            return f"OUTPUT:\n{out}\n\nSTDERR:\n{err}"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Code execution timed out (15s limit)"
    except Exception as e:
        return redact_secrets(f"ERROR: {e}")
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

def _tool_read_file(path: str) -> str:
    from utils.logger import redact_secrets
    import os
    raw = (path or "").strip()
    if not raw:
        return "ERROR: Empty path"
    norm = os.path.normpath(raw)
    if norm.startswith("..") or "/.." in raw or "\\.." in raw:
        return "BLOCKED: Path traversal outside permitted root is forbidden."
    expanded = os.path.expanduser(raw)
    if _is_sensitive_path(expanded):
        return "BLOCKED: Access to sensitive file or system directory is forbidden."
    try:
        if not os.path.exists(expanded):
            return f"ERROR: File not found: {raw}"
        size = os.path.getsize(expanded)
        if size > 50_000:
            with open(expanded, encoding='utf-8', errors='replace') as f:
                content = f.read(50_000)
            return redact_secrets(f"[First 50KB of {size//1024}KB file]\n{content}")
        with open(expanded, encoding='utf-8', errors='replace') as f:
            return redact_secrets(f.read())
    except Exception as e:
        return redact_secrets(f"ERROR reading file: {e}")

def _tool_write_file(path: str, content: str) -> str:
    from utils.logger import redact_secrets
    import os
    raw = (path or "").strip()
    if not raw:
        return "ERROR: Empty path"
    norm = os.path.normpath(raw)
    if norm.startswith("..") or "/.." in raw or "\\.." in raw:
        return "BLOCKED: Path traversal outside permitted root is forbidden."
    expanded = os.path.expanduser(raw)
    if _is_sensitive_path(expanded):
        return "BLOCKED: Writing to sensitive file or system directory is forbidden."
    try:
        os.makedirs(os.path.dirname(os.path.abspath(expanded)), exist_ok=True)
        with open(expanded, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✅ Written {len(content)} chars to {raw}"
    except Exception as e:
        return redact_secrets(f"ERROR writing file: {e}")

def _tool_list_dir(path: str = ".") -> str:
    from utils.logger import redact_secrets
    import os
    raw = (path or ".").strip() or "."
    norm = os.path.normpath(raw)
    if norm.startswith("..") or "/.." in raw or "\\.." in raw:
        return "BLOCKED: Path traversal outside permitted directory is forbidden."
    expanded = os.path.expanduser(raw)
    if _is_sensitive_path(expanded):
        return "BLOCKED: Access to sensitive system directory is forbidden."
    try:
        items = os.listdir(expanded)
        dirs  = sorted([i for i in items if os.path.isdir(os.path.join(expanded, i))])
        files = sorted([i for i in items if os.path.isfile(os.path.join(expanded, i))])
        lines = [f"📁 {raw}"]
        for d in dirs:
            lines.append(f"  📂 {d}/")
        for f in files:
            size = os.path.getsize(os.path.join(expanded, f))
            lines.append(f"  📄 {f}  ({size:,} bytes)")
        return redact_secrets("\n".join(lines))
    except Exception as e:
        return redact_secrets(f"ERROR: {e}")

SAFE_SHELL_COMMANDS = {
    "git", "python", "python3", "pip", "pip3", "node", "npm", "npx",
    "dir", "ls", "echo", "cat", "type", "findstr", "grep", "mkdir",
    "cd", "pwd", "date", "time", "curl", "whoami", "hostname", "tasklist",
    "tree", "pytest", "unittest"
}

DANGEROUS_SHELL_PATTERNS = [
    r"\b(rm\s+-rf|del\s+/[fqs]|format\s+|mkfs|fdisk|diskpart)\b",
    r"\b(rmdir\s+/[sq]|rd\s+/[sq]|erase\s+|remove-item\s+-recurse)\b",
    r"\b(shutdown|reboot|restart-computer|stop-computer)\b",
    r"\b(chmod\s+777|chown|sudo\s+|takeown|icacls\s+.*grant)\b",
    r"\b(reg\s+(add|delete)|vssadmin|bcdedit|net\s+user|net\s+localgroup)\b",
    r"\b(powershell|pwsh|cmd\.exe|wscript|cscript|mshta|rundll32)\b",
    r"\b(iex|invoke-expression|invoke-webrequest|iwr|downloadstring)\b",
    r"\b(certutil|bitsadmin)\b",
    r"(:(){:|:&})",
    r"(>\s*/dev/sd|dd\s+if=)",
    r"(\.\.[/\\]\.\.[/\\]\.\.)",
    r"(&&|\|\||;)",
]

CHAINING_TOKENS = {"&", "&&", "|", "||", ";", ">", ">>", "<", "<<", "^"}

def _tool_run_shell(command: str, cwd: str = None) -> str:
    """Run an allowlisted, safe shell command with structured validation."""
    from utils.logger import redact_secrets
    import subprocess, shlex, sys, os
    cmd_clean = (command or "").strip()
    if not cmd_clean:
        return "ERROR: Empty command"

    if any(c in cmd_clean for c in ("\n", "\r", "\0", "`")):
        return "BLOCKED: Command contains disallowed control characters or command substitution."
    if re.search(r"\$\([^\)]*\)", cmd_clean):
        return "BLOCKED: Subshell command substitution $(...) is forbidden."

    for pat in DANGEROUS_SHELL_PATTERNS:
        if re.search(pat, cmd_clean, re.I):
            return f"BLOCKED: Dangerous command refused — '{cmd_clean[:60]}'"

    try:
        tokens = shlex.split(cmd_clean, posix=False)
        tokens = [
            t[1:-1] if len(t) >= 2 and ((t[0] == '"' and t[-1] == '"') or (t[0] == "'" and t[-1] == "'")) else t
            for t in tokens
        ]
    except Exception as e:
        return redact_secrets(f"ERROR: Malformed command line: {e}")

    if not tokens:
        return "ERROR: Empty command"

    if any(t in CHAINING_TOKENS for t in tokens):
        return "BLOCKED: Command chaining or redirection is forbidden."

    base_cmd = os.path.basename(tokens[0]).lower()
    if base_cmd.endswith(".exe"):
        base_cmd = base_cmd[:-4]

    if base_cmd in {"python", "python3", "py"}:
        tokens[0] = sys.executable
        base_cmd = "python"

    if base_cmd not in SAFE_SHELL_COMMANDS:
        return (
            f"BLOCKED: Command '{base_cmd}' is not in the safe command allowlist. "
            f"Permitted tools include: {', '.join(sorted(SAFE_SHELL_COMMANDS))}"
        )

    # Executable-specific security checks
    if base_cmd == "python":
        for idx, tok in enumerate(tokens[1:], 1):
            if tok in ("-c", "/c") and idx + 1 < len(tokens):
                py_code = tokens[idx + 1]
                for pat in [
                    r"\bos\.system\s*\(",
                    r"\bsubprocess\.(run|Popen|call|check_output)\s*\(",
                    r"\bshutil\.(rmtree|move|copy)\s*\(",
                    r"\bos\.(remove|unlink|rmdir|rename)\s*\(",
                    r"\b(shutdown|reboot|format|mkfs)\b",
                    r"\b__import__\s*\(",
                    r"\beval\s*\(\s*(?!str|repr)",
                    r"\bexec\s*\(",
                ]:
                    if re.search(pat, py_code, re.I):
                        pat_repr = repr(pat)[:60]
                        return f"BLOCKED: Python command contains potentially dangerous pattern ({pat_repr})."
    elif base_cmd in {"node", "npm", "npx"}:
        for idx, tok in enumerate(tokens[1:], 1):
            if tok in ("-e", "--eval") and idx + 1 < len(tokens):
                node_code = tokens[idx + 1]
                if re.search(r"\b(child_process|execSync|spawnSync|exec|spawn|fs\.rm|fs\.unlink)\b", node_code, re.I):
                    return "BLOCKED: Node evaluation contains potentially dangerous process or filesystem call."
    elif base_cmd == "git":
        for tok in tokens[1:]:
            if re.search(r"^-(?:c\s*core\.pager|c\s*credential)", tok, re.I):
                return "BLOCKED: Git pager/credential override is refused."
    elif base_cmd == "curl":
        for tok in tokens[1:]:
            if tok.lower().startswith("file://") or tok in {"-o", "-O", "--output", "-T", "--upload-file"}:
                return "BLOCKED: Dangerous curl arguments (file:// or file output) are refused."

    # Validate argument tokens
    for idx, tok in enumerate(tokens[1:], 1):
        is_code_arg = (base_cmd == "python" and idx > 1 and tokens[idx - 1] in ("-c", "/c"))
        if not is_code_arg:
            if any(c in tok for c in ("&", "|", ";", ">", "<", "`", "\n", "\r", "^")):
                return "BLOCKED: Metacharacters inside arguments are forbidden."
        if _is_sensitive_path(tok):
            return "BLOCKED: Access to system directory is forbidden."
        norm_tok = os.path.normpath(tok)
        if norm_tok.startswith("..") or "/.." in tok or "\\.." in tok:
            return "BLOCKED: Path traversal outside permitted directory is forbidden."

    try:
        if sys.platform == "win32" and base_cmd in {"dir", "type", "echo", "mkdir", "cd", "date", "time"}:
            exec_args = ["cmd.exe", "/c"] + tokens
        else:
            exec_args = tokens

        clean_env = _sanitize_subprocess_env()
        target_cwd = os.path.expanduser("~")
        if cwd:
            resolved_cwd = os.path.abspath(cwd)
            if os.path.isdir(resolved_cwd) and not _is_sensitive_path(resolved_cwd):
                target_cwd = resolved_cwd
        result = subprocess.run(
            exec_args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=15,
            cwd=target_cwd,
            env=clean_env
        )
        out = redact_secrets(result.stdout.strip())
        err = redact_secrets(result.stderr.strip())
        combined = out + ("\n" + err if err else "")
        return combined[:4000] or "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out (15s limit)"
    except Exception as e:
        return redact_secrets(f"ERROR: {e}")

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
    """Trigger the project builder requirements analysis. Never bypasses user approval."""
    from brain.project_agent import run_requirements, load_state, PHASE_IDLE
    from hud.server import send_project_notify
    state = load_state()
    if state.get("phase") != PHASE_IDLE:
        return (f"A project is already active in phase '{state.get('phase')}'. "
                f"Please review or reset the current project first.")
    resp, new_state = run_requirements(description, notify_fn=send_project_notify)
    return (
        f"Project requirements analysis initiated for: {description}\n\n"
        f"{resp}\n\n"
        "Status: Requirements analysis complete. Explicit user approval is required before Architecture, Layout, or Development can proceed."
    )


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

def _tool_browser_defense_summary(query: str = "") -> str:
    from plugins.browser_defense import get_browser_defense_summary
    return get_browser_defense_summary(query)

def _tool_browser_defense_events(limit: int = 5) -> str:
    from plugins.browser_defense import get_browser_defense_events
    return get_browser_defense_events(limit=int(limit) if limit else 5)


# ── Tool registry ──────────────────────────────────────────────
TOOLS = {
    "browser_defense_summary": {
        "fn":   _tool_browser_defense_summary,
        "desc": "Get real-time status and threat summary from the EDITH/SentinelX cyber defense browser extension: blocked threats, active declarativeNetRequest rules, link radar findings, self-healing status, and AI threat investigations. Args: query(str, optional)"
    },
    "browser_defense_events": {
        "fn":   _tool_browser_defense_events,
        "desc": "Get recent security events and intercepted threats from the browser cyber defense extension. Args: limit(int, optional, default=5)"
    },
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
                task_type="agent",
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
