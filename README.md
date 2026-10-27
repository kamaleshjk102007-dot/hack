# 🛡️ E.D.I.T.H. AI & SentinelX Cyber Defense Platform

> **Next-Generation Autonomous Browser Cyber Defense, Multi-Engine Threat Intelligence (VirusTotal v3 + Google Gemma 4), DeclarativeNetRequest Packet Containment, and Biometric HUD Command Center.**

[![Manifest V3](https://img.shields.io/badge/Chrome%20Extension-Manifest%20V3-blue.svg)](https://developer.chrome.com/docs/extensions/mv3/intro/)
[![VirusTotal v3](https://img.shields.io/badge/Threat%20Intelligence-VirusTotal%20v3-0052cc.svg)](https://developers.virustotal.com/reference/overview)
[![Google Gemma 4](https://img.shields.io/badge/AI%20Advisory-Gemma%204%20LLM-00e5ff.svg)](https://ai.google.dev/)
[![Tests](https://img.shields.io/badge/Tests-317%20Passing-brightgreen.svg)](file:///web/test-extension.js)
[![Python](https://img.shields.io/badge/EDITH%20Core-Python%203.10+-yellow.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-purple.svg)](#license)

---

## 📑 Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Architectural Blueprint](#2-architectural-blueprint)
- [3. The 8-Stage Cyber Defense Pipeline](#3-the-8-stage-cyber-defense-pipeline)
- [4. Core Platform Components](#4-core-platform-components)
  - [4.1 SentinelX AI Extension (Manifest V3)](#41-sentinelx-ai-extension-manifest-v3)
  - [4.2 VirusTotal API v3 Threat Intelligence Engine](#42-virustotal-api-v3-threat-intelligence-engine)
  - [4.3 Local Gemma 4 AI Gateway](#43-local-gemma-4-ai-gateway)
  - [4.4 E.D.I.T.H. AI Core & Cybersecurity HUD](#44-edith-ai-core--cybersecurity-hud)
- [5. Security, Privacy & Zero-Trust Invariants](#5-security-privacy--zero-trust-invariants)
- [6. Directory Structure](#6-directory-structure)
- [7. Setup & Installation](#7-setup--installation)
- [8. Automated Test Suite & Verification](#8-automated-test-suite--verification)
- [9. Operational Verification](#9-operational-verification)
- [10. License & Ethics](#10-license--ethics)

---

## 1. Executive Summary

The **EDITH AI & SentinelX Cyber Defense Platform** unites an autonomous, multi-modal desktop AI assistant (**E.D.I.T.H.**) with an enterprise-grade zero-trust browser security engine (**SentinelX AI**).

Unlike superficial extensions that merely act as cosmetic interfaces, SentinelX and EDITH operate a deep, verifiable defensive fabric:
- **Autonomous Zero-Trust Heuristics**: Evaluates Punycode homoglyphs, numerical IP hosts, userinfo credential spoofing, high-abuse TLDs, and path entropy offline in sub-milliseconds.
- **VirusTotal API v3 Telemetry**: Integrates on-demand multi-scanner URL intelligence with standard RFC 4648 Base64URL encoding, bounded caching, and automated rate-limit backoff.
- **Google Gemma 4 AI Gateway**: Leverages local/cloud Gemma 4 models inside prompt-isolated boundaries for complex linguistic and infrastructure threat investigation.
- **Kernel-Level Packet Containment**: Uses Chrome's `declarativeNetRequest` engine to quarantine hostile domains before a single HTTP request packet traverses the network stack.
- **Idempotent Self-Healing**: Automatically scans and restores corrupted or bypassed DeclarativeNetRequest dynamic rules.
- **EDITH Executive HUD Integration**: Real-time bi-directional telemetry streaming directly into EDITH's cyberpunk Heads-Up Display and conversational ReAct router.

---

## 2. Architectural Blueprint

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                         GOOGLE CHROME BROWSER                          │
 │                                                                        │
 │   ┌────────────────────────┐            ┌──────────────────────────┐   │
 │   │      Active Webpage    │            │  SentinelX MV3 Extension │   │
 │   │  (Links, DOM, Forms)   │            │  (Popup, Warning, SW)    │   │
 │   └───────────┬────────────┘            └─────────────┬────────────┘   │
 └───────────────┼───────────────────────────────────────┼────────────────┘
                 │ DOM Radar / Nav Events                │ DeclarativeNetRequest
                 ▼                                       ▼ Dynamic Packet Quarantine
 ┌────────────────────────────────────────────────────────────────────────┐
 │                     SENTINELX SECURITY SERVICE WORKER                  │
 │                                                                        │
 │   [Stage 1: Zero-Trust Heuristics] ──► [Stage 2: Deterministic Policy] │
 │                      │                                                 │
 └──────────────────────┼─────────────────────────────────────────────────┘
                        ▼ Local Gateway Dispatch
 ┌────────────────────────────────────────────────────────────────────────┐
 │                  LOCAL SECURITY GATEWAY (PORT 8787)                    │
 │                                                                        │
 │   ┌──────────────────────────────┐    ┌────────────────────────────┐   │
 │   │  VirusTotal v3 Intelligence  │    │     Google Gemma 4 AI      │   │
 │   │   - Base64URL Encoder        │    │   - Prompt Injection Guard │   │
 │   │   - Sensitive Token Stripper │    │   - Advisory Model Parser  │   │
 │   │   - 30-min Bounded Cache     │    │   - Concurrency Limiter    │   │
 │   │   - 429 Cooldown Guard       │    │   - Uncertainty Scoring    │   │
 │   └──────────────┬───────────────┘    └─────────────┬──────────────┘   │
 └──────────────────┼──────────────────────────────────┼──────────────────┘
                    ▼                                  ▼
         ┌─────────────────────┐            ┌─────────────────────┐
         │   VirusTotal API    │            │  Google Gemini /    │
         │     Endpoints       │            │  Gemma 4 Endpoints  │
         └─────────────────────┘            └─────────────────────┘
                    ▲                                  ▲
                    └──────────────────┬───────────────┘
                                       │ Real-time Sync & Briefings
 ┌─────────────────────────────────────┴──────────────────────────────────┐
 │                      E.D.I.T.H. AI CORE (PYTHON)                       │
 │                                                                        │
 │   - browser_defense.py Plugin        - HUD Flask Telemetry Server      │
 │   - Multi-Modal ReAct Agent          - Biometric Pattern Authentication│
 │   - NEXUS Task Automation Engine     - Self-Healing Python Watchdog    │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The 8-Stage Cyber Defense Pipeline

Every inspected URL traverses a strict, non-bypassable 8-stage sequence:

```
  1. DETECT       Extract URL target from navigations, links, buttons, forms, or user input.
     ↓
  2. HEURISTICS   Evaluate lexical/structural signals offline (Punycode, raw IPs, userinfo, entropy).
     ↓
  3. VIRUSTOTAL   (On-Demand) Strip sensitive tokens, check bounded cache, query VirusTotal v3 URL report.
     ↓
  4. GEMMA 4      (Optional) Dispatch isolated metadata to Gemma 4 for contextual reasoning.
     ↓
  5. POLICY       Centralized deterministic engine decides action (BLOCK, WARN, ALLOW, MONITOR).
     ↓
  6. CONTAIN      Enforce Chrome declarativeNetRequest dynamic rule quarantine; redirect tab to warning.
     ↓
  7. REPAIR       Self-healing engine verifies active DNR rule tables and restores missing rules.
     ↓
  8. AUDIT        Persist sanitized incident telemetry to EventStore and synchronize with EDITH HUD.
```

---

## 4. Core Platform Components

### 4.1 SentinelX AI Extension (Manifest V3)
Located in `web/sentinelx-ai/extension/`:
- **`manifest.json`**: Strict MV3 configuration requesting only necessary permissions (`declarativeNetRequest`, `storage`, `activeTab`, `tabs`, `webNavigation`).
- **`background/service-worker.js`**: Core brain executing the deterministic policy engine, DeclarativeNetRequest rule injection, navigation interception, and telemetry synchronization.
- **`content/link-scanner.js`**: High-performance in-page DOM radar utilizing `MutationObserver` to inspect up to 500 links, hidden menu anchors, forms, and executable downloads without lagging the page.
- **`popup/`**: Dark navy and electric-cyan Operations Center with live telemetry dials, Link Radar breakdowns, Gemma 4 triggers, and the **VirusTotal Intel** control module.
- **`warning/`**: Interstitial cyber barrier preventing drive-by payload downloads when high-risk destinations are navigated to.

### 4.2 VirusTotal API v3 Threat Intelligence Engine
Located in `web/sentinelx-ai/backend/virustotal.js`:
- **Protocol & Target Sanitization**: Strictly allows `http:` and `https:`. Automatically strips credentials (`user:pass@`) and sensitive query parameters (`token`, `session_id`, `api_key`, `auth`, `password`).
- **Private Host Defense**: Blocks queries for `localhost`, `127.0.0.1`, `[::1]`, RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and internal TLDs (`.local`, `.internal`).
- **Standard Base64URL Encoding**: Calculates URL identifiers using RFC 4648 URL-safe Base64 without `=` padding (`Buffer.from(url).toString('base64url')`).
- **Key Isolation**: Sends keys strictly through the `x-apikey` HTTP header. Zero key exposure to client JS, browser logs, or HTTP responses.
- **Bounded In-Memory Cache**: LRU-style cache storing up to 500 entries with a 30-minute TTL to minimize API consumption.
- **HTTP 429 Cooldown**: Automatically triggers a 60-second backoff upon quota exhaustion to prevent endpoint spamming.
- **Distinct Verdict Mapping**: Explicitly categorizes results into `malicious`, `suspicious`, `clean/no detections`, `unknown`, `unavailable`, and `error`.

### 4.3 Local Gemma 4 AI Gateway
Located in `web/sentinelx-ai/backend/server.js`:
- **Zero-Dependency Express Server**: Exposes `/api/investigate`, `/api/reputation/url`, `/api/health`, `/api/events`, and `/api/summary` on `http://127.0.0.1:8787`.
- **Origin Authorization**: Restricts requests strictly to authorized `chrome-extension://` IDs and `localhost`.
- **Prompt Injection Defense**: Encapsulates untrusted web metadata inside `<<<UNTRUSTED_METADATA>>>` boundaries with explicit model constraints.
- **Concurrency Limiting**: Limits concurrent AI inferences to 5 to prevent resource exhaustion.

### 4.4 E.D.I.T.H. AI Core & Cybersecurity HUD
Located in `edith_v7_fixed/`:
- **`plugins/browser_defense.py`**: Queries the SentinelX gateway or fallback event storage to generate executive cyber defense briefings.
- **`hud/`**: Cyberpunk interface providing live maps, telemetry graphs, and interactive terminal controls.
- **`security/pattern_lock.py`**: Visual grid-based biometric pattern authentication safeguarding EDITH commands.
- **`brain/router.py`**: Intent-matching system directing user queries like *"what threats were blocked"* or *"show browser defense summary"* straight to the defense engine.

---

## 5. Security, Privacy & Zero-Trust Invariants

| Principle | Implementation |
| :--- | :--- |
| **Zero-Trust Precedence** | **A clean or unknown VirusTotal or Gemma 4 verdict CANNOT override a mandatory local heuristic block.** Deterministic zero-trust policies always hold authority over third-party advisory telemetry. |
| **Absence of Proof ≠ Proof of Safety** | An empty or unrecorded VirusTotal detection (`stats.harmless > 0` or `stats.undetected > 0`) is labeled `clean/no detections`, never as absolute proof of safety. |
| **Credential & Token Stripping** | All embedded userinfo (`http://admin:pass@host`) and sensitive parameters (`?token=secret&session_id=123`) are stripped *before* calculating URL hashes or sending external API lookups. |
| **Private Infrastructure Exclusion** | Localhost, loopback addresses, internal company subnets, and home router IPs are never transmitted to VirusTotal or external LLMs. |
| **API Key Secrecy** | `VT_API_KEY` and `GEMINI_API_KEY` are stored strictly in local server `.env` files. They are excluded from browser responses, client JavaScript, and GitHub via `.gitignore`. |
| **Submodule-Free Packaging** | All source repositories are directly tracked to guarantee reliable, complete deployments without broken gitlinks. |

---

## 6. Directory Structure

```text
EDITH_v7_Optimized/
├── .gitignore                               # Comprehensive exclusion rules (secrets, logs, caches)
├── README.md                                # Master documentation (this file)
│
├── web/                                     # Web Applications & Browser Defense Suite
│   ├── sentinelx-ai/                        # SentinelX Cyber Defense Platform Root
│   │   ├── backend/                         # Node.js Security Gateway & Threat Intelligence API
│   │   │   ├── server.js                    # Gateway server, origin validator, endpoint router
│   │   │   ├── virustotal.js                # VirusTotal v3 engine, URL sanitizer, LRU cache
│   │   │   ├── .env.example                 # Environment variable templates (VT_API_KEY, GEMINI_API_KEY)
│   │   │   └── package.json                 # Backend dependencies (express, cors, dotenv)
│   │   │
│   │   ├── dashboard/                       # React 18 + Vite Operations Dashboard
│   │   │   ├── src/                         # React views, components, and live telemetry feeds
│   │   │   └── package.json                 # Dashboard build scripts & dependencies
│   │   │
│   │   └── extension/                       # Google Chrome Manifest V3 Security Extension
│   │       ├── manifest.json                # MV3 permissions, background worker & content scripts
│   │       ├── background/service-worker.js # Navigation inspector, DNR manager, policy engine
│   │       ├── content/link-scanner.js      # MutationObserver in-page link & form scanner
│   │       ├── popup/                       # Cyber Operations Center UI (HTML/CSS/JS)
│   │       ├── warning/                     # Threat quarantine barrier page (HTML/CSS/JS)
│   │       ├── storage/event-store.js       # Local privacy-preserving incident store
│   │       └── fonts/                       # Embedded zero-telemetry local typography
│   │
│   └── test-extension.js                    # 317-test automated verification test suite
│
├── edith_v7_fixed/                          # E.D.I.T.H. AI Autonomous System (Active Python Core)
│   ├── brain/                               # Autonomous ReAct agent, router & verification
│   ├── plugins/                             # System plugins (browser_defense.py, universal_control)
│   ├── hud/                                 # Flask HUD command center, templates & assets
│   ├── nexus/                               # Multi-step task approval & system execution
│   ├── security/                            # Biometric pattern lock & authorization policies
│   ├── tests/                               # Pytest test suite (browser defense, verification, HUD)
│   ├── .env.example                         # Environment configuration template
│   ├── main.py                              # EDITH core launcher
│   ├── requirements.txt                     # Python platform dependencies
│   └── run.bat                              # Windows one-click execution script
│
└── edith_v7_backup/                         # Baseline reference snapshot
```

---

## 7. Setup & Installation

### 7.1 Prerequisites
- **Node.js**: v18.0.0 or higher
- **Python**: v3.10.0 or higher
- **Browser**: Google Chrome, Brave, Edge, or any Chromium browser supporting Manifest V3

---

### 7.2 Backend & Threat Intelligence Configuration

1. Navigate to the backend directory:
   ```bash
   cd web/sentinelx-ai/backend
   npm install
   ```
2. Create your local environment file:
   ```bash
   cp .env.example .env
   ```
3. Edit `web/sentinelx-ai/backend/.env` with your API credentials:
   ```env
   # SentinelX AI Gateway Configuration
   PORT=8787
   HOST=127.0.0.1
   NODE_ENV=production

   # VirusTotal v3 Threat Intelligence
   VT_API_KEY=your_virustotal_api_key_here
   VT_ENABLED=true

   # Google Gemma 4 AI Gateway
   GEMINI_API_KEY=your_gemini_api_key_here
   GEMMA_MODEL_ID=gemma-4-26b-a4b-it
   ```
4. Start the gateway server:
   ```bash
   node server.js
   ```
   *The gateway will initialize on `http://127.0.0.1:8787`.*

---

### 7.3 Chrome Extension Installation

1. Open your Chromium browser and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked**.
4. Select the directory:
   ```text
   <PROJECT_ROOT>/web/sentinelx-ai/extension
   ```
5. Pin **EDITH AI — SentinelX Cyber Defense** to your browser toolbar.

---

### 7.4 EDITH AI Core Setup

1. Open a new terminal and navigate to `edith_v7_fixed`:
   ```bash
   cd edith_v7_fixed
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copy the environment configuration:
   ```bash
   cp .env.example .env
   ```
3. Start the EDITH AI engine and HUD:
   ```bash
   python main.py
   ```
   *The interactive HUD will be available at `http://localhost:5000`.*

---

## 8. Automated Test Suite & Verification

The platform includes exhaustive, zero-quota automated test suites validating all components:

### 8.1 Extension & Gateway Tests (317 Tests)
Run the Node.js test suite from the project root:
```bash
node web/test-extension.js
```
*Coverage highlights:*
- **Groups 1–3**: Manifest V3 structure, permissions, and syntax integrity.
- **Groups 4–8**: URL parsing, homoglyphs, typosquatting, keywords, and zero-trust scoring.
- **Groups 9–11**: DeclarativeNetRequest dynamic rules, real installation verification, and self-healing.
- **Groups 12–15**: Event store deduplication, Gemma 4 gateway prompt injection defense, and origin validation.
- **Group 16 (102 Tests)**: VirusTotal API v3 integration:
  - Protocol rejection (`ftp:`, `chrome:`, `javascript:`, `file:`).
  - Sensitive token and credential stripping (`token`, `session_id`, `apikey`).
  - RFC 1918 and internal destination blocking (`127.0.0.1`, `192.168.1.1`, `.local`, `[::1]`).
  - URL-safe Base64URL without padding.
  - Verdict classification mapping (`malicious`, `suspicious`, `clean/no detections`, `unknown`).
  - Mocked clean, malicious, 404, 429 rate-limited, and 500 error lookups.
  - In-memory bounded cache verification.
  - Leak prevention (zero API keys in response objects).
  - `blog.google` false-positive resolution.
  - Policy invariant preservation (clean VT cannot override local heuristic blocks).

### 8.2 EDITH Python Integration Tests (6 Tests)
Run pytest inside `edith_v7_fixed`:
```bash
cd edith_v7_fixed
python -m pytest tests/test_browser_defense.py -v
```
*Validates status dictionary formatting, briefing generation, router fast-paths, ReAct agent tool execution, and HUD sync endpoints.*

---

## 9. Operational Verification

1. **Test Heuristic Detection**:
   - Navigate to `http://192.168.1.1/login` or `http://paypal.com@phish-test.local`.
   - SentinelX immediately redirects the tab to the Warning Interstitial and injects dynamic DeclarativeNetRequest Rule.
2. **Test On-Demand VirusTotal Intelligence**:
   - Navigate to any public webpage (e.g., `https://example.com`).
   - Open the SentinelX popup.
   - Click the **VirusTotal Intel** button.
   - The card dynamically displays real multi-scanner verdicts: `Malicious`, `Suspicious`, `Harmless`, and `Undetected`.
3. **Test EDITH Cyber Defense Query**:
   - Open the EDITH terminal or HUD interface.
   - Ask: *"Show browser defense summary"* or *"What threats were blocked?"*
   - EDITH instantly formats an executive briefing summarizing active DNR rules, blocked targets, and threat telemetry.

---

## 10. License & Ethics

Distributed under the **MIT License**.

> **Ethical Cybersecurity Notice**: SentinelX AI and E.D.I.T.H. are engineered for defensive security, threat intelligence research, and local privacy preservation. Always ensure you have authorization before performing active network analysis or penetration testing against external domains.
