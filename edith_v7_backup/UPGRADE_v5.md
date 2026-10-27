# EDITH v5 — Claude-Powered Project Creation

## What Changed

### Problem (v4)
- Project creation used `phi3:mini` (Ollama) to write code
- `phi3:mini` is too weak → placeholder code, broken logic, incomplete files
- `MAX_TOKENS=150` was cutting off responses mid-function

### Solution (v5)
- Added `brain/claude_engine.py` — connects to the **Anthropic Claude API**
- Claude writes code files exactly like Claude.ai does: full, working, no TODOs
- `project_agent.py` now auto-selects Claude if `ANTHROPIC_API_KEY` is set
- Falls back to Gemini/Ollama if no Claude key (same behavior as before)

---

## Setup — One Step

Open `.env` and replace this line:
```
ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
```
With your real key from: https://console.anthropic.com

That's it. EDITH will now write code like Claude.ai.

---

## Files Changed

| File | Change |
|------|--------|
| `brain/claude_engine.py` | **NEW** — Claude API engine for code generation |
| `brain/project_agent.py` | **UPGRADED** — uses Claude engine, better prompts, 8192 token limit |
| `.env` | **UPDATED** — added `ANTHROPIC_API_KEY` slot |

---

## How It Works Now

When you say: **"create a Python web scraper that monitors Amazon prices"**

1. **Understand** → Claude analyzes and extracts project structure (JSON)
2. **Blueprint** → Claude designs the file list with descriptions
3. **Scaffold** → creates folders and empty files
4. **Write** → Claude writes each file completely (8192 tokens, no truncation)
5. **Verify** → syntax-checks Python/JSON/JS files
6. **Fix** → if errors found, Claude rewrites the file correctly
7. **Deliver** → saves to `Documents/EDITH_Projects/`, zips, opens folder

The code quality is identical to what you see in Claude.ai artifacts.
