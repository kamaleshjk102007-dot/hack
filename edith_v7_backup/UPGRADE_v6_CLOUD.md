# E.D.I.T.H. — Cloud-Only Multi-Provider Upgrade

## What changed

This build removes the Gemini-primary / Ollama-fallback architecture and
replaces it with a full cloud multi-provider failover chain. **No local
inference, no Ollama dependency anywhere.**

### New file: `brain/cloud_router.py`
Implements the priority chain for text/code/agent tasks:

```
1. Groq        — GPT OSS 120B   (minutes-tier reset)
2. Mistral     — Codestral      (minutes-tier reset)
3. Gemini      — 2.5 Flash      (minutes-tier reset)
4. Gemini      — 2.5 Pro        (daily-tier, 50 RPD — used last)
5. OpenRouter  — free router    (daily-tier overflow)
```

On a 429 / rate-limit / timeout / error, that provider is put on a
cooldown timer and the chain automatically moves to the next one for
the *same* request — no manual intervention, no asking the user what
to do. Cooldowns clear themselves automatically (minutes-tier: ~90s,
daily-tier: much longer), matching how these free tiers actually
reset.

### Modified files

- **`brain/ai_engine.py`** — `query()` and `stream_query()` now route
  through `cloud_router.chat_completion()` instead of Gemini→Ollama.
  Streaming tries Groq first, then Gemini, then falls back to the full
  chain (returned as one chunk if a non-streaming provider answers).
  `query_vision()` still uses Gemini (only provider currently wired
  for multimodal input here — Groq's Llama 4 Scout also supports
  vision and can be added as a second vision provider later).

- **`config/settings.py`** — added `GROQ_API_KEY`, `MISTRAL_API_KEY`,
  `OPENROUTER_API_KEY`, `HF_API_KEY`, `KLING_API_KEY`, and the
  associated model-name env vars. Old `OLLAMA_URL` / `OLLAMA_MODEL`
  are kept as harmless inert placeholders so nothing crashes on
  import, but they are not used by the cloud chain.

- **`brain/router.py`** — the `EDITH network node: CLOUD-CHAIN` status
  command now reports live cooldown state per provider, replacing the
  old `OLLAMA-API` node.

- **`brain/self_healing.py`** — the watchdog no longer tries to
  "restart Ollama"; it now reports which cloud providers are
  currently cooling down (informational only — they self-recover).

- **`main.py`** — boot banner and `check_engines()` now show the full
  cloud chain and Groq/Gemini key status instead of a primary/fallback
  pair.

### New file: `.env.example`
A clean template with the new variable names (`GROQ_API_KEY`,
`MISTRAL_API_KEY`, `OPENROUTER_API_KEY`, `HF_API_KEY`,
`KLING_API_KEY`, plus renamed `EDITH_TEMPERATURE` / `EDITH_MAX_TOKENS`
— the old `EDITH_OLLAMA_*` names are gone).

## What you need to do

1. **Copy `.env.example` to `.env`** (or merge the new variable names
   into your existing `.env`) and fill in your own keys:
   ```
   GOOGLE_API_KEY=
   GROQ_API_KEY=
   MISTRAL_API_KEY=
   OPENROUTER_API_KEY=
   HF_API_KEY=
   KLING_API_KEY=
   ```
2. **If any of these keys were ever shared outside your own machine**
   (pasted into a chat, screenshotted, committed to a public repo),
   rotate them at the provider dashboard before using this build.
3. Run `pip install -r requirements.txt` (no new dependencies were
   added — everything uses the `requests` library already in the
   project).
4. Start normally: `python main.py` (or `run.bat` on Windows).

## Not yet wired up (future work, not done in this pass)

- **Image generation** (Hugging Face FLUX/SDXL, Gemini image-out,
  Pollinations) — `HF_API_KEY` / `KLING_API_KEY` are read into
  settings but there's no plugin yet that calls them. Same goes for
  Veo 3.1 / Kling video generation.
- **Speech-to-Text / Text-to-Speech via Groq** (Whisper, Orpheus) —
  not yet wired; the project currently uses `pyttsx3` for TTS.
- **Task classification** — the chain currently treats every text
  request the same way (one priority order). A classifier step (code
  vs. project vs. search vs. agent) to pick *different* chain orders
  per task type, as discussed, is not implemented in this pass.

Happy to wire up any of the above next — just say which one.
