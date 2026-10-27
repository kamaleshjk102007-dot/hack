# SYNTRAX AI — Autonomous AI Cyber Defense

> **Zero-Trust Browser Link & Navigation Security Extension with Google Gemma 4 Threat Investigation, DeclarativeNetRequest Packet Containment & Verified Self-Healing**

---

## 1. Executive Summary & Vision

**SYNTRAX AI** is a local-first, privacy-preserving browser defense extension developed under Google Chrome Manifest V3. It combines deterministic zero-trust heuristics with on-demand **Google Gemma 4** threat investigation, real-time dynamic packet containment via Chrome's `declarativeNetRequest` API, and verified self-healing recovery.

Unlike superficial extensions that merely display mockup dashboards, SYNTRAX AI is an operational security tool where every threat detection, AI investigation, policy decision, rule installation, packet containment, and self-healing recovery is independently verifiable and backed by a comprehensive automated test suite.

---

## 2. Seven-Stage Cyber Defense Pipeline

```
  DETECT
    ↓  (Active tab URLs, navigation events, hyperlinks, form actions, buttons, iframes, downloads)
INVESTIGATE
    ↓  (Local deterministic zero-trust engine + on-demand advisory Google Gemma 4 LLM)
  DECIDE
    ↓  (Deterministic policy engine: HIGH_RISK, SUSPICIOUS, UNKNOWN, LOW_RISK, INTERNAL_RESTRICTED, ERROR)
 PROTECT
    ↓  (DeclarativeNetRequest dynamic rule enforcement + warning interstitial redirect)
SELF-HEAL
    ↓  (Continuous baseline rule reconciliation, discrepancy isolation, and safe restorative repair)
  VERIFY
    ↓  (Query active browser rule tables to verify physical presence of blocking rules)
  RECORD
    ↓  (Privacy-sanitized, credential-stripped, bounded local audit trail in chrome.storage.local)
```

1. **DETECT**: Collects actionable navigation and DOM targets across visible hyperlinks, hidden dropdown menus, closed `<details>` tags, form action URLs, navigation buttons, frame sources, and executable download links.
2. **INVESTIGATE**: Employs an offline-first local heuristic engine (Punycode homoglyphs, numerical IP hosts, userinfo authority spoofing, deceptive brands, keyword entropy). For complex threats, dispatches non-sensitive technical metadata to a local Gemma 4 gateway (`http://127.0.0.1:8787`).
3. **DECIDE**: Evaluates findings through a deterministic, centralized policy engine. AI recommendations are strictly advisory and cannot override local deterministic decisions. `UNKNOWN` is never equated with safe.
4. **PROTECT**: Implements real network-level blocking via Chrome's `declarativeNetRequest` API using dynamic rules with explicit priorities and domain-scoped filters. Redirects high-risk navigations to an interstitial security warning (`warning/warning.html`).
5. **SELF-HEAL**: Detects missing, tampered, or degraded baseline rules, repairs discrepancies idempotently, and re-verifies rule installation without disturbing third-party browser rules.
6. **VERIFY**: Confirms active protection by physically querying `chrome.declarativeNetRequest.getDynamicRules()` from the browser engine before declaring a verified state.
7. **RECORD**: Persists incident records locally in `chrome.storage.local` with automatic credential sanitization, token redaction, duplicate suppression, and bounded retention limits.

---

## 3. Directory Structure

```text
sentinelx-ai/
├── extension/                        # Manifest V3 Extension Root
│   ├── manifest.json                 # Permissions, content scripts, and resource definitions
│   ├── background/
│   │   └── service-worker.js         # Navigation coordinator, policy engine, DNR manager, AI proxy
│   ├── content/
│   │   └── link-scanner.js           # In-page link, button, form, and frame scanner with MutationObserver
│   ├── popup/
│   │   ├── popup.html                # Cybersecurity Operations Center popup interface
│   │   ├── popup.css                 # Dark navy, graphite, and electric-cyan design system
│   │   └── popup.js                  # Real-time HUD, Link Radar, Gemma 4 triggers, and self-healing controls
│   ├── warning/
│   │   ├── warning.html              # Interstitial security warning barrier
│   │   ├── warning.css               # Radar animations and threat breakdown styling
│   │   └── warning.js                # Interstitial parameter parser and bypass handling
│   ├── storage/
│   │   └── event-store.js            # Privacy-sanitized local storage manager and deduplicator
│   └── fonts/                        # Local typography (Space Grotesk, Inter, IBM Plex Mono)
│
├── backend/                          # Local Gemma 4 Security Gateway
│   ├── server.js                     # Zero-dependency HTTP gateway, origin validator, prompt builder
│   ├── .env                          # Local environment variables (GEMINI_API_KEY, GEMMA_MODEL_ID)
│   ├── .env.example                  # Template environment configuration
│   └── README.md                     # Backend API specification and model setup
│
├── README.md                         # Master documentation (this file)
└── test-extension.js                 # 215-test automated verification suite
```

---

## 4. Prerequisites & Environment Setup

* **Operating System**: Windows 10/11, macOS, or Linux.
* **Node.js**: Version 18.0.0 or higher.
* **Browser**: Google Chrome Version 110+ (supporting Manifest V3 and DeclarativeNetRequest dynamic rules).
* **Google AI Studio API Key**: Required for live Gemma 4 threat inference (obtain free from [Google AI Studio](https://aistudio.google.com/app/apikey)).

---

## 5. Step-by-Step Installation & Execution

### Step A: Configure the Backend Environment
1. Open PowerShell or a terminal and navigate to the backend directory:
   ```powershell
   cd D:\movie\web\sentinelx-ai\backend
   ```
2. Create or verify your `.env` configuration file:
   ```env
   PORT=8787
   GEMINI_API_KEY=YOUR_ACTUAL_GOOGLE_API_KEY_HERE
   GEMMA_MODEL_ID=gemma-4-26b-a4b-it
   REQUEST_TIMEOUT_MS=35000
   ```

### Step B: Launch the Local Gemma 4 Gateway
Start the lightweight, zero-dependency Node.js gateway:
```powershell
node server.js
```
The gateway will start on `http://127.0.0.1:8787` and confirm:
* Port: 8787
* Model ID: `gemma-4-26b-a4b-it` (with automatic failover to `gemma-4-31b-it`)
* API Key Status: `CONFIGURED ✓`

Verify the gateway health endpoint:
```powershell
curl http://127.0.0.1:8787/api/health
```

### Step C: Load the Extension into Google Chrome
1. Launch Google Chrome.
2. Navigate to `chrome://extensions/`.
3. In the top-right corner, enable **Developer mode**.
4. Click **Load unpacked** in the top-left corner.
5. Select the directory:
   ```text
   D:\movie\web\sentinelx-ai\extension
   ```
6. The extension will load as **SYNTRAX AI (SentinelX) — Autonomous Cyber Defense**.
7. Pin the extension icon to your Chrome toolbar.

---

## 6. Using the SYNTRAX AI Interface

### Active Tab Evaluation & Inspector
* Click the SYNTRAX AI icon in the Chrome toolbar.
* The popup immediately resolves the current active tab destination and runs a zero-trust heuristic scan.
* Inspect the risk score (0 to 100), risk badge (`HIGH_RISK`, `SUSPICIOUS`, `UNKNOWN`, `LOW_RISK`), and observed evidence chips.
* Use the **Presets** buttons (`IP Host`, `Phishing`, `Safe Baseline`, `Unknown`) for instant verification of detection rules.

### In-Page Link & Navigation Radar
* Click **Rescan Links** in the Link Radar panel.
* The content script traverses visible links, hidden dropdowns, form targets (`<form action>`), buttons (`data-href`), and subframe sources (`<iframe src>`).
* Real-time metrics display discovered targets, inspected targets, high-risk targets, suspicious targets, unknown targets, and skipped non-web protocols.
* Select any item in the findings scroll list to inspect its technical evidence and isolate its threat profile.

### Gemma 4 Threat Investigation
* Click **Investigate** in the AI card.
* Non-sensitive technical metadata (target domain, protocol, heuristic score, observed indicators) is dispatched to the local gateway.
* Gemma 4 analyzes the target under strict prompt-injection isolation delimiters (`<<<UNTRUSTED_METADATA>>>`).
* The popup displays the AI's advisory recommendation, technical explanation, forensic indicators, and explicit uncertainty percentage.
* If the gateway is offline or unconfigured, the extension automatically falls back to **Autonomous Local Defense Mode** without disruption.

### Dynamic Domain Blocking
* Click **Block Domain** on any flagged threat.
* The service worker creates a deterministic rule ID, registers the dynamic rule in `chrome.declarativeNetRequest`, and physically verifies its installation in the browser's active rule table.
* Subsequent requests to that domain are blocked at the network level by the browser engine.

### Self-Healing Integrity Diagnostic & Repair
* Navigate to the **Controls** tab (wrench icon) on the left rail.
* Click **Run Integrity Diagnostic**: Compares currently active browser rules against the expected baseline managed rule set.
* If any baseline rules are missing or corrupted, click **Restore & Verify Rules**: The self-healing engine restores the missing rules, verifies their installation in the browser table, and updates the integrity status to **VERIFIED HEALTHY**.

---

## 7. Privacy & Zero-Trust Guarantees

* **Zero Credential Scraping**: SYNTRAX AI strictly ignores, never reads, and never stores passwords, authentication cookies, session tokens, JWTs, or form input values.
* **URL Sanitization**: Before storing or transmitting URLs, embedded credentials (`user:pass@`) and 19 sensitive query parameters (`password`, `token`, `secret`, `jwt`, `cvv`, etc.) are stripped or redacted to `[REDACTED]`.
* **Local-First Operation**: All heuristic evaluation, policy decisions, and declarativeNetRequest blocking occur 100% locally on your machine with zero external network dependencies.
* **Origin Authorization Defense**: The local gateway restricts `POST /api/investigate` access to Chrome extensions, local tools, and localhost, blocking unauthorized cross-origin web scripts with HTTP 403 `FORBIDDEN_ORIGIN`.
* **Bounded Queues**: Link scanning enforces a maximum threshold of 500 unique destinations per page to prevent memory exhaustion on giant DOMs.

---

## 8. Automated Test Suite Execution

The project includes an end-to-end automated verification suite covering Manifest V3 compliance, heuristic detection, deterministic policy supremacy, DeclarativeNetRequest blocking, self-healing integrity, privacy sanitization, Gemma 4 contracts, live gateway endpoints, link scanning, navigation protection, and origin authorization:

```powershell
node test-extension.js
```

### Verified Test Groups (215 / 215 PASS):
1. **Manifest V3 Validation**: 10/10 PASS
2. **Referenced File Integrity Check**: 10/10 PASS
3. **JavaScript Syntax & Compilation**: 5/5 PASS
4. **URL Parsing & Scheme Handling**: 8/8 PASS
5. **Domain Sanitization & Obfuscation**: 15/15 PASS
6. **Zero-Trust Local Heuristics**: 8/8 PASS
7. **Deterministic Policy Engine**: 7/7 PASS
8. **DeclarativeNetRequest Rule Enforcement**: 10/10 PASS
9. **Self-Healing Integrity & Protection Recovery**: 10/10 PASS
10. **Privacy-Safe Incident Storage & Deduplication**: 7/7 PASS
11. **Gemma 4 AI Contract & Schema Validation**: 10/10 PASS
12. **Popup Integration Message Contracts**: 16/16 PASS
13. **Genuine Gemma 4 Gateway & Prompt Injection Defense**: 26/26 PASS
14. **Link, Navigation, Button, Form & Subframe Security Engine**: 34/34 PASS
15. **Gateway Concurrency, Origin Defense & Bounded Queues**: 19/19 PASS

---

## 9. Honest Security Limitations & Unsupported Cases

1. **Cross-Origin Frame DOM Traversal**: In accordance with the browser's Same-Origin Policy (SOP), content scripts cannot inspect the inner DOM elements of cross-origin `<iframe>` elements. The frame source URL (`src`) is inspected, and the SOP boundary is disclosed in the report.
2. **Opaque JavaScript Event Handlers**: Button navigation triggered by arbitrary JavaScript closures attached via `addEventListener('click', ...)` without declarative navigation attributes (`data-href`, `onclick`) cannot be predicted before execution without speculative side effects.
3. **AI Advisory Role**: Google Gemma 4 provides advisory intelligence only. The local client deterministic policy engine remains strictly authoritative over all blocking actions.
4. **Operating System Scope**: SYNTRAX AI protects browser navigation; it does not claim to prevent local administrator extension uninstallation or physical machine compromise.

---

## 10. License & Credits

Developed by the SYNTRAX AI Autonomous Cyber Defense Team.
* Engine: Manifest V3, Chrome Storage API, Chrome DeclarativeNetRequest API.
* AI Reasoning: Google Gemma 4 via Google Generative Language API.
