// sentinelx-ai/extension/warning/warning.js
/**
 * SentinelX AI - Security Interstitial Warning Controller
 * Handles URL parameter extraction, threat telemetry presentation,
 * safe fallback navigation, and deliberate user bypass execution.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Extract URL parameters
  const params = new URLSearchParams(window.location.search);
  const targetUrl = params.get('url') || 'https://malicious-target.example';
  const targetDomain = params.get('domain') || 'malicious-target.example';
  const riskScore = parseInt(params.get('score'), 10) || 85;
  const riskLevel = params.get('level') || 'HIGH_RISK';
  const verdictReason = params.get('reason') || 'Critical heuristic risk signatures detected on target resource.';

  // DOM Elements
  const eventTimestamp = document.getElementById('event-timestamp');
  const warningRiskBadge = document.getElementById('warning-risk-badge');
  const warningTargetUrl = document.getElementById('warning-target-url');
  const warningVerdictText = document.getElementById('warning-verdict-text');
  const warningIndicatorsList = document.getElementById('warning-indicators-list');

  const btnBackSafety = document.getElementById('btn-back-safety');
  const btnToggleAdvanced = document.getElementById('btn-toggle-advanced');
  const technicalDrawer = document.getElementById('technical-drawer');

  const specScore = document.getElementById('spec-score');
  const specEventId = document.getElementById('spec-event-id');
  const btnProceedUnsafe = document.getElementById('btn-proceed-unsafe');

  // Populate Telemetry
  eventTimestamp.textContent = `INCIDENT TIMESTAMP: ${new Date().toISOString()}`;
  warningTargetUrl.textContent = targetUrl;
  warningVerdictText.textContent = verdictReason;

  warningRiskBadge.textContent = riskLevel.replace('_', ' ');
  warningRiskBadge.className = `threat-level-badge ${riskLevel}`;

  specScore.textContent = `${riskScore} / 100`;
  specEventId.textContent = `EVT_${Date.now().toString(36).toUpperCase()}`;

  // Big score readout + meter fill (UI only)
  const scoreBig = document.getElementById('warning-score-big');
  const scoreFill = document.getElementById('warning-score-fill');
  const safeScore = Math.max(0, Math.min(100, riskScore));
  if (scoreBig) scoreBig.textContent = String(safeScore);
  if (scoreFill) requestAnimationFrame(() => { scoreFill.style.width = `${Math.max(5, safeScore)}%`; });

  // Populate Detection Factors
  warningIndicatorsList.innerHTML = '';

  const defaultFactors = [];
  if (targetUrl.startsWith('http://')) {
    defaultFactors.push({
      severity: 'WARNING',
      text: 'Unencrypted HTTP Transport: Authentication credentials and transmitted data can be intercepted by intermediate nodes.'
    });
  }

  if (riskScore >= 50) {
    defaultFactors.push({
      severity: 'CRITICAL',
      text: 'Deceptive or Hostile Infrastructure: High probability of phishing kit, brand spoofing, or credential harvesting mechanism.'
    });
  } else if (riskLevel === 'UNKNOWN') {
    defaultFactors.push({
      severity: 'INFO',
      text: 'Zero-Trust Warning: Domain reputation cannot be substantiated. Site has no established trust baseline.'
    });
  } else {
    defaultFactors.push({
      severity: 'WARNING',
      text: 'Anomalous URI Pattern: Target syntax or host profile violates safe operational standards.'
    });
  }

  defaultFactors.forEach(factor => {
    const li = document.createElement('li');
    li.className = `indicator-item ${factor.severity}`;
    li.textContent = factor.text;
    warningIndicatorsList.appendChild(li);
  });

  // Action: Return to Safety
  btnBackSafety.addEventListener('click', () => {
    if (window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = 'about:blank';
    }
  });

  // Action: Toggle Technical Drawer
  btnToggleAdvanced.addEventListener('click', () => {
    const isHidden = technicalDrawer.classList.contains('hidden');
    if (isHidden) {
      technicalDrawer.classList.remove('hidden');
      btnToggleAdvanced.textContent = 'Hide Details';
    } else {
      technicalDrawer.classList.add('hidden');
      btnToggleAdvanced.textContent = 'Technical Details';
    }
  });

  // Action: Proceed Unsafe with Explicit Confirmation
  btnProceedUnsafe.addEventListener('click', () => {
    const confirmed = window.confirm(
      '⚠️ SECURITY NOTICE:\n\nAre you sure you want to bypass EDITH AI protection?\n\n' +
      'Visiting this site may result in immediate credential theft, session hijacking, or malicious payload execution.'
    );

    if (confirmed) {
      window.location.href = targetUrl;
    }
  });
});
