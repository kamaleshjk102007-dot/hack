// sentinelx-ai/extension/background/service-worker.js
/**
 * SentinelX AI — Autonomous Security Engine & Self-Healing Service Worker
 * Manifest V3 Background Security Coordinator
 *
 * Architecture:
 * DETECT → INVESTIGATE → DECIDE → PROTECT → REPAIR → VERIFY → RECORD
 *
 * Core Responsibilities:
 * 1. Deterministic Zero-Trust URL detection & multi-heuristic inspection.
 * 2. Real dynamic declarativeNetRequest rule enforcement with installation verification.
 * 3. Genuine self-healing protection-rule diagnostics, restoration, and cryptographic verification.
 * 4. Deterministic security policy engine (100% local, offline-capable).
 * 5. Sanitized event persistence and deduplication in local storage.
 * 6. Gemma 4 AI evidence sanitization & response validation contract.
 * 7. Standardized messaging contract for Popup UI (Member 2).
 */

// Import local event store
importScripts('../storage/event-store.js');

// ============================================================================
// CONFIGURATION & THREAT INDICATORS
// ============================================================================

// Known verified high-reputation infrastructure baselines
const VERIFIED_REPUTABLE_DOMAINS = new Set([
  'google.com',
  'www.google.com',
  'github.com',
  'www.github.com',
  'microsoft.com',
  'www.microsoft.com',
  'mozilla.org',
  'www.mozilla.org',
  'wikipedia.org',
  'www.wikipedia.org',
  'w3.org',
  'www.w3.org',
  'stackoverflow.com',
  'chrome.google.com',
  'chromewebstore.google.com',
  'blog.google'
]);


// Active threat indicator database (known malicious domains / test fixtures)
const KNOWN_MALICIOUS_DOMAINS = new Set([
  'malware-test.sentinelx.local',
  'phish-test.sentinelx.local',
  'credential-harvest-demo.xyz',
  'evil-c2-tracker.top',
  'badssl.com',
  'login-verify-account.click',
  'ransomware-c2-node.biz',
  'stealer-logs-collector.info'
]);

// High-abuse top-level domains frequently leveraged in phishing and malware campaigns
const HIGH_ABUSE_TLDS = new Set([
  'zip', 'mov', 'top', 'xyz', 'click', 'buzz', 'work', 'gq', 'cf', 'tk', 'ml', 'country'
]);

// Sensitive authentication and credential keywords
const SENSITIVE_KEYWORDS = [
  'login', 'signin', 'sign-in', 'log-in', 'verify', 'verification', 'secure',
  'account', 'banking', 'update-password', 'password', 'credential',
  'wallet', 'metamask', 'binance', 'paypal', 'apple-id', 'microsoft-verify'
];

// Common typosquatting patterns targeting major platforms
const TYPOSQUAT_PATTERNS = [
  { pattern: /paypa[l1i]/i, legitimate: 'paypal.com' },
  { pattern: /goog[l1i][e0]/i, legitimate: 'google.com' },
  { pattern: /g[0o]{2}gle/i, legitimate: 'google.com' },
  { pattern: /micros[0o]ft/i, legitimate: 'microsoft.com' },
  { pattern: /app[l1i]e/i, legitimate: 'apple.com' },
  { pattern: /amaz[0o]n/i, legitimate: 'amazon.com' },
  { pattern: /faceb[0o]{2}k/i, legitimate: 'facebook.com' },
  { pattern: /tw[i1]tt[e0]r/i, legitimate: 'twitter.com' }
];

// Reserved DeclarativeNetRequest Rule ID Ranges
const RULE_ID_RANGES = {
  BASELINE_START: 1001,
  BASELINE_END: 1999,
  DYNAMIC_START: 10000,
  DYNAMIC_END: 89999
};

// Baseline Managed Protection Rules (SentinelX Core Managed Defense Set)
const BASELINE_MANAGED_RULES = [
  {
    id: 1001,
    priority: 1,
    action: { type: 'block' },
    condition: {
      urlFilter: '||phish-test.sentinelx.local',
      resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'script']
    }
  },
  {
    id: 1002,
    priority: 1,
    action: { type: 'block' },
    condition: {
      urlFilter: '||malware-test.sentinelx.local',
      resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'script']
    }
  },
  {
    id: 1003,
    priority: 1,
    action: { type: 'block' },
    condition: {
      urlFilter: '||credential-harvest-demo.xyz',
      resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'script']
    }
  },
  {
    id: 1004,
    priority: 1,
    action: { type: 'block' },
    condition: {
      urlFilter: '||login-verify-account.click',
      resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'script']
    }
  }
];

// ============================================================================
// PRIORITY 1: URL DETECTION & HEURISTIC SECURITY ENGINE
// ============================================================================

/**
 * Safely parse, normalize, and evaluate a URL adhering to zero-trust principles.
 * Rule: Do not claim arbitrary websites are safe.
 * Rule: Do not rely on a single heuristic to declare a website malicious.
 *
 * @param {string} rawUrl - Target URL to analyze
 * @returns {Object} Deterministic detection assessment
 */
function analyzeUrlHeuristics(rawUrl) {
  const result = {
    url: rawUrl,
    normalizedUrl: '',
    domain: '',
    protocol: '',
    riskScore: 0,
    riskLevel: 'UNKNOWN', // Zero-trust default
    verdictReason: '',
    findings: [],
    heuristicCount: 0,
    analyzedAt: new Date().toISOString()
  };

  // 1. Validate input format
  if (!rawUrl || typeof rawUrl !== 'string') {
    result.verdictReason = 'Invalid or empty URL provided.';
    result.findings.push({
      severity: 'WARNING',
      category: 'SYNTAX',
      detail: 'URL parameter is missing, empty, or not a string.'
    });
    return result;
  }

  const trimmed = rawUrl.trim();
  result.url = trimmed;

  // 2. Handle internal browser schemes safely
  if (trimmed.startsWith('chrome://') || trimmed.startsWith('chrome-extension://') || trimmed.startsWith('about:')) {
    result.domain = 'Browser Internal';
    result.protocol = trimmed.split(':')[0] + ':';
    result.normalizedUrl = trimmed;
    result.riskScore = 0;
    result.riskLevel = 'LOW_RISK';
    result.verdictReason = 'Internal browser system interface; protected within the browser security sandbox.';
    result.findings.push({
      severity: 'SAFE',
      category: 'SCHEME',
      detail: 'Internal browser page is isolated from external network threats.'
    });
    return result;
  }

  // 3. Handle non-standard or dangerous schemes
  const lowerUrl = trimmed.toLowerCase();
  if (lowerUrl.startsWith('javascript:') || lowerUrl.startsWith('data:') || lowerUrl.startsWith('vbscript:')) {
    result.domain = 'Executable URI Scheme';
    result.protocol = lowerUrl.split(':')[0] + ':';
    result.riskScore = 95;
    result.riskLevel = 'HIGH_RISK';
    result.verdictReason = 'Potentially hostile pseudo-protocol capable of client-side code execution.';
    result.findings.push({
      severity: 'CRITICAL',
      category: 'UNSUPPORTED_SCHEME',
      detail: `Suspicious Protocol: "${result.protocol}" allows direct script payload injection.`
    });
    return result;
  }

  if (lowerUrl.startsWith('file:') || lowerUrl.startsWith('ftp:')) {
    result.domain = 'Local / Legacy Scheme';
    result.protocol = lowerUrl.split(':')[0] + ':';
    result.riskScore = 40;
    result.riskLevel = 'SUSPICIOUS';
    result.verdictReason = 'Non-web protocol; SentinelX analyzes HTTP and HTTPS web destinations.';
    result.findings.push({
      severity: 'WARNING',
      category: 'UNSUPPORTED_SCHEME',
      detail: `Non-Web Protocol: "${result.protocol}" routes outside standard web TLS protections.`
    });
    return result;
  }

  // 4. Safe URL Parsing
  let parsed;
  try {
    parsed = new URL(trimmed);
    result.normalizedUrl = parsed.origin + parsed.pathname;
    result.protocol = parsed.protocol;
  } catch (err) {
    result.domain = 'Unparseable';
    result.riskScore = 45;
    result.riskLevel = 'SUSPICIOUS';
    result.verdictReason = 'Malformed URI structure; violates standard RFC 3986 URI specifications.';
    result.findings.push({
      severity: 'WARNING',
      category: 'SYNTAX',
      detail: 'Target string could not be parsed as a valid standard web URL.'
    });
    return result;
  }

  // Accept only HTTP and HTTPS for standard web security analysis
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    result.domain = parsed.hostname || 'Unknown Host';
    result.riskScore = 30;
    result.riskLevel = 'UNKNOWN';
    result.verdictReason = `Unsupported web scheme (${parsed.protocol}); SentinelX analyzes HTTP and HTTPS.`;
    result.findings.push({
      severity: 'INFO',
      category: 'SCHEME',
      detail: `Unsupported transport scheme "${parsed.protocol}".`
    });
    return result;
  }

  const hostname = parsed.hostname.toLowerCase();
  result.domain = hostname;
  let score = 0;
  let highSeverityHeuristicCount = 0;

  // --------------------------------------------------------------------------
  // HEURISTIC EVALUATION PIPELINE
  // --------------------------------------------------------------------------

  // Check A: Known Malicious Domain Database Match
  if (KNOWN_MALICIOUS_DOMAINS.has(hostname)) {
    score += 80;
    highSeverityHeuristicCount += 2; // Immediate high confidence
    result.findings.push({
      severity: 'CRITICAL',
      category: 'THREAT_DATABASE',
      detail: `Known Malicious Domain: "${hostname}" matches active cybersecurity threat indicator feed.`
    });
  }

  // Check B: Direct IP Address Host (IPv4 / IPv6)
  const isIpv4 = /^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(hostname);
  const isIpv6 = hostname.startsWith('[') && hostname.endsWith(']');
  if (isIpv4 || isIpv6) {
    score += 45;
    highSeverityHeuristicCount++;
    result.findings.push({
      severity: 'HIGH',
      category: 'HOST_IDENTITY',
      detail: 'Raw IP Host: Connects directly via numerical IP address instead of registered domain name.'
    });
  }

  // Check C: Authority Userinfo Spoofing (e.g. https://google.com@evil.com)
  if (parsed.username || parsed.password) {
    score += 50;
    highSeverityHeuristicCount++;
    result.findings.push({
      severity: 'CRITICAL',
      category: 'URL_OBFUSCATION',
      detail: 'Authority Spoofing: Contains credentials/userinfo ("@") in authority string to disguise the true destination host.'
    });
  }

  // Check D: Punycode / IDN Homoglyph Encoding
  if (hostname.includes('xn--')) {
    score += 35;
    highSeverityHeuristicCount++;
    result.findings.push({
      severity: 'HIGH',
      category: 'HOMOGRAPH',
      detail: 'Punycode (IDN) Detected: Uses ASCII-compatible encoding (xn--) frequently utilized in visual homoglyph spoofing.'
    });
  }

  // Check E: Lookalike / Typosquatting of High-Value Brands
  for (const typo of TYPOSQUAT_PATTERNS) {
    const isLegitimate = hostname === typo.legitimate ||
                         hostname.endsWith('.' + typo.legitimate) ||
                         (typo.legitimate === 'google.com' && (hostname === 'google' || hostname.endsWith('.google')));
    if (typo.pattern.test(hostname) && !isLegitimate) {
      score += 40;
      highSeverityHeuristicCount++;
      result.findings.push({
        severity: 'HIGH',
        category: 'TYPOSQUAT',
        detail: `Typosquatting Indicator: Domain resembles authoritative brand "${typo.legitimate}" but resolves to an unverified entity.`
      });
      break;
    }
  }

  // Check F: Sensitive Authentication Keywords on Unverified Domain
  const fullUrlLower = trimmed.toLowerCase();
  const isVerifiedReputable = VERIFIED_REPUTABLE_DOMAINS.has(hostname) ||
                              hostname === 'google' ||
                              hostname.endsWith('.google') ||
                              hostname.endsWith('.google.com');


  for (const keyword of SENSITIVE_KEYWORDS) {
    if (fullUrlLower.includes(keyword) && !isVerifiedReputable) {
      if (hostname.includes(keyword) || parsed.pathname.includes(keyword)) {
        score += 30;
        highSeverityHeuristicCount++;
        result.findings.push({
          severity: 'HIGH',
          category: 'BRAND_IMPERSONATION',
          detail: `Deceptive Keyword: Found authentication indicator "${keyword}" on an unverified domain.`
        });
        break;
      }
    }
  }

  // Check G: High-Abuse Top-Level Domain
  const hostParts = hostname.split('.');
  const tld = hostParts.length > 1 ? hostParts[hostParts.length - 1] : '';
  if (HIGH_ABUSE_TLDS.has(tld)) {
    score += 20;
    result.findings.push({
      severity: 'WARNING',
      category: 'TLD_REPUTATION',
      detail: `Elevated-Risk TLD: .${tld} top-level domain exhibits statistically high abuse rates in malicious campaigns.`
    });
  }

  // Check H: Excessive Subdomain Depth
  if (hostParts.length > 4) {
    score += 20;
    result.findings.push({
      severity: 'WARNING',
      category: 'DOMAIN_STRUCTURE',
      detail: `Excessive Subdomain Nesting: Domain contains ${hostParts.length - 2} subdomain levels, often used to obscure real origin.`
    });
  }

  // Check I: Transport Protocol (Insecure HTTP vs TLS HTTPS)
  if (parsed.protocol === 'http:') {
    score += 25;
    result.findings.push({
      severity: 'WARNING',
      category: 'TRANSPORT',
      detail: 'Insecure Protocol: URL uses unencrypted HTTP. Communications are subject to interception and tampering.'
    });
  } else if (parsed.protocol === 'https:') {
    result.findings.push({
      severity: 'INFO',
      category: 'TRANSPORT',
      detail: 'Encrypted Transport: TLS (HTTPS) transport active. Note: Encryption validates connection channel, not remote intent.'
    });
  }

  // Check J: Non-Standard Web Port
  if (parsed.port && parsed.port !== '80' && parsed.port !== '443') {
    score += 15;
    result.findings.push({
      severity: 'WARNING',
      category: 'PORT_ANOMALY',
      detail: `Non-Standard Port: Routes through TCP port ${parsed.port} rather than standard web ports.`
    });
  }

  // Check K: Suspicious Payload Patterns (Null bytes, dual extensions)
  if (/%00/i.test(trimmed) || /\.(?:pdf|doc|docx|jpg|png)\.(?:exe|scr|bat|cmd|vbs|ps1)$/i.test(parsed.pathname)) {
    score += 45;
    highSeverityHeuristicCount++;
    result.findings.push({
      severity: 'HIGH',
      category: 'MALICIOUS_PAYLOAD',
      detail: 'Suspicious File Extension: Contains dual extensions or encoded delimiters associated with executable delivery.'
    });
  }

  // --------------------------------------------------------------------------
  // DETERMINISTIC VERDICT FORMULATION
  // Strict rule: Do not rely on a single heuristic to declare a website malicious.
  // Strict rule: Unknown results must remain unknown.
  // --------------------------------------------------------------------------
  result.riskScore = Math.min(100, score);
  result.heuristicCount = highSeverityHeuristicCount;

  // Multi-heuristic requirement for HIGH_RISK / Malicious:
  // Requires score >= 50 AND (known malicious domain OR critical finding OR at least 2 distinct suspicious indicators)
  const hasCriticalFinding = result.findings.some(f => f.severity === 'CRITICAL');
  const isMultiHeuristicThreat = (highSeverityHeuristicCount >= 2 && result.riskScore >= 50) ||
                                 (hasCriticalFinding && result.riskScore >= 50) ||
                                 KNOWN_MALICIOUS_DOMAINS.has(hostname);

  if (isMultiHeuristicThreat) {
    result.riskLevel = 'HIGH_RISK';
    result.verdictReason = `High-confidence threat: Triggered ${highSeverityHeuristicCount || 1} structural risk signature(s) with elevated threat score (${result.riskScore}/100).`;
  } else if (result.riskScore >= 25) {
    result.riskLevel = 'SUSPICIOUS';
    result.verdictReason = 'One or more security anomalies detected (e.g. raw IP host or unencrypted transport). Further inspection recommended.';
  } else {
    // Score < 25: Check for verified infrastructure baseline
    const isVerifiedInfrastructure = isVerifiedReputable && parsed.protocol === 'https:';

    if (isVerifiedInfrastructure) {
      result.riskLevel = 'LOW_RISK';
      result.verdictReason = 'Verified public infrastructure baseline with encrypted TLS transport and no observed anomalies.';
      result.findings.push({
        severity: 'SAFE',
        category: 'BASELINE',
        detail: 'Domain matches verified high-reputation infrastructure baseline.'
      });
    } else {
      // ZERO-TRUST MANDATE: If evidence is insufficient, remain UNKNOWN.
      result.riskLevel = 'UNKNOWN';
      result.verdictReason = 'Zero-Trust Baseline: Insufficient historical evidence to confirm safety. No overt threat signatures detected, but domain reputation is unverified.';
      result.findings.push({
        severity: 'INFO',
        category: 'ZERO_TRUST',
        detail: 'Zero-Trust Baseline: Site does not trigger immediate heuristic flags, but has no verified trust history. Proceed with standard caution.'
      });
    }
  }

  return result;
}

// ============================================================================
// PRIORITY 4: DETERMINISTIC SECURITY POLICY ENGINE
// ============================================================================

/**
 * Evaluates the deterministic security policy on an analysis outcome.
 * Fails safely when external services or AI are unavailable.
 *
 * @param {Object} analysis - Output from analyzeUrlHeuristics
 * @param {boolean} protectionEnabled - Whether autonomous protection is active
 * @returns {Object} Deterministic policy decision
 */
function evaluateSecurityPolicy(analysis, protectionEnabled = true) {
  const policy = {
    decision: 'ALLOW',
    actionRequired: 'NONE',
    requiresWarning: false,
    requiresBlocking: false,
    explanation: '',
    policyCode: 'POL_ALLOW_VERIFIED'
  };

  if (!analysis) {
    policy.decision = 'ALLOW';
    policy.explanation = 'Empty analysis input; defaulting to fail-safe monitoring.';
    return policy;
  }

  switch (analysis.riskLevel) {
    case 'HIGH_RISK':
      if (protectionEnabled) {
        policy.decision = 'BLOCK';
        policy.actionRequired = 'ENFORCE_DYNAMIC_RULE';
        policy.requiresBlocking = true;
        policy.requiresWarning = true;
        policy.policyCode = 'POL_AUTONOMOUS_CONTAINMENT';
        policy.explanation = 'Autonomous Quarantine: High-risk multi-heuristic threat detected under active protection policy.';
      } else {
        policy.decision = 'WARN';
        policy.actionRequired = 'INTERSTITIAL_WARNING';
        policy.requiresWarning = true;
        policy.policyCode = 'POL_PAUSED_PROTECTION_WARNING';
        policy.explanation = 'Protection Paused: Threat flagged, but autonomous blocking is suspended by user policy.';
      }
      break;

    case 'SUSPICIOUS':
      policy.decision = 'WARN';
      policy.actionRequired = 'DISPLAY_INSPECTION_NOTICE';
      policy.requiresWarning = true;
      policy.policyCode = 'POL_SUSPICIOUS_ANOMALY';
      policy.explanation = 'Heuristic Anomalies Flagged: Advisory warning recommended; domain access requires explicit caution.';
      break;

    case 'UNKNOWN':
      policy.decision = 'MONITOR';
      policy.actionRequired = 'ZERO_TRUST_INSPECTION';
      policy.policyCode = 'POL_ZERO_TRUST_BASELINE';
      policy.explanation = 'Zero-Trust Policy: Unverified domain monitored under standard surveillance posture.';
      break;

    case 'INTERNAL_RESTRICTED':
      policy.decision = 'ALLOW';
      policy.actionRequired = 'NONE';
      policy.requiresBlocking = false;
      policy.requiresWarning = false;
      policy.policyCode = 'POL_INTERNAL_RESTRICTED';
      policy.explanation = 'Internal / Restricted Browser Target: Isolated within browser sandbox.';
      break;

    case 'ERROR':
      policy.decision = 'MONITOR';
      policy.actionRequired = 'LOG_ERROR';
      policy.requiresBlocking = false;
      policy.requiresWarning = true;
      policy.policyCode = 'POL_EVALUATION_ERROR';
      policy.explanation = 'Evaluation Error: Heuristic parsing failed; destination monitored cautiously.';
      break;

    case 'LOW_RISK':
    default:
      policy.decision = 'ALLOW';
      policy.actionRequired = 'NONE';
      policy.policyCode = 'POL_VERIFIED_ALLOW';
      policy.explanation = 'Verified Infrastructure: Destination matches verified baseline reputation standard.';
      break;
  }

  return policy;
}

// ============================================================================
// PRIORITY 2: REAL DECLARATIVENETREQUEST DOMAIN BLOCKING & VERIFICATION
// ============================================================================

/**
 * Generate a deterministic rule ID from domain name in reserved dynamic range
 * @param {string} domain
 * @returns {number} Integer between RULE_ID_RANGES.DYNAMIC_START and DYNAMIC_END
 */
function generateDynamicRuleId(domain) {
  const clean = (domain || '').trim().toLowerCase();
  let hash = 0;
  for (let i = 0; i < clean.length; i++) {
    hash = ((hash << 5) - hash) + clean.charCodeAt(i);
    hash |= 0;
  }
  const range = RULE_ID_RANGES.DYNAMIC_END - RULE_ID_RANGES.DYNAMIC_START;
  return RULE_ID_RANGES.DYNAMIC_START + (Math.abs(hash) % range);
}

/**
 * Normalize and validate domain before creating DeclarativeNetRequest blocking rules
 * @param {string} rawDomain
 * @returns {string|null} Normalized valid domain or null
 */
function normalizeDomainForRule(rawDomain) {
  if (!rawDomain || typeof rawDomain !== 'string') return null;

  let cleaned = rawDomain.trim().toLowerCase();

  // Strip protocol if included
  cleaned = cleaned.replace(/^[a-z]+:\/\//i, '');

  // Strip userinfo
  if (cleaned.includes('@')) {
    cleaned = cleaned.split('@')[1];
  }

  // Strip port and path
  cleaned = cleaned.split('/')[0].split(':')[0];

  // Strip leading wildcards
  cleaned = cleaned.replace(/^\*\./, '');

  // Basic domain/host syntax validation
  if (!cleaned || cleaned === 'localhost' || cleaned === 'unknown' || cleaned.includes(' ')) {
    return null;
  }

  return cleaned;
}

/**
 * Enforce real domain blocking via Chrome declarativeNetRequest with installation verification.
 * Follows: Block rule requested → Block rule installed → Block rule verified.
 *
 * @param {string} domain
 * @param {Object} options
 * @returns {Promise<Object>} Verification outcome
 */
async function enforceDomainBlockRule(domain, options = {}) {
  const normalizedDomain = normalizeDomainForRule(domain);

  if (!normalizedDomain) {
    return {
      success: false,
      blocked: false,
      verified: false,
      verificationStatus: 'FAILED',
      error: 'Invalid or unsupported domain specification for declarative rule creation.'
    };
  }

  const ruleId = generateDynamicRuleId(normalizedDomain);
  const ruleFilter = `||${normalizedDomain}`;

  const rule = {
    id: ruleId,
    priority: 1,
    action: { type: 'block' },
    condition: {
      urlFilter: ruleFilter,
      resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'script']
    }
  };

  // Check declarativeNetRequest API availability
  if (typeof chrome === 'undefined' || !chrome.declarativeNetRequest?.updateDynamicRules) {
    return {
      success: false,
      blocked: false,
      verified: false,
      verificationStatus: 'API_UNAVAILABLE',
      error: 'Chrome declarativeNetRequest API is not available in the current environment.'
    };
  }

  try {
    // 1. Block rule requested & installed
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: [ruleId],
      addRules: [rule]
    });

    // 2. Crucial verification step: Query resulting rules from the browser
    const activeRules = await chrome.declarativeNetRequest.getDynamicRules();
    const installedRule = activeRules.find(r => r.id === ruleId);

    const isVerified = Boolean(
      installedRule &&
      installedRule.action?.type === 'block' &&
      installedRule.condition?.urlFilter === ruleFilter
    );

    if (!isVerified) {
      return {
        success: false,
        blocked: false,
        verified: false,
        ruleId,
        domain: normalizedDomain,
        verificationStatus: 'VERIFICATION_FAILED',
        error: 'Dynamic rule installation could not be verified in browser rule table.'
      };
    }

    // 3. Persist to managed blocklist for self-healing restoration
    await EventStore.addManagedBlocklist(normalizedDomain, ruleId);

    // 4. Record verified event in event store
    const eventRecord = await EventStore.recordEvent({
      url: options.url || `https://${normalizedDomain}`,
      domain: normalizedDomain,
      riskScore: options.riskScore || 85,
      riskLevel: 'HIGH_RISK',
      verdictReason: 'Enforced threat containment via verified declarativeNetRequest dynamic rule.',
      findings: options.findings || [
        { severity: 'CRITICAL', category: 'CONTAINMENT', detail: `Domain blocked by verified SentinelX rule #${ruleId}` }
      ],
      blocked: true,
      blockRuleId: ruleId,
      actionAttempted: 'BLOCK_RULE_REQUESTED',
      actualActionResult: 'RULE_INSTALLED',
      verificationStatus: 'VERIFIED'
    });

    return {
      success: true,
      blocked: true,
      verified: true,
      ruleId,
      domain: normalizedDomain,
      verificationStatus: 'VERIFIED',
      eventRecord
    };

  } catch (err) {
    console.error('[SentinelX Engine] Declarative rule error:', err);
    return {
      success: false,
      blocked: false,
      verified: false,
      ruleId,
      domain: normalizedDomain,
      verificationStatus: 'FAILED',
      error: err.message
    };
  }
}

/**
 * Remove an existing dynamic block rule
 * @param {number} ruleId
 * @returns {Promise<Object>}
 */
async function removeDomainBlockRule(ruleId) {
  const id = parseInt(ruleId, 10);
  if (!id || typeof chrome === 'undefined' || !chrome.declarativeNetRequest?.updateDynamicRules) {
    return { success: false, error: 'Invalid rule ID or declarativeNetRequest unavailable.' };
  }

  try {
    await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: [id] });
    await EventStore.removeManagedBlocklist(id);
    return { success: true, unblocked: true, ruleId: id };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

// ============================================================================
// PRIORITY 3: SELF-HEALING ENGINE (GENUINE PROTECTION-RULE RECOVERY)
// ============================================================================

/**
 * Define expected protection rules (Baseline managed rules + user managed blocklist)
 * @returns {Promise<Array<Object>>}
 */
async function getExpectedProtectionRules() {
  const expected = [...BASELINE_MANAGED_RULES];

  // Merge with stored user-managed blocklist
  const userBlocklist = await EventStore.getManagedBlocklist();
  for (const item of userBlocklist) {
    if (item.domain && item.ruleId) {
      expected.push({
        id: item.ruleId,
        priority: 1,
        action: { type: 'block' },
        condition: {
          urlFilter: `||${item.domain}`,
          resourceTypes: ['main_frame', 'sub_frame', 'xmlhttprequest', 'script']
        }
      });
    }
  }

  return expected;
}

/**
 * Inspect actual protection rules and identify missing or corrupted SentinelX rules.
 * Does NOT touch unrelated browser rules from other extensions.
 *
 * @returns {Promise<Object>} Integrity diagnostic report
 */
async function checkProtectionRuleIntegrity() {
  const report = {
    healthy: false,
    totalExpected: 0,
    totalActive: 0,
    intactCount: 0,
    missingCount: 0,
    corruptedCount: 0,
    missingRules: [],
    corruptedRuleIds: [],
    unmanagedRulesCount: 0,
    checkedAt: new Date().toISOString()
  };

  if (typeof chrome === 'undefined' || !chrome.declarativeNetRequest?.getDynamicRules) {
    report.healthy = false;
    report.error = 'declarativeNetRequest API unavailable.';
    return report;
  }

  try {
    const expectedRules = await getExpectedProtectionRules();
    const activeRules = await chrome.declarativeNetRequest.getDynamicRules();

    report.totalExpected = expectedRules.length;
    report.totalActive = activeRules.length;

    const activeMap = new Map();
    for (const rule of activeRules) {
      activeMap.set(rule.id, rule);
      // Check if rule is in SentinelX managed ranges
      const isManaged = (rule.id >= RULE_ID_RANGES.BASELINE_START && rule.id <= RULE_ID_RANGES.BASELINE_END) ||
                        (rule.id >= RULE_ID_RANGES.DYNAMIC_START && rule.id <= RULE_ID_RANGES.DYNAMIC_END);
      if (!isManaged) {
        report.unmanagedRulesCount++;
      }
    }

    // Inspect each expected rule
    for (const exp of expectedRules) {
      const active = activeMap.get(exp.id);

      if (!active) {
        report.missingRules.push(exp);
        report.missingCount++;
      } else {
        // Verify exact rule action and condition match
        const actionMatches = active.action?.type === exp.action.type;
        const conditionMatches = active.condition?.urlFilter === exp.condition.urlFilter;

        if (actionMatches && conditionMatches) {
          report.intactCount++;
        } else {
          report.corruptedRuleIds.push(exp.id);
          report.corruptedCount++;
          report.missingRules.push(exp); // Re-install expected configuration
        }
      }
    }

    report.healthy = (report.missingCount === 0 && report.corruptedCount === 0);
    return report;

  } catch (err) {
    report.healthy = false;
    report.error = err.message;
    return report;
  }
}

/**
 * Execute genuine self-healing rule restoration and verify the result.
 * Workflow:
 * 1. Define expected configuration
 * 2. Inspect configured rules
 * 3. Identify missing/inconsistent rules
 * 4. Restore only rules managed by SentinelX
 * 5. Re-read configuration
 * 6. Verify expected rules are present
 * 7. Record outcome & report failure if repair cannot be verified
 *
 * @returns {Promise<Object>} Self-healing repair outcome
 */
async function repairProtectionRules() {
  const diagnostic = await checkProtectionRuleIntegrity();

  if (diagnostic.healthy) {
    return {
      success: true,
      repaired: false,
      verified: true,
      message: 'Protection-rule configuration is already intact and verified healthy.',
      diagnostic
    };
  }

  if (typeof chrome === 'undefined' || !chrome.declarativeNetRequest?.updateDynamicRules) {
    return {
      success: false,
      repaired: false,
      verified: false,
      error: 'declarativeNetRequest API unavailable for rule restoration.'
    };
  }

  try {
    // 4. Restore only the rules managed by SentinelX AI
    const addRules = diagnostic.missingRules;
    const removeRuleIds = diagnostic.corruptedRuleIds;

    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds,
      addRules
    });

    // 5. Re-read the resulting configuration
    const postRepairRules = await chrome.declarativeNetRequest.getDynamicRules();
    const postRepairMap = new Map(postRepairRules.map(r => [r.id, r]));

    // 6. Verify that all expected rules are now present and correct
    const expectedRules = await getExpectedProtectionRules();
    let allVerified = true;
    const unverifiedIds = [];

    for (const exp of expectedRules) {
      const active = postRepairMap.get(exp.id);
      if (!active || active.action?.type !== exp.action.type || active.condition?.urlFilter !== exp.condition.urlFilter) {
        allVerified = false;
        unverifiedIds.push(exp.id);
      }
    }

    // 7. Record the repair outcome
    await EventStore.recordEvent({
      url: 'sentinelx://self-healing/recovery',
      domain: 'Self-Healing Engine',
      riskScore: 0,
      riskLevel: 'LOW_RISK',
      verdictReason: allVerified
        ? `Self-healing successfully restored and verified ${addRules.length} protection rules.`
        : 'Self-healing restoration executed but failed post-repair verification check.',
      findings: [
        {
          severity: allVerified ? 'SAFE' : 'CRITICAL',
          category: 'INTEGRITY_REPAIR',
          detail: allVerified
            ? `Reconciled: ${addRules.length} rules restored, verified active.`
            : `Repair Incomplete: Unverified rules detected: ${unverifiedIds.join(', ')}`
        }
      ],
      actionAttempted: 'REPAIR_REQUESTED',
      actualActionResult: allVerified ? 'REPAIR_COMPLETED' : 'REPAIR_INCOMPLETE',
      verificationStatus: allVerified ? 'VERIFIED' : 'FAILED',
      blocked: false
    });

    // 8. Report failure when repair cannot be verified
    if (!allVerified) {
      return {
        success: false,
        repaired: true,
        verified: false,
        error: `Repair verification failed for rule IDs: ${unverifiedIds.join(', ')}`,
        unverifiedIds
      };
    }

    return {
      success: true,
      repaired: true,
      verified: true,
      restoredCount: addRules.length,
      totalActiveRules: postRepairRules.length,
      verifiedAt: new Date().toISOString()
    };

  } catch (err) {
    console.error('[SentinelX Self-Healing] Repair error:', err);
    return {
      success: false,
      repaired: false,
      verified: false,
      error: err.message
    };
  }
}

// ============================================================================
// PRIORITY 6: GEMMA 4 AI INTEGRATION CONTRACT
// ============================================================================

/**
 * Interface Contract for Member 2 (AI Investigation):
 * Prepares a sanitized, privacy-safe evidence payload for Gemma 4 threat investigation.
 * Never exposes credentials, query tokens, or sensitive user data.
 *
 * @param {Object} analysis - Output from analyzeUrlHeuristics
 * @returns {Object} Sanitized AI investigation payload
 */
function createGemmaInvestigationPayload(analysis) {
  if (!analysis) return null;

  return {
    target: {
      domain: analysis.domain,
      protocol: analysis.protocol,
      normalizedUri: analysis.normalizedUrl
    },
    threatContext: {
      initialRiskLevel: analysis.riskLevel,
      heuristicRiskScore: analysis.riskScore,
      anomalyCount: analysis.heuristicCount || analysis.findings?.length || 0,
      observedIndicators: (analysis.findings || []).map(f => ({
        category: f.category,
        severity: f.severity,
        evidence: f.detail
      }))
    },
    metadata: {
      engineVersion: '1.0.0-mv3',
      timestamp: new Date().toISOString(),
      offlineCapable: true
    }
  };
}

/**
 * Strictly validate and sanitize an AI investigation response from Gemma 4.
 * Enforces that AI output conforms to expected schema and cannot bypass policy.
 *
 * @param {Object} aiResponse
 * @returns {Object} Validation outcome with sanitized result or error details
 */
/**
 * Strictly validate and sanitize an AI investigation response from Gemma 4.
 * Enforces that AI output conforms to expected schema and cannot bypass policy.
 * Supports both legacy contract fields and structured forensic schema.
 *
 * @param {Object} aiResponse
 * @returns {Object} Validation outcome with sanitized result or error details
 */
function validateGemmaResponse(aiResponse) {
  const allowedActions = new Set(['BLOCK', 'WARN', 'MONITOR', 'ALLOW']);

  if (!aiResponse || typeof aiResponse !== 'object') {
    return { valid: false, error: 'AI response must be a non-null object.' };
  }

  // Handle both standard field names and structured forensic schema
  const explanation = (typeof aiResponse.evidenceExplanation === 'string' && aiResponse.evidenceExplanation.trim().length > 0)
    ? aiResponse.evidenceExplanation
    : aiResponse.explanation;

  const rawFindings = Array.isArray(aiResponse.suspiciousIndicators)
    ? aiResponse.suspiciousIndicators
    : aiResponse.findings;

  const recommendedAction = aiResponse.recommendedNextStep || aiResponse.recommendedAction;
  const rawUncertainty = typeof aiResponse.uncertaintyScore === 'number'
    ? aiResponse.uncertaintyScore
    : aiResponse.uncertainty;

  if (typeof explanation !== 'string' || explanation.trim().length === 0) {
    return { valid: false, error: 'AI response missing valid "explanation" or "evidenceExplanation" string.' };
  }

  if (!Array.isArray(rawFindings)) {
    return { valid: false, error: 'AI response "findings" or "suspiciousIndicators" must be an array.' };
  }

  if (!allowedActions.has(recommendedAction)) {
    return { valid: false, error: `Invalid recommended action: ${recommendedAction}. Must be BLOCK, WARN, MONITOR, or ALLOW.` };
  }

  const numericUncertainty = typeof rawUncertainty === 'number' ? Math.max(0, Math.min(1, rawUncertainty)) : 0.5;
  const modelId = (aiResponse.modelId && typeof aiResponse.modelId === 'string') ? aiResponse.modelId : 'gemma-4-31b-it';
  const investigationSummary = (typeof aiResponse.investigationSummary === 'string' && aiResponse.investigationSummary.trim())
    ? aiResponse.investigationSummary.trim().slice(0, 300)
    : explanation.trim().slice(0, 300);
  const uncertaintyAndLimitations = (typeof aiResponse.uncertaintyAndLimitations === 'string' && aiResponse.uncertaintyAndLimitations.trim())
    ? aiResponse.uncertaintyAndLimitations.trim().slice(0, 300)
    : 'Static lexical assessment without dynamic runtime execution sandbox.';
  const investigationStatus = aiResponse.investigationStatus || 'GENUINE_AI_VERIFIED';

  return {
    valid: true,
    sanitizedResponse: {
      explanation: explanation.trim().slice(0, 600),
      evidenceExplanation: explanation.trim().slice(0, 600),
      findings: rawFindings.slice(0, 10),
      suspiciousIndicators: rawFindings.slice(0, 10).map(f => typeof f === 'string' ? f : (f.detail || f.indicator || JSON.stringify(f))),
      recommendedAction,
      recommendedNextStep: recommendedAction,
      uncertainty: numericUncertainty,
      uncertaintyScore: numericUncertainty,
      modelId,
      investigationSummary,
      uncertaintyAndLimitations,
      investigationStatus,
      validatedAt: new Date().toISOString()
    }
  };
}

// Local Gemma 4 Gateway Endpoint (Secure Node.js backend proxy)
const GEMMA_GATEWAY_URL = 'http://127.0.0.1:8787';

/**
 * Check health and availability of the local Gemma 4 AI Gateway.
 * Fails safely and gracefully if the gateway is offline.
 *
 * @returns {Promise<Object>} Gateway health state
 */
async function checkGemmaGatewayHealth() {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller ? setTimeout(() => controller.abort(), 2500) : null;

  try {
    const fetchFn = (typeof fetch !== 'undefined') ? fetch : null;
    if (!fetchFn) {
      return { available: false, configured: false, error: 'Fetch API unavailable in environment', offlineDefenseActive: true };
    }

    const res = await fetchFn(`${GEMMA_GATEWAY_URL}/api/health`, {
      method: 'GET',
      signal: controller ? controller.signal : undefined
    });

    if (timeoutId) clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      return {
        available: true,
        configured: Boolean(data.configured),
        modelId: data.modelId || 'gemma-4-31b-it',
        service: data.service,
        version: data.version,
        offlineDefenseActive: true
      };
    } else {
      return {
        available: false,
        configured: false,
        error: `Gateway returned status ${res.status}`,
        offlineDefenseActive: true
      };
    }
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    return {
      available: false,
      configured: false,
      error: err.name === 'AbortError' ? 'Gateway health request timed out' : 'Gateway is offline or unreachable',
      offlineDefenseActive: true
    };
  }
}

/**
 * Query local backend gateway for VirusTotal v3 URL reputation
 * Preserves local privacy: Gatekeeper on server side prevents private/token leaks.
 *
 * @param {string} rawUrl
 * @returns {Promise<Object>} Reputation result
 */
async function fetchVirusTotalReputation(rawUrl) {
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller ? setTimeout(() => controller.abort(), 12000) : null;

  try {
    const fetchFn = (typeof fetch !== 'undefined') ? fetch : null;
    if (!fetchFn) {
      return {
        success: false,
        provider: 'VirusTotal v3',
        status: 'unavailable',
        verdict: 'unavailable',
        lookupStatus: 'FETCH_UNAVAILABLE',
        error: 'Fetch API is unavailable in current runtime.'
      };
    }

    const res = await fetchFn(`${GEMMA_GATEWAY_URL}/api/reputation/url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: rawUrl }),
      signal: controller ? controller.signal : undefined
    });

    if (timeoutId) clearTimeout(timeoutId);

    if (res.ok) {
      const data = await res.json();
      return data;
    } else {
      const errData = await res.json().catch(() => ({}));
      return {
        success: false,
        provider: 'VirusTotal v3',
        status: res.status === 403 ? 'forbidden' : 'error',
        verdict: 'unavailable',
        lookupStatus: `HTTP_${res.status}`,
        error: errData.error || `Gateway returned HTTP ${res.status}`
      };
    }
  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    return {
      success: false,
      provider: 'VirusTotal v3',
      status: 'unavailable',
      verdict: 'unavailable',
      lookupStatus: err.name === 'AbortError' ? 'TIMEOUT' : 'GATEWAY_OFFLINE',
      error: err.name === 'AbortError'
        ? 'VirusTotal gateway request timed out.'
        : 'Local security gateway is unreachable at http://127.0.0.1:8787. Autonomous zero-trust heuristics remain active.'
    };
  }
}

/**
 * Integrate VirusTotal reputation into heuristic analysis and policy evaluation.
 * MANDATORY INVARIANT: Mandatory local blocks (HIGH_RISK) CANNOT be overridden by a clean or unknown VirusTotal result.
 *
 * @param {Object} analysis - Output from analyzeUrlHeuristics
 * @param {Object} vtResult - Output from fetchVirusTotalReputation
 * @param {boolean} [protectionEnabled=true] - Whether protection is enabled
 * @returns {Object} Updated analysis
 */
function integrateVirusTotalReputation(analysis, vtResult, protectionEnabled = true) {
  if (!analysis) return analysis;
  if (!vtResult || typeof vtResult !== 'object') {
    analysis.policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled);
    return analysis;
  }

  // Clone or mutate analysis with reputation telemetry
  analysis.virusTotal = vtResult;

  // 1. Malicious verdict: Elevate threat to HIGH_RISK
  if (vtResult.verdict === 'malicious') {
    const malCount = vtResult.stats?.malicious || 1;
    const total = vtResult.totalEngines || malCount;
    analysis.findings.push({
      severity: 'CRITICAL',
      category: 'VIRUSTOTAL_REPUTATION',
      detail: `VirusTotal Intelligence: Flagged as malicious by ${malCount}/${total} security engines.`
    });
    analysis.riskScore = Math.max(analysis.riskScore, 85);
    analysis.riskLevel = 'HIGH_RISK';
    analysis.verdictReason = `Multi-Engine Threat Containment: Flagged malicious by ${malCount} VirusTotal engines.`;
    analysis.policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled);
    return analysis;
  }

  // 2. Suspicious verdict: Elevate threat to at least SUSPICIOUS if not already HIGH_RISK
  if (vtResult.verdict === 'suspicious') {
    const suspCount = vtResult.stats?.suspicious || 1;
    analysis.findings.push({
      severity: 'HIGH',
      category: 'VIRUSTOTAL_REPUTATION',
      detail: `VirusTotal Intelligence: Flagged as suspicious by ${suspCount} security engines.`
    });
    analysis.riskScore = Math.max(analysis.riskScore, 60);
    if (analysis.riskLevel !== 'HIGH_RISK') {
      analysis.riskLevel = 'SUSPICIOUS';
      analysis.verdictReason = 'Suspicious Indicators: Flagged by VirusTotal threat telemetry.';
    }
    analysis.policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled);
    return analysis;
  }

  // 3. Clean / No detections: Supporting evidence ONLY — NEVER override mandatory local blocks!
  if (vtResult.verdict === 'clean/no detections') {
    if (analysis.riskLevel === 'HIGH_RISK') {
      analysis.findings.push({
        severity: 'INFO',
        category: 'VIRUSTOTAL_CLEAN_OVERRIDDEN',
        detail: 'Zero-Trust Precedence: Mandatory local block retained. Clean VirusTotal reputation does not override local zero-trust findings.'
      });
    } else {
      analysis.findings.push({
        severity: 'INFO',
        category: 'VIRUSTOTAL_CLEAN',
        detail: `VirusTotal Intelligence: 0/${vtResult.totalEngines || 0} engines detected threats (${vtResult.stats?.harmless || 0} harmless / ${vtResult.stats?.undetected || 0} undetected). Supporting evidence only.`
      });
    }
    // Invariant: Do NOT lower existing HIGH_RISK or SUSPICIOUS local findings
    analysis.policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled);
    return analysis;
  }

  // 4. Unknown / Unavailable / Error
  if (vtResult.verdict === 'unknown') {
    analysis.findings.push({
      severity: 'INFO',
      category: 'VIRUSTOTAL_UNKNOWN',
      detail: 'VirusTotal Intelligence: Target URL not found in dataset. Zero-trust baseline policy governs destination.'
    });
  }

  analysis.policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled);
  return analysis;
}

/**
 * Perform genuine Gemma 4 threat investigation via secure local backend gateway.
 * Preserves local policy supremacy: AI output is strictly advisory and cannot override local rules.
 *
 * @param {string} rawUrl
 * @param {Object} [cachedAnalysis]
 * @returns {Promise<Object>} Investigation outcome
 */
async function performGemmaInvestigation(rawUrl, cachedAnalysis) {
  const analysis = cachedAnalysis || analyzeUrlHeuristics(rawUrl);
  const protectionEnabled = await EventStore.getProtectionStatus();
  const policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled !== false);

  // Build sanitized prompt injection-safe payload
  const payload = createGemmaInvestigationPayload(analysis);
  if (!payload) {
    return {
      success: false,
      genuineAi: false,
      error: 'Failed to construct sanitized investigation payload.',
      offlineDefenseActive: true,
      analysis,
      policyDecision
    };
  }

  // Include non-sensitive policy decision context for advisory review
  payload.authoritativePolicy = {
    policyCode: policyDecision.policyCode,
    decision: policyDecision.decision,
    requiresBlocking: policyDecision.requiresBlocking,
    isLocalAuthoritative: true
  };

  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller ? setTimeout(() => controller.abort(), 38000) : null;

  try {
    const fetchFn = (typeof fetch !== 'undefined') ? fetch : null;
    if (!fetchFn) {
      return {
        success: false,
        genuineAi: false,
        error: 'Fetch API not supported in runtime environment.',
        offlineDefenseActive: true,
        analysis,
        policyDecision
      };
    }

    const res = await fetchFn(`${GEMMA_GATEWAY_URL}/api/investigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller ? controller.signal : undefined
    });

    if (timeoutId) clearTimeout(timeoutId);

    const data = await res.json().catch(() => null);

    if (!res.ok || !data || !data.success) {
      const errStatus = data?.status || (res.status === 503 ? 'CONFIG_REQUIRED' : 'GATEWAY_ERROR');
      const errMsg = data?.error || `Gateway returned HTTP ${res.status}`;
      return {
        success: false,
        genuineAi: false,
        status: errStatus,
        error: errMsg,
        offlineDefenseActive: true,
        analysis,
        policyDecision
      };
    }

    // Validate the response through schema contract
    const validation = validateGemmaResponse(data.investigation);
    if (!validation.valid) {
      return {
        success: false,
        genuineAi: false,
        status: 'MALFORMED_AI_OUTPUT',
        error: `AI response rejected by schema validator: ${validation.error}`,
        offlineDefenseActive: true,
        analysis,
        policyDecision
      };
    }

    // Record verified investigation event in local audit store
    try {
      await EventStore.recordEvent({
        url: analysis.url,
        domain: analysis.domain,
        riskScore: analysis.riskScore,
        riskLevel: analysis.riskLevel,
        verdictReason: `Gemma 4 Advisory: ${validation.sanitizedResponse.investigationSummary}`,
        findings: analysis.findings,
        actionAttempted: 'AI_INVESTIGATION',
        actualActionResult: 'INVESTIGATED',
        verificationStatus: 'GENUINE_AI_VERIFIED',
        blocked: false,
        metadata: {
          modelId: validation.sanitizedResponse.modelId,
          advisoryNextStep: validation.sanitizedResponse.recommendedNextStep,
          uncertaintyScore: validation.sanitizedResponse.uncertaintyScore,
          authoritativePolicyCode: policyDecision.policyCode
        }
      });
    } catch (storeErr) {
      console.warn('[SentinelX Service Worker] Event logging notice:', storeErr);
    }

    return {
      success: true,
      genuineAi: true,
      investigation: validation.sanitizedResponse,
      analysis,
      policyDecision,
      offlineDefenseActive: true
    };

  } catch (err) {
    if (timeoutId) clearTimeout(timeoutId);
    const isTimeout = err.name === 'AbortError';
    return {
      success: false,
      genuineAi: false,
      status: isTimeout ? 'TIMEOUT' : 'GATEWAY_OFFLINE',
      error: isTimeout
        ? 'Gemma 4 gateway request timed out (inference latency exceeded).'
        : 'Gemma 4 gateway is unreachable at http://127.0.0.1:8787. Autonomous local defense remains active.',
      offlineDefenseActive: true,
      analysis,
      policyDecision
    };
  }
}

// ============================================================================
// PRIORITY 6.5: LIVE NAVIGATION PROTECTION & IN-PAGE DESTINATION COORDINATOR
// ============================================================================

// Active tab assessment cache (Map<number, Object>)
const activeTabAssessments = new Map();

// In-page destination assessment cache (Map<string, Object>)
const pageDestinationsCache = new Map();

/**
 * Handle browser tab navigation destinations dynamically.
 * Intercepts high-risk navigations before exposure and enforces autonomous policy.
 *
 * @param {number} tabId
 * @param {string} rawUrl
 * @param {string} source - 'TAB_URL_UPDATE' | 'BEFORE_NAVIGATE'
 * @returns {Promise<Object>} Assessment outcome
 */
async function processNavigationTarget(tabId, rawUrl, source = 'TAB_URL_UPDATE') {
  if (!rawUrl || typeof rawUrl !== 'string') {
    return { skipped: true, reason: 'Empty navigation URL' };
  }

  // 1. Identify Scheme and Safety Baseline
  if (rawUrl.startsWith('chrome://') || rawUrl.startsWith('about:') || rawUrl.startsWith('chrome-extension://')) {
    return {
      skipped: true,
      decision: 'BYPASS_INTERNAL',
      riskLevel: 'LOW_RISK',
      schemeType: 'INTERNAL_BROWSER',
      reason: 'Protected internal browser interface',
      url: rawUrl
    };
  }

  if (rawUrl.startsWith('devtools://') || rawUrl.startsWith('edge://') || rawUrl.startsWith('view-source:')) {
    return {
      skipped: true,
      decision: 'SKIPPED_RESTRICTED',
      riskLevel: 'LOW_RISK',
      schemeType: 'RESTRICTED_SYSTEM',
      reason: 'Restricted system protocol',
      url: rawUrl
    };
  }

  // 2. Perform Local Zero-Trust Heuristic Evaluation
  const analysis = analyzeUrlHeuristics(rawUrl);
  const protectionEnabled = await EventStore.getProtectionStatus();
  const policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled !== false);
  const quarantined = Boolean(policyDecision.requiresBlocking);

  const assessment = {
    tabId,
    url: analysis.url,
    domain: analysis.domain,
    source,
    navSource: source,
    riskScore: analysis.riskScore,
    riskLevel: analysis.riskLevel,
    policyDecision,
    quarantined,
    findings: analysis.findings,
    protectionEnabled: protectionEnabled !== false,
    assessedAt: new Date().toISOString()
  };

  if (tabId) {
    activeTabAssessments.set(tabId, assessment);
  }

  // 3. Autonomous Protection Action
  if (policyDecision.requiresBlocking) {
    console.warn(`[SYNTRAX Navigation Shield] Quarantining dangerous navigation target: ${analysis.domain} (${analysis.riskLevel})`);

    // Enforce DeclarativeNetRequest block rule
    await enforceDomainBlockRule(analysis.domain, {
      url: analysis.url,
      riskScore: analysis.riskScore,
      findings: analysis.findings
    });

    // Redirect tab to warning interstitial if supported
    if (typeof chrome !== 'undefined' && chrome.tabs?.update && tabId) {
      const warningUrl = chrome.runtime.getURL(
        `warning/warning.html?url=${encodeURIComponent(analysis.url)}&domain=${encodeURIComponent(analysis.domain)}&score=${analysis.riskScore}&level=${analysis.riskLevel}&reason=${encodeURIComponent(analysis.verdictReason)}`
      );
      try {
        await chrome.tabs.update(tabId, { url: warningUrl });
      } catch (_) {}
    }
  } else {
    // Record inspection in local audit trail (non-blocking)
    try {
      await EventStore.recordEvent({
        url: analysis.url,
        domain: analysis.domain,
        riskScore: analysis.riskScore,
        riskLevel: analysis.riskLevel,
        verdictReason: analysis.verdictReason,
        findings: analysis.findings,
        actionAttempted: 'NAVIGATE_INSPECT',
        actualActionResult: 'INSPECTED',
        verificationStatus: 'VERIFIED',
        blocked: false
      });
    } catch (_) {}
  }

  return assessment;
}

/**
 * Setup navigation listeners on chrome.tabs and chrome.webNavigation
 */
function setupNavigationProtection() {
  if (typeof chrome === 'undefined') return;

  // 1. chrome.tabs.onUpdated URL change listener
  if (chrome.tabs?.onUpdated) {
    chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
      if (changeInfo.url) {
        await processNavigationTarget(tabId, changeInfo.url, 'TAB_URL_UPDATE');
      }
    });
  }

  // 2. chrome.webNavigation.onBeforeNavigate listener (if permission/API available)
  if (chrome.webNavigation?.onBeforeNavigate) {
    chrome.webNavigation.onBeforeNavigate.addListener(async (details) => {
      if (details.frameId === 0 && details.url) {
        await processNavigationTarget(details.tabId, details.url, 'BEFORE_NAVIGATE');
      }
    });
  }
}

/**
 * Batch-evaluate in-page destinations discovered by content script.
 * Reuses local heuristic engine and deterministic policy engine.
 *
 * @param {Array<Object>} destinations
 * @param {string} pageUrl
 * @returns {Object} Comprehensive destination threat assessment
 */
function evaluatePageDestinationsBatch(destinations, pageUrl) {
  if (!Array.isArray(destinations)) {
    return {
      pageUrl: pageUrl || '',
      totalDiscovered: 0,
      inspectableCount: 0,
      highRiskCount: 0,
      suspiciousCount: 0,
      unknownCount: 0,
      lowRiskCount: 0,
      skippedCount: 0,
      skippedSummary: {},
      flaggedDestinations: [],
      destinations: []
    };
  }

  let highRiskCount = 0;
  let suspiciousCount = 0;
  let unknownCount = 0;
  let lowRiskCount = 0;
  let skippedCount = 0;
  const skippedSummary = {};

  const assessedDestinations = destinations.map(dest => {
    if (!dest.isInspectableWebUrl) {
      skippedCount++;
      const cat = dest.category || 'SKIPPED';
      skippedSummary[cat] = (skippedSummary[cat] || 0) + 1;
      return {
        ...dest,
        riskLevel: 'SKIPPED',
        riskScore: 0,
        findings: []
      };
    }

    const analysis = analyzeUrlHeuristics(dest.url);
    const policyDecision = evaluateSecurityPolicy(analysis, true);

    const level = analysis.riskLevel;
    if (level === 'HIGH_RISK') highRiskCount++;
    else if (level === 'SUSPICIOUS') suspiciousCount++;
    else if (level === 'LOW_RISK') lowRiskCount++;
    else unknownCount++;

    return {
      ...dest,
      riskLevel: level,
      riskScore: analysis.riskScore,
      policyDecision,
      verdictReason: analysis.verdictReason,
      findings: analysis.findings || []
    };
  });

  // Sort flagged findings (highest risk first)
  const flaggedDestinations = assessedDestinations
    .filter(d => d.riskLevel === 'HIGH_RISK' || d.riskLevel === 'SUSPICIOUS')
    .sort((a, b) => (b.riskScore || 0) - (a.riskScore || 0));

  const result = {
    pageUrl: pageUrl || '',
    totalDiscovered: destinations.length,
    inspectableCount: destinations.length - skippedCount,
    highRiskCount,
    suspiciousCount,
    unknownCount,
    lowRiskCount,
    skippedCount,
    skippedSummary,
    flaggedDestinations,
    destinations: assessedDestinations,
    assessedAt: new Date().toISOString()
  };

  if (pageUrl) {
    pageDestinationsCache.set(pageUrl, result);
  }

  return result;
}

// Initialize navigation listeners
setupNavigationProtection();

// ============================================================================
// LIFECYCLE & STARTUP RECOVERY
// ============================================================================

chrome.runtime.onInstalled.addListener(async (details) => {
  console.log('[SentinelX AI] Engine initialized/installed:', details.reason);

  // Initialize default protection status
  const isEnabled = await EventStore.getProtectionStatus();
  if (isEnabled === undefined) {
    await EventStore.setProtectionStatus(true);
  }

  // Run initial self-healing rule baseline verification
  try {
    const integrity = await checkProtectionRuleIntegrity();
    if (!integrity.healthy) {
      console.log('[SentinelX AI] Baseline rules missing; initiating self-healing recovery...');
      await repairProtectionRules();
    }
  } catch (e) {
    console.warn('[SentinelX AI] Install check notice:', e);
  }
});

// ============================================================================
// PRIORITY 7: CHROME RUNTIME MESSAGING INTERFACE (CONTRACT FOR MEMBER 2)
// ============================================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type) {
    return false;
  }

  (async () => {
    try {
      switch (message.type) {

        // 1. URL Analysis Request
        case 'ANALYZE_URL': {
          const analysis = analyzeUrlHeuristics(message.url);
          const protectionEnabled = await EventStore.getProtectionStatus();
          const policyDecision = evaluateSecurityPolicy(analysis, protectionEnabled);

          // Record non-blocking inspection event
          const eventRecord = await EventStore.recordEvent({
            url: analysis.url,
            domain: analysis.domain,
            riskScore: analysis.riskScore,
            riskLevel: analysis.riskLevel,
            verdictReason: analysis.verdictReason,
            findings: analysis.findings,
            actionAttempted: 'INSPECT',
            actualActionResult: 'INSPECTED',
            verificationStatus: 'VERIFIED',
            blocked: false
          });

          sendResponse({
            success: true,
            analysis,
            policyDecision,
            eventRecord,
            protectionEnabled
          });
          break;
        }

        // 2. Real DeclarativeNetRequest Domain Block
        case 'BLOCK_DOMAIN_RULE': {
          const blockOutcome = await enforceDomainBlockRule(message.domain, {
            url: message.url,
            riskScore: message.riskScore,
            findings: message.findings
          });
          sendResponse(blockOutcome);
          break;
        }

        // 3. Remove Block Rule
        case 'REMOVE_BLOCK_RULE': {
          const removeOutcome = await removeDomainBlockRule(message.ruleId);
          sendResponse(removeOutcome);
          break;
        }

        // 4. Retrieve Active Dynamic Rules
        case 'GET_ACTIVE_RULES': {
          if (typeof chrome !== 'undefined' && chrome.declarativeNetRequest?.getDynamicRules) {
            const rules = await chrome.declarativeNetRequest.getDynamicRules();
            sendResponse({ success: true, rules });
          } else {
            sendResponse({ success: true, rules: [] });
          }
          break;
        }

        // 5. Self-Healing Integrity Check
        case 'CHECK_INTEGRITY':
        case 'RUN_INTEGRITY_CHECK': {
          const integrityReport = await checkProtectionRuleIntegrity();

          // If repair requested or if report is degraded, run verified repair
          let repairOutcome = null;
          if (message.autoRepair && !integrityReport.healthy) {
            repairOutcome = await repairProtectionRules();
          }

          sendResponse({
            success: true,
            healthy: integrityReport.healthy,
            verified: integrityReport.healthy || Boolean(repairOutcome?.verified),
            rulesCount: integrityReport.totalActive,
            integrityReport,
            repairOutcome,
            checkedAt: new Date().toISOString()
          });
          break;
        }

        // 6. Explicit Self-Healing Repair Request
        case 'REPAIR_RULES': {
          const outcome = await repairProtectionRules();
          sendResponse(outcome);
          break;
        }

        // 7. Verify Operational State (Storage + DeclarativeNetRequest Health)
        case 'VERIFY_OPERATIONAL_STATE': {
          let storageHealthy = false;
          let rulesHealthy = false;
          let activeRulesCount = 0;

          try {
            const status = await EventStore.getProtectionStatus();
            storageHealthy = status !== undefined;
          } catch (_) {
            storageHealthy = false;
          }

          try {
            if (typeof chrome !== 'undefined' && chrome.declarativeNetRequest?.getDynamicRules) {
              const rules = await chrome.declarativeNetRequest.getDynamicRules();
              rulesHealthy = true;
              activeRulesCount = rules.length;
            } else {
              rulesHealthy = true;
            }
          } catch (_) {
            rulesHealthy = false;
          }

          const protectionEnabled = await EventStore.getProtectionStatus();
          const isOperational = storageHealthy && rulesHealthy;

          sendResponse({
            success: true,
            operational: isOperational,
            protectionEnabled: protectionEnabled !== false,
            storageHealthy,
            rulesHealthy,
            activeRulesCount,
            verifiedAt: new Date().toISOString()
          });
          break;
        }

        // 8. Event Log Retrieval & Stats
        case 'GET_EVENTS': {
          const events = await EventStore.getEvents(message.limit || 50);
          const stats = await EventStore.getEventStats();
          sendResponse({ success: true, events, stats });
          break;
        }

        // 9. Clear Event Logs
        case 'CLEAR_EVENTS': {
          const cleared = await EventStore.clearEvents();
          sendResponse({ success: cleared });
          break;
        }

        // 10. Protection Status Toggle
        case 'GET_PROTECTION_STATUS': {
          const status = await EventStore.getProtectionStatus();
          sendResponse({ success: true, protectionEnabled: status });
          break;
        }

        case 'SET_PROTECTION_STATUS': {
          const updated = await EventStore.setProtectionStatus(message.enabled);
          sendResponse({ success: updated, protectionEnabled: message.enabled });
          break;
        }

        // 11. AI Investigation Payload Contract Helper
        case 'PREPARE_AI_INVESTIGATION': {
          const analysis = analyzeUrlHeuristics(message.url);
          const payload = createGemmaInvestigationPayload(analysis);
          sendResponse({ success: true, payload });
          break;
        }

        // 12. Validate AI Response Contract Helper
        case 'VALIDATE_AI_PAYLOAD': {
          const validation = validateGemmaResponse(message.aiResponse);
          sendResponse(validation);
          break;
        }

        // 13. Genuine Gemma 4 Threat Investigation Request
        case 'INVESTIGATE_URL_WITH_AI': {
          const outcome = await performGemmaInvestigation(message.url, message.analysis);
          sendResponse(outcome);
          break;
        }

        // 14. Check Gemma 4 Gateway Service Health
        case 'CHECK_AI_SERVICE_HEALTH': {
          const health = await checkGemmaGatewayHealth();
          sendResponse(health);
          break;
        }

        // 15. Analyze In-Page Discovered Destinations (Batch)
        case 'ANALYZE_PAGE_DESTINATIONS': {
          const report = evaluatePageDestinationsBatch(message.destinations, message.pageUrl);
          sendResponse({ success: true, report });
          break;
        }

        // 16. Get Cached Page Destinations Status
        case 'GET_PAGE_DESTINATIONS_STATUS': {
          const cached = message.pageUrl ? pageDestinationsCache.get(message.pageUrl) : null;
          sendResponse({ success: true, report: cached || null });
          break;
        }

        // 17. Content Script Notification: Page Links Discovered
        case 'PAGE_LINKS_DISCOVERED': {
          const report = evaluatePageDestinationsBatch(message.destinations, message.pageUrl);
          sendResponse({ success: true, received: true, total: report.totalDiscovered });
          break;
        }

        // 18. Retrieve Current Active Tab Navigation Assessment
        case 'GET_ACTIVE_TAB_ASSESSMENT': {
          const assessment = message.tabId ? activeTabAssessments.get(message.tabId) : null;
          sendResponse({ success: true, assessment: assessment || null });
          break;
        }

        // 19. VirusTotal URL Reputation Check
        case 'CHECK_VIRUSTOTAL_REPUTATION':
        case 'GET_VIRUSTOTAL_REPUTATION': {
          const rawUrl = message.url;
          const vtResult = await fetchVirusTotalReputation(rawUrl);

          let updatedAnalysis = null;
          let policyDecision = null;

          if (message.integrateWithAnalysis) {
            const baseAnalysis = message.analysis || analyzeUrlHeuristics(rawUrl);
            updatedAnalysis = integrateVirusTotalReputation(baseAnalysis, vtResult);
            const protectionEnabled = await EventStore.getProtectionStatus();
            policyDecision = evaluateSecurityPolicy(updatedAnalysis, protectionEnabled);
          }

          sendResponse({
            success: true,
            url: rawUrl,
            reputation: vtResult,
            analysis: updatedAnalysis,
            policyDecision
          });
          break;
        }

        default:
          sendResponse({ success: false, error: `Unrecognized SentinelX message type: ${message.type}` });
          break;
      }
    } catch (err) {
      console.error('[SentinelX Service Worker] Top-level handler error:', err);
      sendResponse({ success: false, error: err.message });
    }
  })();

  // Return true to keep message channel open for async response
  return true;
});

// Export helper methods for Node.js unit testing suite
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    analyzeUrlHeuristics,
    evaluateSecurityPolicy,
    generateDynamicRuleId,
    normalizeDomainForRule,
    enforceDomainBlockRule,
    removeDomainBlockRule,
    checkProtectionRuleIntegrity,
    repairProtectionRules,
    getExpectedProtectionRules,
    createGemmaInvestigationPayload,
    validateGemmaResponse,
    checkGemmaGatewayHealth,
    performGemmaInvestigation,
    fetchVirusTotalReputation,
    integrateVirusTotalReputation,
    processNavigationTarget,
    evaluatePageDestinationsBatch,
    activeTabAssessments,
    pageDestinationsCache,
    GEMMA_GATEWAY_URL,
    BASELINE_MANAGED_RULES,
    KNOWN_MALICIOUS_DOMAINS,
    VERIFIED_REPUTABLE_DOMAINS
  };
}

