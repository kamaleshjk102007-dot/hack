# ============================================================
# E.D.I.T.H. — AI Brain  (v6.0 — CLOUD MULTI-PROVIDER, no Ollama)
# CHAIN: Groq -> Mistral -> Gemini Flash -> Gemini Pro -> OpenRouter
# See brain/cloud_router.py for the full failover chain.
# STREAMING: yields tokens live for real-time code display
# ============================================================

import time, threading, requests, json
from config.settings import (
    GOOGLE_API_KEY, GEMINI_MODEL, GEMINI_PRO_MODEL, GEMINI_API_URL,
    GROQ_API_KEY, GROQ_MODEL_CODE, TEMPERATURE,
)
from utils.logger import get_logger

log = get_logger("ai")

CHAT_MAX_TOKENS = 3072
CODE_MAX_TOKENS = 8192

# Direct Gemini/Groq calls in this module need their own pooled session.
# cloud_router has a similarly named private session, but importing it here
# would tightly couple these modules and make their initialization order
# fragile.  The missing definition previously made every streaming request
# fail immediately with NameError and unnecessarily fall back to another
# provider.
_SHARED_HTTP_SESSION = requests.Session()
_SHARED_HTTP_SESSION.trust_env = False
_adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
_SHARED_HTTP_SESSION.mount("https://", _adapter)
_SHARED_HTTP_SESSION.mount("http://", _adapter)

SYSTEM_PROMPT = (
    "You are E.D.I.T.H. (Even Dead I'm The Hero), Kamalesh's advanced AI assistant. "
    "Be concise, professional, and subtly witty like JARVIS. Never break character.\n\n"
    "OWNER: Your owner is KAMALESH. Always address him as 'Sir'.\n\n"
    "LANGUAGE: Default is English only — do NOT add a Tamil (or any other "
    "language) translation unless THIS specific message explicitly asks for "
    "it. This applies even if earlier replies in this same conversation were "
    "bilingual or in another language — do not pattern-match off previous "
    "turns; judge ONLY the current message. When Sir does ask for Tamil (or "
    "another language) in a message, reply fully in that language for that "
    "reply. If he asks for Tamil specifically and also wants English kept, "
    "format it as:\n"
    "<English answer>\n"
    "--- தமிழ் ---\n"
    "<Tamil translation>\n"
    "Otherwise — meaning almost every message — just answer in plain English "
    "with no translation section at all. Never refuse a language request.\n\n"
    "STYLE: Short precise answers unless detail is requested. No filler phrases.\n\n"
    "IMAGES: If Sir asks to see a picture/photo/image of something (e.g. 'show me "
    "image of lion', 'show mountain image'), DO NOT respond with text about it — "
    "that request is handled by the image search system BEFORE reaching you. "
    "If you somehow receive such a request, reply ONLY with: "
    "[ROUTE:image_search] and nothing else. Never say 'displaying', 'showing', "
    "or pretend to show an image yourself.\n\n"
    "MAPS: You still cannot render an interactive map yourself, and you do not know "
    "real URLs for specific map listings — never invent or guess a link (e.g. a "
    "fake maps.google.com or bing.com/maps URL). If Sir asks to see a place or "
    "satellite view, tell him to use the GEOLOCATION panel in the HUD, or simply "
    "say something like 'show me <place> on the map' and the satellite map will "
    "update automatically — do not list external websites or fabricated links.\n\n"
    "AGENT METHODOLOGY: For any non-trivial request, reason in this order before "
    "answering (skip the visible steps for simple/quick questions — use this for "
    "real tasks: debugging, building something, multi-part requests, research, "
    "decisions with tradeoffs):\n"
    "1. UNDERSTAND — restate the actual goal in one line; ask a clarifying "
    "question ONLY if truly ambiguous, otherwise proceed on the most reasonable "
    "interpretation.\n"
    "2. THINK — consider the real approach(es) and pick the best one; note real "
    "tradeoffs if more than one is reasonable.\n"
    "3. PLAN — briefly list the concrete steps before doing them, for anything "
    "with more than one step.\n"
    "4. ACT — do the work directly: write the actual code/report/email/doc/"
    "answer. Never describe what you would do instead of doing it.\n"
    "5. VERIFY — before finishing, check your own output for correctness, "
    "completeness, and obvious mistakes; fix what you find.\n"
    "6. IMPROVE — if there's a clearly better approach Sir didn't ask for, say "
    "so briefly at the end. Don't pad good answers with unnecessary suggestions.\n\n"
    "REASONING RULES: Never guess facts or invent information — say what you "
    "don't know. Don't skip steps in multi-step tasks. Don't ignore errors — "
    "surface them and explain the fix. For code: write clean, modular code with "
    "real error handling, and call out anything risky or non-obvious.\n\n"
    "HONEST CAPABILITY LIMITS: You are a text-chat assistant integrated into this "
    "HUD with a SPECIFIC, real toolset — not a general computer-using agent. You "
    "actually have: web search, weather lookup, email send/check, system stats, "
    "real image search/display, the satellite map, a project-builder that "
    "writes code files to disk, AND a live frontend preview panel that renders "
    "HTML/CSS/JS you produce directly in the HUD.\n\n"
    "FRONTEND / UI BUILDS: When Sir asks you to build, create, or design any UI "
    "component, webpage, form, chart, dashboard, animation, or any frontend element "
    "— respond with complete, self-contained HTML/CSS/JS inside a SINGLE fenced "
    "code block marked as ```html. Include ALL styles inside a <style> tag and all "
    "scripts inside <script> tags within the same file. Do NOT split code across "
    "multiple blocks. Only use external dependencies from cdnjs.cloudflare.com if "
    "needed. Make output visually polished with a dark-themed aesthetic by default. "
    "The HUD will automatically detect the code block and show a live '👁 Preview' "
    "button — so always produce complete runnable HTML so Sir can preview instantly.\n\n"
    "ITERATION: When Sir says things like 'make the button blue', 'add a dark mode "
    "toggle', 'change the font' — always output the FULL updated HTML again in a "
    "single ```html block so the preview panel refreshes with the complete updated "
    "component. Never output partial diffs.\n\n"
    "You do NOT have: GitHub access, database access, or the ability to act on "
    "real websites or accounts. If Sir asks for something outside this real toolset, "
    "say so plainly and do the closest real thing you can instead."
)

_lock = threading.Lock()



# ── Gemini — normal (non-streaming) ──────────────────────────────

def _gemini_chat(messages, max_tokens=CHAT_MAX_TOKENS, system=None):
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY not set in .env")

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "system_instruction": {"parts": [{"text": system or SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": max_tokens},
    }

    session = _SHARED_HTTP_SESSION
    url  = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent?key={GOOGLE_API_KEY}"
    resp = session.post(url, json=payload, timeout=120)

    if resp.status_code == 429: raise _QuotaError(f"Gemini 429: {resp.text[:100]}")
    if resp.status_code == 503: raise _QuotaError(f"Gemini 503: {resp.text[:100]}")
    if resp.status_code == 400:
        b = resp.text
        if any(k in b.lower() for k in ("quota","limit","billing")):
            raise _QuotaError(f"Gemini quota: {b[:120]}")
        raise RuntimeError(f"Gemini 400: {b[:200]}")
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text: return text
        raise RuntimeError("Gemini empty response")
    except (KeyError, IndexError):
        finish = data.get("candidates", [{}])[0].get("finishReason", "")
        if finish in ("SAFETY","RECITATION"):
            raise RuntimeError(f"Gemini blocked: {finish}")
        raise RuntimeError(f"Unexpected Gemini structure: {data}")


# ── Gemini — STREAMING ────────────────────────────────────────────

def _gemini_stream(messages, max_tokens=CODE_MAX_TOKENS, system=None):
    """
    Generator that yields text chunks from Gemini as they arrive.
    Uses streamGenerateContent endpoint with Server-Sent Events.
    """
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY not set in .env")

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "system_instruction": {"parts": [{"text": system or SYSTEM_PROMPT}]},
        "contents": contents,
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": max_tokens},
    }

    session = _SHARED_HTTP_SESSION
    url = (f"{GEMINI_API_URL}/{GEMINI_MODEL}:streamGenerateContent"
           f"?alt=sse&key={GOOGLE_API_KEY}")

    with session.post(url, json=payload, stream=True, timeout=180) as resp:
        if resp.status_code == 429: raise _QuotaError(f"Gemini 429")
        if resp.status_code == 503: raise _QuotaError(f"Gemini 503")
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini stream HTTP {resp.status_code}: {resp.text[:200]}")

        buffer = ""
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if raw_line.startswith("data:"):
                raw_line = raw_line[5:].strip()
            if raw_line in ("[DONE]", ""):
                continue
            try:
                chunk = json.loads(raw_line)
                text  = (chunk.get("candidates", [{}])[0]
                              .get("content", {})
                              .get("parts", [{}])[0]
                              .get("text", ""))
                if text:
                    yield text
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


# ── Groq — STREAMING (used as first choice for stream_query) ──────

def _groq_stream(messages, max_tokens=CODE_MAX_TOKENS, system=None):
    """Generator that yields text chunks from Groq as they arrive."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    session = _SHARED_HTTP_SESSION
    payload = {
        "model": GROQ_MODEL_CODE,
        "messages": [{"role": "system", "content": system or SYSTEM_PROMPT}] + messages,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
        "stream": True,
    }
    # gpt-oss models are reasoning models: without this, Groq can leak the
    # model's internal "thinking" (e.g. "The user asks... according to
    # policy...") straight into the streamed `content` deltas, appearing
    # glued onto — or duplicated with — the real answer. "hidden" keeps
    # reasoning tokens out of content entirely instead of merging them in.
    if "gpt-oss" in GROQ_MODEL_CODE:
        payload["reasoning_effort"] = "low"
        payload["reasoning_format"] = "hidden"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    with session.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=payload, headers=headers, stream=True, timeout=60,
    ) as resp:
        if resp.status_code == 429:
            raise RuntimeError(f"Groq rate limited: {resp.text[:100]}")
        if resp.status_code != 200:
            raise RuntimeError(f"Groq stream HTTP {resp.status_code}")
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw or not raw.startswith("data: "):
                continue
            data_str = raw[len("data: "):]
            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta_obj = chunk["choices"][0]["delta"]
                # Belt-and-suspenders: even with reasoning_format="hidden",
                # a reasoning-only delta can occasionally still arrive
                # under a "reasoning" key instead of "content" — never
                # forward that to the chat window.
                if "reasoning" in delta_obj and not delta_obj.get("content"):
                    continue
                delta = delta_obj.get("content", "")
                if delta:
                    yield delta
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


class _QuotaError(Exception):
    """Raised when Gemini specifically hits a quota/rate-limit (used by query_vision)."""
    pass


# ── Public: normal query ──────────────────────────────────────────

def query(prompt, history=None, max_tokens=CHAT_MAX_TOKENS, system=None, task_type=None):
    """
    Classifies the request by task type (code/project/search/agent/
    safety/vision) and routes through that task's cloud priority chain
    with automatic failover. See brain/cloud_router.py for the chain
    definitions and per-provider cooldown/retry logic. No local
    inference (no Ollama) is used anywhere in this build.
    """
    from brain.cloud_router import chat_completion, classify_task
    if task_type is None:
        task_type = classify_task(prompt)
    messages = list((history or [])[-10:])
    messages.append({"role": "user", "content": prompt})

    try:
        response, provider = chat_completion(
            messages, system=system or SYSTEM_PROMPT, max_tokens=max_tokens, task_type=task_type
        )
        log.info(f"[AI] task={task_type} provider={provider} ✅ ({len(response)} chars)")
        return response
    except RuntimeError as e:
        log.error(f"[AI] All providers for task={task_type} failed: {e}")
        return (f"⚠️ All available cloud models for {task_type} are currently "
                f"rate-limited or unavailable, Sir. Please try again shortly.")


# ── Gemini — VISION (multimodal: image + text) ────────────────────

def _gemini_vision(prompt, image_b64, mime_type, max_tokens=CHAT_MAX_TOKENS, system=None):
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY not set in .env")

    payload = {
        "system_instruction": {"parts": [{"text": system or SYSTEM_PROMPT}]},
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}},
            ],
        }],
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": max_tokens},
    }

    session = _SHARED_HTTP_SESSION
    url  = f"{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent?key={GOOGLE_API_KEY}"
    resp = session.post(url, json=payload, timeout=120)

    if resp.status_code == 429: raise _QuotaError(f"Gemini 429: {resp.text[:100]}")
    if resp.status_code == 503: raise _QuotaError(f"Gemini 503: {resp.text[:100]}")
    if resp.status_code == 400:
        b = resp.text
        if any(k in b.lower() for k in ("quota","limit","billing")):
            raise _QuotaError(f"Gemini quota: {b[:120]}")
        raise RuntimeError(f"Gemini 400: {b[:200]}")
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text: return text
        raise RuntimeError("Gemini empty response")
    except (KeyError, IndexError):
        finish = data.get("candidates", [{}])[0].get("finishReason", "")
        if finish in ("SAFETY","RECITATION"):
            raise RuntimeError(f"Gemini blocked: {finish}")
        raise RuntimeError(f"Unexpected Gemini structure: {data}")


def query_vision(prompt, image_b64, mime_type, max_tokens=CHAT_MAX_TOKENS, system=None):
    """
    Image + text prompt (real pixel analysis via Gemini's multimodal
    endpoint). Groq's Llama 4 Scout also supports vision and can be
    added as a second provider here later; for now Gemini is the sole
    vision path, so if it's rate-limited we say so plainly rather than
    silently failing.
    """
    if GOOGLE_API_KEY:
        try:
            response = _gemini_vision(prompt, image_b64, mime_type, max_tokens=max_tokens, system=system)
            log.info(f"[AI] Gemini Vision ✅ ({len(response)} chars)")
            return response
        except _QuotaError as e:
            log.warning(f"[AI] Gemini Vision quota: {e}")
            return ("⚠️ Gemini vision quota hit, Sir — image analysis is "
                    "unavailable until it resets (usually a few minutes).")
        except Exception as e:
            log.error(f"[AI] Gemini Vision error: {e}")
            return f"⚠️ Image analysis failed, Sir: {e}"

    return "⚠️ Gemini is unavailable (no API key set), Sir — I can't analyze image content right now."


# ── Public: STREAMING query ───────────────────────────────────────

def stream_query(prompt, system=None, max_tokens=CODE_MAX_TOKENS, pause_event=None):
    """
    Generator that yields text chunks in real time.
    pause_event: a threading.Event — if cleared, stream pauses between chunks.
    Tries Groq stream first, then Gemini stream, then falls back to the
    full non-streaming cloud chain (Mistral/Gemini Pro/OpenRouter),
    yielding the complete response as one chunk if streaming isn't
    available from those providers. No local inference (no Ollama).
    """
    from brain.cloud_router import chat_completion, _on_cooldown, _set_cooldown
    messages = [{"role": "user", "content": prompt}]

    def _record_stream_usage(provider, output_chars):
        """Make successful streamed replies visible in the usage HUD."""
        from brain.cloud_router import record_external_usage
        # Streaming APIs do not consistently provide final token metadata.
        estimated_tokens = max(1, (len(prompt) + output_chars + 3) // 4)
        record_external_usage(provider, estimated_tokens, task_type="code")

    def _yield_with_pause(source):
        for chunk in source:
            if pause_event is not None and not pause_event.is_set():
                log.info("[AI] stream paused — waiting for resume...")
                pause_event.wait()
                log.info("[AI] stream resumed")
            yield chunk

    # 1) Try Groq streaming
    if GROQ_API_KEY and not _on_cooldown("groq"):
        try:
            total = 0
            for chunk in _yield_with_pause(
                    _groq_stream(messages, max_tokens=max_tokens, system=system)):
                total += len(chunk)
                yield chunk
            _record_stream_usage("groq", total)
            log.info(f"[AI] Groq stream ✅ ({total} chars)")
            return
        except Exception as e:
            log.warning(f"[AI] Groq stream failed — trying Gemini. {e}")
            _set_cooldown("groq")

    # 2) Try Gemini streaming
    if GOOGLE_API_KEY:
        try:
            total = 0
            for chunk in _yield_with_pause(
                    _gemini_stream(messages, max_tokens=max_tokens, system=system)):
                total += len(chunk)
                yield chunk
            _record_stream_usage("gemini", total)
            log.info(f"[AI] Gemini stream ✅ ({total} chars)")
            return
        except Exception as e:
            log.warning(f"[AI] Gemini stream failed — trying full cloud chain. {e}")

    # 3) Fall back to the full non-streaming chain (Mistral / Gemini Pro / OpenRouter)
    try:
        response, provider = chat_completion(
            messages, system=system or SYSTEM_PROMPT, max_tokens=max_tokens
        )
        log.info(f"[AI] Fallback chain ✅ via {provider} ({len(response)} chars)")
        yield response
    except RuntimeError as e:
        log.error(f"[AI] All cloud providers failed: {e}")
        yield ("⚠️ All available cloud models are currently rate-limited "
               "or unavailable, Sir. Please try again shortly.")


# ── Status helpers ────────────────────────────────────────────────

# ── Status helpers ────────────────────────────────────────────────

def get_active_model(task_type="agent"):
    """
    Returns the cloud task-routing status for a given task type (default
    "agent") — which provider would be tried first, and which providers
    (if any) are currently cooling down after a rate limit. This is a
    100% cloud, multi-provider build: there is no Ollama / local
    inference fallback anywhere in the chain.
    """
    from brain.cloud_router import get_chain_status, _CHAINS, _on_cooldown_label
    chain = _CHAINS.get(task_type, _CHAINS["agent"])
    chain_labels = [label for label, _ in chain]
    first_available = next((label for label in chain_labels if not _on_cooldown_label(label)), None)
    status = get_chain_status()
    return {
        "task_type":       task_type,
        "active":          first_available or "none (all on cooldown)",
        "fallback":        " -> ".join(chain_labels),
        "chain":           chain_labels,
        "cooldowns":       status,
        "gemini_active":   GOOGLE_API_KEY is not None and bool(GOOGLE_API_KEY) and not _on_cooldown_label("gemini"),
        "gemini_api_key":  "set" if GOOGLE_API_KEY else "missing",
        "groq_api_key":    "set" if GROQ_API_KEY else "missing",
    }


def is_gemini_available():
    return bool(GOOGLE_API_KEY)


def is_groq_available():
    return bool(GROQ_API_KEY)
