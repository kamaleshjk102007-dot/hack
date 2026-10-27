# SYNTRAX AI — Gemma 4 Threat Investigation Gateway

> **Secure AI Security Co-Pilot Gateway for Chrome Extension (Manifest V3)**  
> Built with zero external dependencies using Node.js built-ins (`http`, `https`).

---

## 🔒 Security Architecture

1. **Secret Isolation**:
   The `GEMINI_API_KEY` is hosted **strictly inside this local backend gateway**. It is **never** embedded or exposed inside the Chrome extension client, HTML, JavaScript, or public repositories.
2. **Untrusted Data Isolation**:
   Inspected URL strings, pathnames, and heuristic findings from the extension are wrapped within strict isolation boundaries (`<<<UNTRUSTED_METADATA>>> ... <<<END_UNTRUSTED_METADATA>>>`) to neutralize prompt injection attacks.
3. **Deterministic Policy Supremacy**:
   The AI model operates strictly as an **advisory intelligence co-pilot**. It cannot create or mutate browser blocking rules, nor can it override the extension's local zero-trust policy engine.
4. **Honest Operational Accounting**:
   When the gateway is stopped or an API key is unconfigured, the extension reports an honest offline/unavailable state. No mock or hallucinated AI responses are ever fabricated.

---

## 🚀 Setup & Startup Instructions

### Step 1: Configure Environment

Copy `.env.example` to `.env`:

```bash
cd sentinelx-ai/backend
copy .env.example .env
```

Open `.env` and set your key:
```ini
GEMINI_API_KEY=your_actual_google_ai_studio_key_here
GEMMA_MODEL_ID=gemma-4-31b-it
PORT=8787
```

### Step 2: Start the Gateway

```bash
node server.js
```

Or pass the key inline without creating a file:
```bash
set GEMINI_API_KEY=your_key_here && node server.js
```

### Step 3: Verify Health

Visit or probe the health endpoint:
```bash
curl http://127.0.0.1:8787/api/health
```

Expected Response:
```json
{
  "status": "ok",
  "service": "SYNTRAX AI — Gemma 4 Security Gateway",
  "version": "1.0.0",
  "modelId": "gemma-4-31b-it",
  "configured": true
}
```

---

## 📡 API Endpoints

### 1. `GET /api/health`
Checks gateway readiness and API key configuration status.

### 2. `POST /api/investigate`
Accepts a sanitized security payload:
```json
{
  "target": {
    "domain": "phishing-bank.xyz",
    "protocol": "https:",
    "normalizedUri": "https://phishing-bank.xyz/auth"
  },
  "threatContext": {
    "initialRiskLevel": "HIGH_RISK",
    "heuristicRiskScore": 85,
    "observedIndicators": [
      {
        "category": "BRAND_IMPERSONATION",
        "severity": "HIGH",
        "evidence": "Deceptive keyword found on unverified domain."
      }
    ]
  }
}
```

Returns validated JSON:
```json
{
  "success": true,
  "genuineAi": true,
  "investigation": {
    "modelId": "gemma-4-31b-it",
    "investigationSummary": "High confidence credential harvesting attempt targeting financial services.",
    "suspiciousIndicators": ["Brand keyword on unverified TLD", "High-abuse registrar"],
    "evidenceExplanation": "The domain combines high-value financial keywords with unverified infrastructure.",
    "uncertaintyAndLimitations": "Lexical structural analysis only; runtime payload execution not observed.",
    "recommendedNextStep": "BLOCK",
    "uncertaintyScore": 0.12,
    "investigationStatus": "GENUINE_AI_VERIFIED"
  }
}
```
