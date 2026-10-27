// sentinelx-ai/extension/popup/popup.js
/**
 * SYNTRAX AI — Autonomous Cybersecurity Command Center Controller
 * Connects the dark navy / electric-cyan popup interface with real Chrome Extension APIs,
 * local EventStore records, declarativeNetRequest verification, and zero-trust heuristic engine.
 */

document.addEventListener('DOMContentLoaded', async () => {
  // Navigation Tabs
  const railBtns = document.querySelectorAll('.rail-btn');
  const tabPanels = document.querySelectorAll('.tab-content-panel');

  // Header Elements
  const targetSearchInput = document.getElementById('target-search-input');
  const mainProtectionToggle = document.getElementById('main-protection-toggle');
  const headerDate = document.getElementById('header-date');
  const bellNotifyBtn = document.getElementById('bell-notify-btn');

  // Stat Cards
  const statTotalAlerts = document.getElementById('stat-total-alerts');
  const statProtectedDomains = document.getElementById('stat-protected-domains');
  const statCriticalThreats = document.getElementById('stat-critical-threats');
  const statProtectionStatus = document.getElementById('stat-protection-status');
  const statStatusPill = document.getElementById('stat-status-pill');

  // Current Tab Target Elements
  const currentProtocolBadge = document.getElementById('current-protocol-badge');
  const currentRiskBadge = document.getElementById('current-risk-badge');
  const policyDecisionBadge = document.getElementById('policy-decision-badge');
  const currentUrlText = document.getElementById('current-url-text');
  const btnCopyTarget = document.getElementById('btn-copy-target');
  const targetMeterFill = document.getElementById('target-meter-fill');
  const meterScoreVal = document.getElementById('meter-score-val');
  const meterCaption = document.getElementById('meter-caption');
  const findingsChipsList = document.getElementById('findings-chips-list');
  const btnRunAnalysis = document.getElementById('btn-run-analysis');
  const btnPreviewWarning = document.getElementById('btn-preview-warning');
  const btnBlockThreatDomain = document.getElementById('btn-block-threat-domain');
  const blockConfirmNote = document.getElementById('block-confirm-note');
  const presetChips = document.querySelectorAll('.preset-chip');

  // AI Panel
  const aiStatusPill = document.getElementById('ai-status-pill');
  const aiContentBox = document.getElementById('ai-content-box');
  const btnTriggerAi = document.getElementById('btn-trigger-ai');

  // VirusTotal Panel Elements
  const btnCheckVt = document.getElementById('btn-check-vt');
  const vtReputationCard = document.getElementById('vt-reputation-card');
  const vtVerdictPill = document.getElementById('vt-verdict-pill');
  const vtStatMalicious = document.getElementById('vt-stat-malicious');
  const vtStatSuspicious = document.getElementById('vt-stat-suspicious');
  const vtStatHarmless = document.getElementById('vt-stat-harmless');
  const vtStatUndetected = document.getElementById('vt-stat-undetected');
  const vtStatusNote = document.getElementById('vt-status-note');
  const vtTimestamp = document.getElementById('vt-timestamp');

  // In-Page Link & Navigation Radar Elements
  const btnRescanLinks = document.getElementById('btn-rescan-links');
  const radarStatusPill = document.getElementById('radar-status-pill');
  const radarTotalDiscovered = document.getElementById('radar-total-discovered');
  const radarTotalInspected = document.getElementById('radar-total-inspected');
  const radarHighRiskCount = document.getElementById('radar-high-risk-count');
  const radarSuspiciousCount = document.getElementById('radar-suspicious-count');
  const radarUnknownCount = document.getElementById('radar-unknown-count');
  const radarSkippedCount = document.getElementById('radar-skipped-count');
  const radarScanTime = document.getElementById('radar-scan-time');
  const radarTargetPage = document.getElementById('radar-target-page');
  const radarDestinationsScroll = document.getElementById('radar-destinations-scroll');
  const radarSkippedCounter = document.getElementById('radar-skipped-counter');
  const radarSkippedContent = document.getElementById('radar-skipped-content');

  // Incident Timeline & Analytics Elements
  const timelineChainTrack = document.getElementById('timeline-chain-track');
  const btnClearTimeline = document.getElementById('btn-clear-timeline');
  const btnQuickClear = document.getElementById('btn-quick-clear');
  const btnWipeLogs = document.getElementById('btn-wipe-logs');
  const eventsVerticalList = document.getElementById('events-vertical-list');
  const svgTooltipPill = document.getElementById('svg-tooltip-pill');

  // Severity Cluster Elements
  const pctCritical = document.getElementById('pct-critical');
  const pctHigh = document.getElementById('pct-high');
  const pctUnknown = document.getElementById('pct-unknown');
  const pctSafe = document.getElementById('pct-safe');

  // Analytics tab elements
  const analyticsTotal = document.getElementById('analytics-total');
  const analyticsHigh = document.getElementById('analytics-high');
  const analyticsSuspicious = document.getElementById('analytics-suspicious');
  const analyticsUnknown = document.getElementById('analytics-unknown');
  const analyticsSafe = document.getElementById('analytics-safe');
  const analyticsBlocked = document.getElementById('analytics-blocked');

  // Self-Healing & Controls
  const toggleShield = document.getElementById('toggle-shield');
  const toggleDnr = document.getElementById('toggle-dnr');
  const toggleHomoglyph = document.getElementById('toggle-homoglyph');
  const btnRunIntegrity = document.getElementById('btn-run-integrity');
  const btnRepairRules = document.getElementById('btn-repair-rules');
  const integrityFeedback = document.getElementById('integrity-feedback');
  const integrityStatusPill = document.getElementById('integrity-status-pill');
  const specRulesCount = document.getElementById('spec-rules-count');
  const specLastCheck = document.getElementById('spec-last-check');
  const specRepairResult = document.getElementById('spec-repair-result');

  // Modal Dialog Elements
  const clearConfirmModal = document.getElementById('clear-confirm-modal');
  const btnModalCancel = document.getElementById('btn-modal-cancel');
  const btnModalConfirm = document.getElementById('btn-modal-confirm');
  const btnRailHelp = document.getElementById('btn-rail-help');
  const helpInfoModal = document.getElementById('help-info-modal');
  const btnModalHelpClose = document.getElementById('btn-modal-help-close');

  // Internal State
  let currentTabUrl = '';
  let currentTabDomain = '';
  let currentAnalysis = null;
  let isScanning = false;

  // Format today's date in header
  if (headerDate) {
    const now = new Date();
    const month = now.toLocaleString('en-US', { month: 'short' });
    headerDate.textContent = `Today, ${month} ${now.getDate()}`;
  }

  /**
   * Safe sendMessage wrapper with error handling
   */
  function sendBackgroundMessage(msg) {
    return new Promise((resolve) => {
      if (typeof chrome === 'undefined' || !chrome.runtime?.sendMessage) {
        resolve({ success: false, error: 'Extension runtime unavailable' });
        return;
      }
      chrome.runtime.sendMessage(msg, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ success: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(response || { success: false });
        }
      });
    });
  }

  /**
   * TAB SWITCHING (Left Rail Navigation)
   */
  railBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTabId = btn.dataset.tab;
      if (!targetTabId) return;

      railBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      tabPanels.forEach(p => p.classList.remove('active'));
      const activePanel = document.getElementById(targetTabId);
      if (activePanel) activePanel.classList.add('active');
    });
  });

  if (bellNotifyBtn) {
    bellNotifyBtn.addEventListener('click', () => {
      const timelineRailBtn = document.querySelector('[data-tab="tab-timeline"]');
      if (timelineRailBtn) timelineRailBtn.click();
    });
  }

  /**
   * 1. Query Current Active Tab
   */
  async function queryActiveTab() {
    if (typeof chrome === 'undefined' || !chrome.tabs?.query) {
      currentTabUrl = 'https://github.com/torvalds/linux';
      applyDetectedUrl(currentTabUrl);
      return;
    }

    try {
      let tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      if (!tabs || tabs.length === 0) {
        tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      }

      const tab = tabs && tabs[0];
      const rawUrl = tab ? (tab.url || tab.pendingUrl) : '';

      if (rawUrl) {
        currentTabUrl = rawUrl;
        applyDetectedUrl(rawUrl);
      } else {
        // Restricted tab (e.g. chrome://extensions/)
        currentTabUrl = '';
        currentTabDomain = 'Browser System';
        currentUrlText.textContent = 'chrome:// System Page (Protected by Browser Sandbox)';
        currentProtocolBadge.textContent = 'INTERNAL';
        currentProtocolBadge.className = 'protocol-chip internal';
        currentRiskBadge.textContent = 'SYSTEM SECURE';
        currentRiskBadge.className = 'risk-pill LOW_RISK';
        if (targetSearchInput) targetSearchInput.placeholder = 'Enter or select preset to analyze...';
      }
    } catch (err) {
      console.warn('[SYNTRAX Popup] Tab query notice:', err);
      currentUrlText.textContent = 'Tab access restricted';
      currentProtocolBadge.textContent = 'RESTRICTED';
      currentProtocolBadge.className = 'protocol-chip internal';
    }
  }

  function applyDetectedUrl(url) {
    currentUrlText.textContent = url;
    currentUrlText.title = url;
    if (targetSearchInput && !targetSearchInput.value) {
      targetSearchInput.value = url;
    }

    const trimmed = url.toLowerCase();
    if (trimmed.startsWith('https://')) {
      currentProtocolBadge.textContent = 'HTTPS';
      currentProtocolBadge.className = 'protocol-chip https';
    } else if (trimmed.startsWith('http://')) {
      currentProtocolBadge.textContent = 'HTTP (INSECURE)';
      currentProtocolBadge.className = 'protocol-chip http';
    } else if (trimmed.startsWith('chrome://') || trimmed.startsWith('about:') || trimmed.startsWith('chrome-extension://')) {
      currentProtocolBadge.textContent = 'INTERNAL';
      currentProtocolBadge.className = 'protocol-chip internal';
    } else {
      currentProtocolBadge.textContent = 'URI';
      currentProtocolBadge.className = 'protocol-chip';
    }

    try {
      const parsed = new URL(url);
      currentTabDomain = parsed.hostname;
    } catch (_) {
      currentTabDomain = url.split('/')[0] || '';
    }
  }

  /**
   * Clipboard Copy
   */
  if (btnCopyTarget) {
    btnCopyTarget.addEventListener('click', async () => {
      const text = currentUrlText.textContent;
      if (text) {
        try {
          await navigator.clipboard.writeText(text);
          btnCopyTarget.innerHTML = '✓';
          setTimeout(() => {
            btnCopyTarget.innerHTML = `
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2"/>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
            `;
          }, 1000);
        } catch (_) {}
      }
    });
  }

  /**
   * Search input handler (Enter key triggers analysis)
   */
  if (targetSearchInput) {
    targetSearchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = targetSearchInput.value.trim();
        if (val) triggerScan(val);
      }
    });
  }

  /**
   * Preset Buttons (1-Click instant analysis)
   */
  presetChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const presetUrl = chip.dataset.url;
      if (presetUrl) {
        if (targetSearchInput) targetSearchInput.value = presetUrl;
        triggerScan(presetUrl);
      }
    });
  });

  /**
   * Local Zero-Trust Heuristic Evaluation Fallback (Used only if service-worker unreachable)
   */
  function runLocalAnalysisFallback(rawUrl) {
    let hostname = 'unknown';
    let protocol = 'https:';
    try {
      const parsed = new URL(rawUrl);
      hostname = parsed.hostname.toLowerCase();
      protocol = parsed.protocol;
    } catch (_) {}

    let score = 0;
    const findings = [];

    if (protocol === 'http:') {
      score += 25;
      findings.push({ severity: 'WARNING', category: 'TRANSPORT', detail: 'Insecure Protocol: URL uses unencrypted HTTP.' });
    } else if (protocol === 'https:') {
      findings.push({ severity: 'INFO', category: 'TRANSPORT', detail: 'Encrypted Transport: TLS active.' });
    }

    if (/^[0-9.]+$/.test(hostname)) {
      score += 45;
      findings.push({ severity: 'HIGH', category: 'HOST_IDENTITY', detail: 'Raw IP Host: Connects directly via numerical IP address.' });
    }

    if (rawUrl.includes('@')) {
      score += 50;
      findings.push({ severity: 'CRITICAL', category: 'URL_OBFUSCATION', detail: 'Authority Spoofing: Contains credentials/userinfo ("@") in authority string.' });
    }

    const isVerified = ['google.com', 'github.com', 'microsoft.com', 'wikipedia.org'].some(d => hostname.endsWith(d));
    let level = 'UNKNOWN';
    let reason = 'Zero-Trust Baseline: Insufficient evidence to confirm safety. No overt threat signatures detected, but domain reputation is unverified.';

    if (score >= 50) {
      level = 'HIGH_RISK';
      reason = 'High-confidence heuristic indicators of deceptive or hostile structure.';
    } else if (score >= 25) {
      level = 'SUSPICIOUS';
      reason = 'Heuristic indicators suggest potential security anomalies or unencrypted transport.';
    } else if (isVerified && protocol === 'https:') {
      level = 'LOW_RISK';
      reason = 'Verified public infrastructure baseline with encrypted TLS.';
    }

    return {
      url: rawUrl,
      domain: hostname,
      riskScore: Math.min(100, score),
      riskLevel: level,
      verdictReason: reason,
      findings
    };
  }

  /**
   * Unified Scan Trigger
   */
  async function triggerScan(urlOverride) {
    if (isScanning) return;
    const targetUrl = (urlOverride || (targetSearchInput ? targetSearchInput.value : currentTabUrl) || '').trim();
    if (!targetUrl || targetUrl.startsWith('chrome://') || targetUrl.startsWith('about:')) return;

    isScanning = true;
    currentTabUrl = targetUrl;
    applyDetectedUrl(targetUrl);

    btnRunAnalysis.disabled = true;
    btnRunAnalysis.innerHTML = '<span>Scanning Target...</span>';

    try {
      const response = await sendBackgroundMessage({
        type: 'ANALYZE_URL',
        url: targetUrl
      });

      if (response && response.success && response.analysis) {
        renderAnalysis(response.analysis, response.policyDecision);
      } else {
        const fallback = runLocalAnalysisFallback(targetUrl);
        renderAnalysis(fallback, null);
      }
    } catch (_) {
      const fallback = runLocalAnalysisFallback(targetUrl);
      renderAnalysis(fallback, null);
    } finally {
      isScanning = false;
      btnRunAnalysis.disabled = false;
      btnRunAnalysis.innerHTML = `
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5">
          <circle cx="11" cy="11" r="8"/>
          <line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <span>Re-Analyze Page</span>
      `;
      await refreshLogsAndStats();
    }
  }

  btnRunAnalysis.addEventListener('click', () => {
    triggerScan();
  });

  /**
   * Render Threat Analysis Outcome
   */
  function renderAnalysis(analysis, policyDecision) {
    currentAnalysis = analysis;
    const level = analysis.riskLevel || 'UNKNOWN';
    currentRiskBadge.textContent = level.replace('_', ' ');
    currentRiskBadge.className = `risk-pill ${level}`;

    if (policyDecisionBadge && policyDecision) {
      policyDecisionBadge.classList.remove('hidden');
      policyDecisionBadge.textContent = policyDecision.policyCode || policyDecision.decision || 'POL_MONITOR';
    }

    const score = analysis.riskScore || 0;
    meterScoreVal.textContent = `${score} / 100`;
    targetMeterFill.style.width = `${Math.max(6, score)}%`;

    if (level === 'HIGH_RISK') {
      targetMeterFill.style.background = 'var(--critical-threat)';
      targetMeterFill.style.boxShadow = '0 0 8px rgba(255, 69, 96, 0.4)';
      meterCaption.textContent = 'High-Risk Threat Indicators Flagged';
      btnBlockThreatDomain.classList.remove('hidden');
    } else if (level === 'SUSPICIOUS') {
      targetMeterFill.style.background = 'var(--warning-amber)';
      targetMeterFill.style.boxShadow = '0 0 8px rgba(245, 158, 11, 0.4)';
      meterCaption.textContent = 'Potential Security Anomalies Detected';
      btnBlockThreatDomain.classList.remove('hidden');
    } else if (level === 'LOW_RISK') {
      targetMeterFill.style.background = 'var(--verified-protection)';
      targetMeterFill.style.boxShadow = '0 0 8px rgba(52, 211, 153, 0.4)';
      meterCaption.textContent = 'Verified Clean Public Infrastructure Baseline';
      btnBlockThreatDomain.classList.add('hidden');
    } else {
      targetMeterFill.style.background = 'var(--electric-cyan)';
      targetMeterFill.style.boxShadow = '0 0 8px var(--electric-cyan-glow)';
      meterCaption.textContent = 'Zero-Trust Baseline (Unverified Reputation)';
      btnBlockThreatDomain.classList.remove('hidden');
    }

    // Populate Findings Chips
    findingsChipsList.innerHTML = '';
    if (analysis.findings && analysis.findings.length > 0) {
      analysis.findings.forEach(f => {
        const li = document.createElement('li');
        li.className = `chip-finding ${f.severity || 'safe'}`;
        li.textContent = f.detail;
        findingsChipsList.appendChild(li);
      });
    } else {
      const li = document.createElement('li');
      li.className = 'chip-finding safe';
      li.textContent = 'No overt heuristic threat signatures detected.';
      findingsChipsList.appendChild(li);
    }
  }

  /**
   * Block Domain Action with verified installation guarantee
   */
  btnBlockThreatDomain.addEventListener('click', async () => {
    if (!currentTabDomain || currentTabDomain === 'Browser System') return;

    btnBlockThreatDomain.disabled = true;
    btnBlockThreatDomain.textContent = 'Enforcing Block...';

    const res = await sendBackgroundMessage({
      type: 'BLOCK_DOMAIN_RULE',
      domain: currentTabDomain,
      url: currentTabUrl,
      riskScore: currentAnalysis ? currentAnalysis.riskScore : 85,
      findings: currentAnalysis ? currentAnalysis.findings : []
    });

    btnBlockThreatDomain.disabled = false;
    btnBlockThreatDomain.textContent = 'Block Domain';

    blockConfirmNote.classList.remove('hidden');
    if (res && res.success && res.verified) {
      blockConfirmNote.textContent = `✓ Domain "${res.domain}" quarantined via verified DeclarativeNetRequest Rule #${res.ruleId}`;
      await refreshLogsAndStats();
    } else {
      blockConfirmNote.textContent = `Block action failed: ${res?.error || 'Verification unconfirmed'}`;
    }
  });

  /**
   * Preview Warning Interstitial
   */
  btnPreviewWarning.addEventListener('click', () => {
    const url = currentTabUrl || 'https://unknown.target';
    const domain = currentTabDomain || 'Target Host';
    const score = currentAnalysis ? currentAnalysis.riskScore : 75;
    const level = currentAnalysis ? currentAnalysis.riskLevel : 'SUSPICIOUS';
    const reason = currentAnalysis ? currentAnalysis.verdictReason : 'Manual threat preview inspection';

    const warningUrl = chrome.runtime.getURL(
      `warning/warning.html?url=${encodeURIComponent(url)}&domain=${encodeURIComponent(domain)}&score=${score}&level=${level}&reason=${encodeURIComponent(reason)}`
    );

    if (chrome.tabs?.create) {
      chrome.tabs.create({ url: warningUrl });
    } else {
      window.open(warningUrl, '_blank');
    }
  });

  /**
   * Safe HTML Escaping Helper
   */
  function escapeHtml(str) {
    if (typeof str !== 'string') return String(str || '');
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /**
   * Render genuine Gemma 4 investigation results in the AI card
   */
  function renderGemmaInvestigation(inv) {
    if (!aiContentBox) return;

    const timeStr = inv.validatedAt ? new Date(inv.validatedAt).toLocaleTimeString() : 'Just now';
    const recAction = inv.recommendedNextStep || inv.recommendedAction || 'MONITOR';
    const indicators = Array.isArray(inv.suspiciousIndicators)
      ? inv.suspiciousIndicators
      : (Array.isArray(inv.findings) ? inv.findings.map(f => typeof f === 'string' ? f : (f.detail || f.indicator || JSON.stringify(f))) : []);

    const uncertaintyPct = typeof inv.uncertaintyScore === 'number'
      ? Math.round(inv.uncertaintyScore * 100)
      : Math.round((inv.uncertainty || 0.25) * 100);

    aiContentBox.innerHTML = `
      <div class="ai-result-meta-bar">
        <span class="ai-model-tag">${escapeHtml(inv.modelId || 'gemma-4-31b-it')}</span>
        <div class="ai-meta-right">
          <span class="ai-advisory-pill ${escapeHtml(recAction)}">Advisory: ${escapeHtml(recAction)}</span>
          <span class="ai-timestamp">${escapeHtml(timeStr)}</span>
        </div>
      </div>
      <div class="ai-summary-headline">${escapeHtml(inv.investigationSummary || inv.explanation || 'Investigation complete.')}</div>
      ${inv.evidenceExplanation ? `<p class="ai-evidence-paragraph">${escapeHtml(inv.evidenceExplanation)}</p>` : ''}
      ${indicators.length > 0 ? `
        <ul class="ai-indicators-chips">
          ${indicators.map(ind => `<li class="ai-indicator-chip">${escapeHtml(String(ind))}</li>`).join('')}
        </ul>
      ` : ''}
      <div class="ai-uncertainty-card">
        <span>${escapeHtml(inv.uncertaintyAndLimitations || 'Lexical & structural evaluation without sandbox emulation.')}</span>
        <span class="ai-uncertainty-score">Uncertainty: ${uncertaintyPct}%</span>
      </div>
    `;
  }

  /**
   * Render honest offline or configuration notice in the AI card
   */
  function renderGemmaOfflineNotice(title, detail) {
    if (!aiContentBox) return;

    aiContentBox.innerHTML = `
      <div class="ai-offline-notice">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#00e5ff" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <div class="ai-notice-text">
          <strong>${escapeHtml(title)}:</strong>
          <span>${escapeHtml(detail)}</span>
        </div>
      </div>
    `;
  }

  /**
   * Check Gemma Gateway Health status and update status pill
   */
  async function checkAiGatewayHealth() {
    try {
      const health = await sendBackgroundMessage({ type: 'CHECK_AI_SERVICE_HEALTH' });
      if (health && health.available) {
        if (health.configured) {
          if (aiStatusPill) {
            aiStatusPill.className = 'ai-status-pill online';
            aiStatusPill.textContent = 'ONLINE (GEMMA 4)';
          }
        } else {
          if (aiStatusPill) {
            aiStatusPill.className = 'ai-status-pill config-needed';
            aiStatusPill.textContent = 'CONFIG REQUIRED';
          }
        }
      } else {
        if (aiStatusPill) {
          aiStatusPill.className = 'ai-status-pill offline';
          aiStatusPill.textContent = 'OFFLINE MODE';
        }
      }
    } catch (_) {
      if (aiStatusPill) {
        aiStatusPill.className = 'ai-status-pill offline';
        aiStatusPill.textContent = 'OFFLINE MODE';
      }
    }
  }

  /**
   * Trigger Gemma 4 AI threat investigation
   */
  async function triggerAiInvestigation() {
    const targetUrl = (targetSearchInput ? targetSearchInput.value : currentTabUrl) || currentTabUrl;
    if (!targetUrl || targetUrl.startsWith('chrome://') || targetUrl.startsWith('about:')) {
      renderGemmaOfflineNotice('Target Ineligible', 'Cannot investigate internal browser interfaces with external AI.');
      return;
    }

    if (btnTriggerAi) {
      btnTriggerAi.disabled = true;
      btnTriggerAi.innerHTML = `
        <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 14 14"/>
        </svg>
        <span>Investigating...</span>
      `;
    }

    if (aiStatusPill) {
      aiStatusPill.className = 'ai-status-pill investigating';
      aiStatusPill.textContent = 'INFERRING...';
    }

    try {
      const res = await sendBackgroundMessage({
        type: 'INVESTIGATE_URL_WITH_AI',
        url: targetUrl,
        analysis: currentAnalysis
      });

      if (res && res.success && res.genuineAi && res.investigation) {
        if (aiStatusPill) {
          aiStatusPill.className = 'ai-status-pill verified';
          aiStatusPill.textContent = 'VERIFIED AI';
        }
        renderGemmaInvestigation(res.investigation);
        await refreshLogsAndStats();
      } else {
        const status = res?.status;
        if (status === 'CONFIG_REQUIRED') {
          if (aiStatusPill) {
            aiStatusPill.className = 'ai-status-pill config-needed';
            aiStatusPill.textContent = 'CONFIG REQUIRED';
          }
          renderGemmaOfflineNotice(
            'API Key Configuration Required',
            res?.error || 'GEMINI_API_KEY is not configured in backend environment. Set GEMINI_API_KEY in sentinelx-ai/backend/.env to enable live Gemma 4 inference.'
          );
        } else if (status === 'GATEWAY_OFFLINE') {
          if (aiStatusPill) {
            aiStatusPill.className = 'ai-status-pill offline';
            aiStatusPill.textContent = 'GATEWAY OFFLINE';
          }
          renderGemmaOfflineNotice(
            'Autonomous Local Defense Active',
            'Gemma 4 gateway is unreachable at http://127.0.0.1:8787. Autonomous zero-trust heuristics and deterministic policy enforcement are protecting your browsing locally.'
          );
        } else {
          if (aiStatusPill) {
            aiStatusPill.className = 'ai-status-pill offline';
            aiStatusPill.textContent = 'AI UNAVAILABLE';
          }
          renderGemmaOfflineNotice(
            'AI Investigation Notice',
            res?.error || 'Investigation could not be completed at this time. Local defense remains active.'
          );
        }
      }
    } catch (err) {
      if (aiStatusPill) {
        aiStatusPill.className = 'ai-status-pill offline';
        aiStatusPill.textContent = 'OFFLINE MODE';
      }
      renderGemmaOfflineNotice('Connection Failed', err.message || 'Failed to communicate with service worker.');
    } finally {
      if (btnTriggerAi) {
        btnTriggerAi.disabled = false;
        btnTriggerAi.innerHTML = `
          <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.5">
            <polygon points="5 3 19 12 5 21 5 3"/>
          </svg>
          <span>Investigate</span>
        `;
      }
    }
  }

  if (btnTriggerAi) {
    btnTriggerAi.addEventListener('click', triggerAiInvestigation);
  }

  /**
   * Render VirusTotal v3 Reputation Results in the UI
   */
  function renderVirusTotalReputation(rep) {
    if (!vtReputationCard || !rep) return;
    vtReputationCard.classList.remove('hidden');

    const verdict = (rep.verdict || 'UNKNOWN').toUpperCase();
    if (vtVerdictPill) {
      vtVerdictPill.textContent = verdict.replace('_', ' ');
      vtVerdictPill.className = `vt-verdict-pill ${verdict.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}`;
    }

    if (rep.stats) {
      if (vtStatMalicious) vtStatMalicious.textContent = rep.stats.malicious || 0;
      if (vtStatSuspicious) vtStatSuspicious.textContent = rep.stats.suspicious || 0;
      if (vtStatHarmless) vtStatHarmless.textContent = rep.stats.harmless || 0;
      if (vtStatUndetected) vtStatUndetected.textContent = rep.stats.undetected || 0;
    }

    if (vtStatusNote) {
      let note = rep.note || rep.error || 'VirusTotal v3 URL intelligence lookup completed.';
      if (rep.cached) {
        note = `[CACHED] ${note}`;
      }
      vtStatusNote.textContent = note;
    }

    if (vtTimestamp) {
      const time = rep.timestamp ? new Date(rep.timestamp).toLocaleTimeString() : '';
      vtTimestamp.textContent = time;
    }

    // If VT detected malicious or suspicious signals, elevate target score if not already blocked
    if ((verdict === 'MALICIOUS' || verdict === 'SUSPICIOUS') && currentAnalysis) {
      const elevatedScore = Math.max(currentAnalysis.riskScore || 0, verdict === 'MALICIOUS' ? 90 : 65);
      meterScoreVal.textContent = `${elevatedScore} / 100`;
      targetMeterFill.style.width = `${elevatedScore}%`;
      if (verdict === 'MALICIOUS') {
        currentRiskBadge.textContent = 'HIGH RISK (VT)';
        currentRiskBadge.className = 'risk-pill HIGH_RISK';
        targetMeterFill.style.background = 'var(--critical-threat)';
        meterCaption.textContent = 'VirusTotal v3 flagged active malicious detections!';
        btnBlockThreatDomain.classList.remove('hidden');
      }
    }
  }

  /**
   * Trigger on-demand VirusTotal URL Reputation Check
   */
  async function triggerVirusTotalCheck() {
    const targetUrl = (targetSearchInput ? targetSearchInput.value : currentTabUrl) || currentTabUrl;
    if (!targetUrl || targetUrl.startsWith('chrome://') || targetUrl.startsWith('about:')) {
      if (vtReputationCard) vtReputationCard.classList.remove('hidden');
      if (vtVerdictPill) {
        vtVerdictPill.textContent = 'UNSUPPORTED';
        vtVerdictPill.className = 'vt-verdict-pill unavailable';
      }
      if (vtStatusNote) vtStatusNote.textContent = 'Cannot inspect internal browser schemes via VirusTotal.';
      return;
    }

    if (btnCheckVt) {
      btnCheckVt.disabled = true;
      btnCheckVt.innerHTML = `
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 14 14"/>
        </svg>
        <span>Checking VT...</span>
      `;
    }

    if (vtReputationCard) vtReputationCard.classList.remove('hidden');
    if (vtVerdictPill) {
      vtVerdictPill.textContent = 'LOOKING UP...';
      vtVerdictPill.className = 'vt-verdict-pill scanning';
    }

    try {
      const res = await sendBackgroundMessage({
        type: 'CHECK_VIRUSTOTAL_REPUTATION',
        url: targetUrl
      });

      if (res && res.reputation) {
        renderVirusTotalReputation(res.reputation);
        await refreshLogsAndStats();
      } else {
        renderVirusTotalReputation({
          verdict: 'UNAVAILABLE',
          note: res?.error || 'VirusTotal service currently unavailable. Local zero-trust baseline remains active.',
          stats: { malicious: 0, suspicious: 0, harmless: 0, undetected: 0 }
        });
      }
    } catch (err) {
      renderVirusTotalReputation({
        verdict: 'ERROR',
        note: err.message || 'Failed to query VirusTotal service.',
        stats: { malicious: 0, suspicious: 0, harmless: 0, undetected: 0 }
      });
    } finally {
      if (btnCheckVt) {
        btnCheckVt.disabled = false;
        btnCheckVt.innerHTML = `
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
          <span>VirusTotal Intel</span>
        `;
      }
    }
  }

  if (btnCheckVt) {
    btnCheckVt.addEventListener('click', triggerVirusTotalCheck);
  }

  /**
   * Render In-Page Link & Navigation Radar Report
   */
  function renderLinkRadarReport(report) {
    if (!report) return;

    if (radarTotalDiscovered) radarTotalDiscovered.textContent = report.totalDiscovered || 0;
    if (radarTotalInspected) radarTotalInspected.textContent = report.inspectableCount || 0;
    if (radarHighRiskCount) radarHighRiskCount.textContent = report.highRiskCount || 0;
    if (radarSuspiciousCount) radarSuspiciousCount.textContent = report.suspiciousCount || 0;
    if (radarUnknownCount) radarUnknownCount.textContent = report.unknownCount || 0;
    if (radarSkippedCount) radarSkippedCount.textContent = report.skippedCount || 0;

    if (radarScanTime) {
      const timeStr = report.assessedAt ? new Date(report.assessedAt).toLocaleTimeString() : 'Just now';
      radarScanTime.textContent = `Scanned at ${timeStr}`;
    }

    if (radarTargetPage) {
      radarTargetPage.textContent = report.pageUrl ? report.pageUrl.slice(0, 45) : 'Active Page';
      radarTargetPage.title = report.pageUrl || '';
    }

    if (radarStatusPill) {
      radarStatusPill.className = 'radar-scan-pill done';
      radarStatusPill.textContent = report.highRiskCount > 0 ? `${report.highRiskCount} HIGH RISK` : 'SCANNED';
    }

    // Populate Selectable Findings List
    if (radarDestinationsScroll) {
      radarDestinationsScroll.innerHTML = '';
      const list = report.destinations || [];

      if (list.length === 0) {
        radarDestinationsScroll.innerHTML = `
          <div class="radar-empty-notice">
            <span>No hyperlinks, forms, or navigation destinations found on this page.</span>
          </div>
        `;
      } else {
        // Show flagged or inspectable destinations (prioritize HIGH_RISK and SUSPICIOUS)
        const sorted = [...list].sort((a, b) => {
          const scoreA = a.riskScore || (a.riskLevel === 'HIGH_RISK' ? 90 : (a.riskLevel === 'SUSPICIOUS' ? 50 : 10));
          const scoreB = b.riskScore || (b.riskLevel === 'HIGH_RISK' ? 90 : (b.riskLevel === 'SUSPICIOUS' ? 50 : 10));
          return scoreB - scoreA;
        });

        sorted.slice(0, 40).forEach(dest => {
          const item = document.createElement('div');
          const level = dest.riskLevel || 'UNKNOWN';
          item.className = `radar-dest-item ${level}`;

          let tagClass = '';
          let tagText = dest.sourceTags?.[0] || dest.type || 'link';
          if (dest.meta?.isFormAction) { tagClass = 'form'; tagText = `FORM ${dest.meta.formMethod || 'POST'}`; }
          else if (dest.category === 'DOWNLOAD_DESTINATION') { tagClass = 'download'; tagText = 'DOWNLOAD'; }
          else if (dest.isHidden) { tagClass = 'hidden'; tagText = 'HIDDEN'; }

          const evidenceSnippet = dest.findings && dest.findings.length > 0
            ? dest.findings[0].detail
            : (dest.skipReason || dest.verdictReason || (dest.isInspectableWebUrl ? 'Zero-Trust Inspection Complete' : 'Non-Web Protocol'));

          item.innerHTML = `
            <div class="radar-dest-left">
              <div class="radar-dest-title-row">
                <span class="radar-tag-badge ${tagClass}">${escapeHtml(tagText)}</span>
                <span class="radar-dest-url" title="${escapeHtml(dest.url || dest.raw)}">${escapeHtml(dest.url || dest.raw)}</span>
              </div>
              <span class="radar-dest-evidence" title="${escapeHtml(evidenceSnippet)}">${escapeHtml(evidenceSnippet)}</span>
            </div>
            <span class="risk-pill ${level}">${level.replace('_', ' ')}</span>
          `;

          // Clicking a destination focuses it in the main analysis box
          item.addEventListener('click', () => {
            document.querySelectorAll('.radar-dest-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');

            if (targetSearchInput) targetSearchInput.value = dest.url;
            if (dest.isInspectableWebUrl) {
              triggerScan(dest.url);
            }
          });

          radarDestinationsScroll.appendChild(item);
        });
      }
    }

    // Populate Non-Inspected / Skipped Protocol Disclosures
    if (radarSkippedCounter) {
      radarSkippedCounter.textContent = report.skippedCount || 0;
    }
    if (radarSkippedContent) {
      const summary = report.skippedSummary || {};
      const entries = Object.entries(summary);
      if (entries.length === 0) {
        radarSkippedContent.innerHTML = '<div class="skipped-empty">All discovered links conform to inspectable web protocols.</div>';
      } else {
        radarSkippedContent.innerHTML = entries.map(([category, count]) => `
          <div class="radar-skip-row">
            <span>${escapeHtml(category.replace('SCHEME_', 'Protocol: '))}</span>
            <strong>${count} link${count > 1 ? 's' : ''}</strong>
          </div>
        `).join('');
      }
    }
  }

  /**
   * Trigger in-page scan via content script or background fallback
   */
  async function triggerPageLinksScan() {
    if (!btnRescanLinks) return;

    btnRescanLinks.disabled = true;
    if (radarStatusPill) {
      radarStatusPill.className = 'radar-scan-pill scanning';
      radarStatusPill.textContent = 'SCANNING DOM...';
    }

    try {
      if (typeof chrome !== 'undefined' && chrome.tabs?.query) {
        const tabs = await new Promise(r => chrome.tabs.query({ active: true, currentWindow: true }, r));
        const activeTab = tabs?.[0];

        if (activeTab && activeTab.url && !activeTab.url.startsWith('chrome://') && !activeTab.url.startsWith('about:') && !activeTab.url.startsWith('chrome-extension://')) {
          // Attempt to communicate directly with content script on active tab
          const contentRes = await new Promise(resolve => {
            chrome.tabs.sendMessage(activeTab.id, { type: 'SCAN_PAGE_LINKS' }, (res) => {
              if (chrome.runtime.lastError || !res) {
                resolve(null);
              } else {
                resolve(res);
              }
            });
          });

          if (contentRes && contentRes.success && Array.isArray(contentRes.uniqueDestinations)) {
            // Batch analyze discovered destinations with background heuristic engine
            const bgRes = await sendBackgroundMessage({
              type: 'ANALYZE_PAGE_DESTINATIONS',
              destinations: contentRes.uniqueDestinations,
              pageUrl: contentRes.pageUrl || activeTab.url
            });

            if (bgRes && bgRes.success && bgRes.report) {
              renderLinkRadarReport(bgRes.report);
              return;
            }
          }
        }
      }

      // Fallback: Query cached background destinations status
      const cached = await sendBackgroundMessage({
        type: 'GET_PAGE_DESTINATIONS_STATUS',
        pageUrl: currentTabUrl
      });
      if (cached && cached.success && cached.report) {
        renderLinkRadarReport(cached.report);
      } else {
        // If on internal or blank page
        if (radarStatusPill) {
          radarStatusPill.className = 'radar-scan-pill';
          radarStatusPill.textContent = 'RESTRICTED';
        }
        if (radarDestinationsScroll) {
          radarDestinationsScroll.innerHTML = `
            <div class="radar-empty-notice">
              <span>Internal browser interfaces (${escapeHtml(currentTabUrl.slice(0, 25))}) do not expose inspectable DOM hyperlinks.</span>
            </div>
          `;
        }
      }

    } catch (err) {
      console.warn('[SentinelX Popup] Link scan notice:', err);
    } finally {
      if (btnRescanLinks) btnRescanLinks.disabled = false;
    }
  }

  if (btnRescanLinks) {
    btnRescanLinks.addEventListener('click', () => {
      triggerPageLinksScan();
    });
  }


  /**
   * 2. Populate Statistics, Timeline, and Activity from Stored Events
   */
  async function refreshLogsAndStats() {
    const res = await sendBackgroundMessage({ type: 'GET_EVENTS', limit: 50 });
    const events = (res && res.success && Array.isArray(res.events)) ? res.events : [];
    const stats = (res && res.success && res.stats) ? res.stats : {
      totalAnalyzed: events.length,
      highRiskCount: 0,
      suspiciousCount: 0,
      unknownCount: 0,
      lowRiskCount: 0,
      blockedCount: 0
    };

    // Calculate Unique Protected Domains
    const uniqueDomains = new Set(
      events.map(e => e.domain).filter(d => d && d !== 'Browser Internal' && d !== 'unknown' && d !== 'Browser System')
    );

    // Update 4 Stat Cards
    statTotalAlerts.textContent = events.length;
    statProtectedDomains.textContent = uniqueDomains.size;
    statCriticalThreats.textContent = stats.highRiskCount + stats.blockedCount;

    // Severity Breakdown
    pctCritical.textContent = stats.highRiskCount + stats.blockedCount;
    pctHigh.textContent = stats.suspiciousCount;
    pctUnknown.textContent = stats.unknownCount;
    pctSafe.textContent = stats.lowRiskCount;

    // Analytics Tab Table
    if (analyticsTotal) analyticsTotal.textContent = events.length;
    if (analyticsHigh) analyticsHigh.textContent = stats.highRiskCount;
    if (analyticsSuspicious) analyticsSuspicious.textContent = stats.suspiciousCount;
    if (analyticsUnknown) analyticsUnknown.textContent = stats.unknownCount;
    if (analyticsSafe) analyticsSafe.textContent = stats.lowRiskCount;
    if (analyticsBlocked) analyticsBlocked.textContent = stats.blockedCount;

    // Update Incident Timeline Track
    timelineChainTrack.innerHTML = '';
    if (events.length === 0) {
      timelineChainTrack.innerHTML = `
        <div class="timeline-empty-msg">
          <span class="empty-dot"></span>
          <span>No security incidents recorded yet. Open a website or select a preset to log events.</span>
        </div>
      `;
    } else {
      events.slice(0, 5).forEach((evt) => {
        const node = document.createElement('div');
        node.className = 'chain-node';

        const isRed = evt.blocked || evt.riskLevel === 'HIGH_RISK';
        const isCyan = evt.riskLevel === 'UNKNOWN' || evt.riskLevel === 'SUSPICIOUS';

        let calloutClass = isRed ? 'red' : (isCyan ? 'cyan' : '');
        let calloutText = evt.blocked 
          ? 'Quarantined by Rule' 
          : (evt.riskLevel === 'HIGH_RISK' ? 'Malicious target flagged' : (evt.riskLevel === 'SUSPICIOUS' ? 'Heuristic anomaly detected' : 'Inspected clean'));

        const timeStr = new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        node.innerHTML = `
          <div class="chain-callout-card ${calloutClass}">${calloutText}</div>
          <div class="chain-dot-circle ${isRed ? 'red' : ''}"></div>
          <span class="chain-time-pill">${timeStr}</span>
        `;

        node.addEventListener('click', () => {
          renderAnalysis(evt, null);
        });

        timelineChainTrack.appendChild(node);
      });
    }

    // Populate Historical Vertical List (Tab 2)
    if (eventsVerticalList) {
      eventsVerticalList.innerHTML = '';
      if (events.length === 0) {
        eventsVerticalList.innerHTML = '<div class="empty-list-notice">No stored security events found.</div>';
      } else {
        events.forEach(evt => {
          const item = document.createElement('div');
          item.className = 'history-item-row';
          const time = new Date(evt.timestamp).toLocaleTimeString();
          item.innerHTML = `
            <div class="hist-left">
              <span class="hist-url" title="${evt.url}">${evt.domain || evt.url}</span>
              <span class="hist-time">${time} • ${evt.verdictReason || 'Inspected'}</span>
            </div>
            <span class="risk-pill ${evt.riskLevel || 'UNKNOWN'}">${evt.blocked ? 'BLOCKED' : (evt.riskLevel || 'UNKNOWN').replace('_', ' ')}</span>
          `;
          item.addEventListener('click', () => {
            renderAnalysis(evt, null);
            const overviewTab = document.querySelector('[data-tab="tab-overview"]');
            if (overviewTab) overviewTab.click();
          });
          eventsVerticalList.appendChild(item);
        });
      }
    }

    // Update Activity Graph Tooltip
    if (svgTooltipPill) {
      if (events.length > 0) {
        svgTooltipPill.textContent = `${events.length} Incidents Correlated`;
      } else {
        svgTooltipPill.textContent = 'Threat Baseline Active';
      }
    }
  }

  /**
   * 3. Protection Status Management & Real Operational State
   */
  async function loadProtectionStatus() {
    const res = await sendBackgroundMessage({ type: 'VERIFY_OPERATIONAL_STATE' });
    const isOnline = res && res.success && res.operational && res.protectionEnabled !== false;

    if (mainProtectionToggle) mainProtectionToggle.checked = isOnline;
    if (toggleShield) toggleShield.checked = isOnline;

    if (isOnline) {
      statProtectionStatus.textContent = 'VERIFIED';
      statProtectionStatus.className = 'stat-main-num text-sm highlight-cyan';
      statStatusPill.textContent = 'ONLINE';
      statStatusPill.className = 'stat-pill-cyan';
      if (integrityStatusPill) {
        integrityStatusPill.textContent = 'HEALTHY';
        integrityStatusPill.className = 'status-pill-cyan';
      }
      if (specRulesCount) specRulesCount.textContent = `${res.activeRulesCount || 0} Dynamic Rules Active`;
      if (specLastCheck) specLastCheck.textContent = 'Verified Online';
      if (specRepairResult) specRepairResult.textContent = 'Checksums Reconciled';
    } else {
      statProtectionStatus.textContent = 'STANDBY';
      statProtectionStatus.className = 'stat-main-num text-sm';
      statStatusPill.textContent = 'PAUSED';
      statStatusPill.className = 'stat-pill-muted';
      if (integrityStatusPill) {
        integrityStatusPill.textContent = 'STANDBY';
        integrityStatusPill.className = 'stat-pill-muted';
      }
      if (specLastCheck) specLastCheck.textContent = 'Paused by User';
    }
  }

  if (mainProtectionToggle) {
    mainProtectionToggle.addEventListener('change', async (e) => {
      const enabled = e.target.checked;
      await sendBackgroundMessage({ type: 'SET_PROTECTION_STATUS', enabled });
      await loadProtectionStatus();
    });
  }

  if (toggleShield) {
    toggleShield.addEventListener('change', async (e) => {
      const enabled = e.target.checked;
      await sendBackgroundMessage({ type: 'SET_PROTECTION_STATUS', enabled });
      await loadProtectionStatus();
    });
  }

  /**
   * 4. Self-Healing Integrity Check & Repair
   */
  if (btnRunIntegrity) {
    btnRunIntegrity.addEventListener('click', async () => {
      btnRunIntegrity.disabled = true;
      btnRunIntegrity.innerHTML = '<span>Verifying...</span>';

      const res = await sendBackgroundMessage({ type: 'CHECK_INTEGRITY', autoRepair: false });

      btnRunIntegrity.disabled = false;
      btnRunIntegrity.innerHTML = `
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2">
          <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
        </svg>
        <span>Run Integrity Diagnostic</span>
      `;

      if (integrityFeedback) {
        integrityFeedback.classList.remove('hidden');
        if (res && res.success && res.healthy) {
          integrityFeedback.textContent = `✓ Integrity Diagnostic Passed: All ${res.rulesCount} DeclarativeNetRequest rules reconciled & verified.`;
          integrityStatusPill.textContent = 'VERIFIED HEALTHY';
          integrityStatusPill.className = 'status-pill-cyan';
        } else {
          integrityFeedback.textContent = `Notice: Integrity check found ${res?.integrityReport?.missingCount || 0} missing rule(s). Click "Restore & Verify Rules" to heal.`;
          integrityStatusPill.textContent = 'RECOVERY NEEDED';
          integrityStatusPill.className = 'risk-pill SUSPICIOUS';
        }
      }
    });
  }

  if (btnRepairRules) {
    btnRepairRules.addEventListener('click', async () => {
      btnRepairRules.disabled = true;
      btnRepairRules.textContent = 'Healing Rules...';

      const res = await sendBackgroundMessage({ type: 'REPAIR_RULES' });

      btnRepairRules.disabled = false;
      btnRepairRules.textContent = 'Restore & Verify Rules';

      if (integrityFeedback) {
        integrityFeedback.classList.remove('hidden');
        if (res && res.success && res.verified) {
          integrityFeedback.textContent = `✓ Self-Healing Succeeded: Restored ${res.restoredCount || 0} missing rule(s). Total active: ${res.totalActiveRules}.`;
          integrityStatusPill.textContent = 'VERIFIED HEALTHY';
          integrityStatusPill.className = 'status-pill-cyan';
          await refreshLogsAndStats();
        } else {
          integrityFeedback.textContent = `Repair Warning: ${res?.error || 'Verification unconfirmed'}`;
        }
      }
    });
  }

  /**
   * 5. Clear History Modal
   */
  const triggerClearModal = () => {
    if (clearConfirmModal) clearConfirmModal.classList.remove('hidden');
  };

  if (btnClearTimeline) btnClearTimeline.addEventListener('click', triggerClearModal);
  if (btnQuickClear) btnQuickClear.addEventListener('click', triggerClearModal);
  if (btnWipeLogs) btnWipeLogs.addEventListener('click', triggerClearModal);

  if (btnModalCancel) {
    btnModalCancel.addEventListener('click', () => {
      if (clearConfirmModal) clearConfirmModal.classList.add('hidden');
    });
  }

  if (btnModalConfirm) {
    btnModalConfirm.addEventListener('click', async () => {
      if (clearConfirmModal) clearConfirmModal.classList.add('hidden');
      await sendBackgroundMessage({ type: 'CLEAR_EVENTS' });
      await refreshLogsAndStats();
    });
  }

  // Help info modal handlers
  if (btnRailHelp) {
    btnRailHelp.addEventListener('click', () => {
      if (helpInfoModal) helpInfoModal.classList.remove('hidden');
    });
  }

  if (btnModalHelpClose) {
    btnModalHelpClose.addEventListener('click', () => {
      if (helpInfoModal) helpInfoModal.classList.add('hidden');
    });
  }

  // INITIALIZATION
  await queryActiveTab();
  await loadProtectionStatus();
  await refreshLogsAndStats();
  await checkAiGatewayHealth();

  // Auto-scan current tab URL on open if accessible standard web URL
  if (currentTabUrl && !currentTabUrl.startsWith('chrome://') && !currentTabUrl.startsWith('about:') && !currentTabUrl.startsWith('chrome-extension://')) {
    await triggerScan(currentTabUrl);
    // Automatically trigger page links & navigation radar scan on active tab
    await triggerPageLinksScan();
  }
});
