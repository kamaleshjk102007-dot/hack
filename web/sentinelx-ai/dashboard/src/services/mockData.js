// sentinelx-ai/dashboard/src/services/mockData.js
/**
 * EDITH AI - Verified Demo Fixtures
 * Explicitly labeled simulation datasets for offline / demo mode.
 * Real events are merged from Chrome Storage API or FastAPI backend when connected.
 */

export const DEMO_DATA_TAG = 'DEMO_FIXTURE';

export const DEMO_INCIDENTS = [
  {
    id: 'INC-2026-9041',
    isDemo: true,
    url: 'https://paypal.com@verify-auth-session.xyz/account/login',
    domain: 'verify-auth-session.xyz',
    classification: 'Phishing & Credential Interception',
    riskScore: 94,
    riskLevel: 'HIGH_RISK',
    detectionSource: 'EDITH AI Heuristic Syntax Analyzer & TLD Abuse Monitor',
    evidence: [
      { category: 'URL_OBFUSCATION', detail: 'Authority userinfo "@" character used to conceal actual destination domain.' },
      { category: 'BRAND_IMPERSONATION', detail: 'Keyword "paypal" and "account" combined in hostile authority string.' },
      { category: 'TLD_REPUTATION', detail: '.xyz extension flagged for statistical association with high-velocity phishing kits.' }
    ],
    aiExplanation: 'The target URI deploys an RFC-3986 userinfo trick to visually mislead victims into believing they are contacting PayPal, while routing traffic to an unverified registration on .xyz. High confidence credential harvester.',
    recommendedAction: 'Immediate containment via declarativeNetRequest dynamic blocking and session invalidation.',
    actualActionTaken: 'RULE_BLOCK_ENFORCED',
    actionStatus: 'Enforced via Rule #4891',
    verificationResult: 'Verified: DNS lookup neutralized & Chrome navigation intercepted.',
    timestamp: '2026-10-26T22:30:15Z'
  },
  {
    id: 'INC-2026-9038',
    isDemo: true,
    url: 'http://185.220.101.5/admin/login?payload=exec',
    domain: '185.220.101.5',
    classification: 'C2 Node / Malicious Infrastructure',
    riskScore: 88,
    riskLevel: 'HIGH_RISK',
    detectionSource: 'Raw IP Host Heuristic & Transport Layer Inspection',
    evidence: [
      { category: 'HOST_IDENTITY', detail: 'Connection directly targets raw IPv4 address without reverse DNS hostname.' },
      { category: 'TRANSPORT', detail: 'Cleartext HTTP transport without TLS encryption; sensitive credentials exposed to MITM.' },
      { category: 'QUERY_SYNTAX', detail: 'Suspicious execution parameter "payload=exec" in query string.' }
    ],
    aiExplanation: 'Raw IP infrastructure running unencrypted web endpoints with administrative parameters is characteristic of compromised botnet nodes or automated vulnerability probes.',
    recommendedAction: 'Block IP range and log network telemetry.',
    actualActionTaken: 'RULE_BLOCK_ENFORCED',
    actionStatus: 'Enforced via Rule #7712',
    verificationResult: 'Verified: Request dropped at browser network boundary.',
    timestamp: '2026-10-26T21:45:00Z'
  },
  {
    id: 'INC-2026-9029',
    isDemo: true,
    url: 'https://xn--app-9pa.support-apple-id.top/auth',
    domain: 'xn--app-9pa.support-apple-id.top',
    classification: 'IDN Homograph & Brand Impersonation',
    riskScore: 82,
    riskLevel: 'HIGH_RISK',
    detectionSource: 'Punycode Homoglyph Engine',
    evidence: [
      { category: 'HOMOGRAPH', detail: 'Punycode sequence "xn--app-9pa" creates visual Cyrillic spoof of legitimate character.' },
      { category: 'BRAND_IMPERSONATION', detail: 'Explicit substring "support-apple-id" on untrusted .top registrar.' }
    ],
    aiExplanation: 'Visual homograph attack targeting Apple account credentials. The domain uses Cyrillic substitution to evade standard lexical filters.',
    recommendedAction: 'Prevent tab navigation and redirect to EDITH AI Interstitial Warning.',
    actualActionTaken: 'RULE_BLOCK_ENFORCED',
    actionStatus: 'Enforced via Rule #1209',
    verificationResult: 'Verified: Dynamic rule active; warning screen rendered.',
    timestamp: '2026-10-26T20:12:44Z'
  },
  {
    id: 'INC-2026-8994',
    isDemo: true,
    url: 'http://insecure-regional-newspaper.com/articles/daily',
    domain: 'insecure-regional-newspaper.com',
    classification: 'Insecure Cleartext Transport',
    riskScore: 35,
    riskLevel: 'SUSPICIOUS',
    detectionSource: 'Transport Layer Security Auditor',
    evidence: [
      { category: 'TRANSPORT', detail: 'Unencrypted HTTP protocol in use for media content distribution.' }
    ],
    aiExplanation: 'Site lacks SSL/TLS encryption. While not confirmed malicious, user browsing history and transferred content can be observed or injected with rogue scripts by local networks.',
    recommendedAction: 'Warn user regarding lack of encryption before inputting data.',
    actualActionTaken: 'INSPECTED',
    actionStatus: 'Logged & Monitored',
    verificationResult: 'Verified: Passive observation active; no blocking required.',
    timestamp: '2026-10-26T18:05:12Z'
  },
  {
    id: 'INC-2026-8971',
    isDemo: true,
    url: 'https://emerging-fintech-beta.io/waitlist',
    domain: 'emerging-fintech-beta.io',
    classification: 'Unverified Entity / Zero-Trust Baseline',
    riskScore: 12,
    riskLevel: 'UNKNOWN',
    detectionSource: 'EDITH AI Zero-Trust Baseline Engine',
    evidence: [
      { category: 'ZERO_TRUST', detail: 'No known malicious indicators found, but domain lacks verified historical reputation.' },
      { category: 'TRANSPORT', detail: 'Valid TLS encryption active.' }
    ],
    aiExplanation: 'Domain does not trigger heuristic threat signatures. However, under zero-trust guidelines, unknown entities cannot be certified as safe without verified reputation history.',
    recommendedAction: 'Retain in UNKNOWN classification; display neutral advisory.',
    actualActionTaken: 'INSPECTED',
    actionStatus: 'Logged as Unknown',
    verificationResult: 'Verified: Policy correctly set to UNKNOWN.',
    timestamp: '2026-10-26T16:22:30Z'
  },
  {
    id: 'INC-2026-8950',
    isDemo: true,
    url: 'https://github.com/kubernetes/kubernetes',
    domain: 'github.com',
    classification: 'Verified Infrastructure Baseline',
    riskScore: 2,
    riskLevel: 'LOW_RISK',
    detectionSource: 'High-Reputation Whitelist Baseline',
    evidence: [
      { category: 'BASELINE', detail: 'Domain matches verified global software development infrastructure.' },
      { category: 'TRANSPORT', detail: 'Modern TLS 1.3 encryption with strong cipher suites.' }
    ],
    aiExplanation: 'Verified public infrastructure with valid certificates and zero observable syntax anomalies.',
    recommendedAction: 'Allow normal traffic; enforce passive zero-trust telemetry.',
    actualActionTaken: 'INSPECTED',
    actionStatus: 'Allowed',
    verificationResult: 'Verified: Operational.',
    timestamp: '2026-10-26T14:10:05Z'
  }
];

export const DEMO_SELF_HEALING_RULES = [
  {
    id: 'RULE-01',
    isDemo: true,
    name: 'Declarative Net Request Threat Engine',
    category: 'Network Interception',
    required: true,
    status: 'ACTIVE',
    checksum: 'sha256-a94f1c',
    repairAttempts: 0,
    lastOutcome: 'Verified intact during boot',
    failureReason: null,
    description: 'Enforces dynamic packet dropping and redirection for confirmed malicious hosts.'
  },
  {
    id: 'RULE-02',
    isDemo: true,
    name: 'Content Security Policy (CSP) Auto-Shield',
    category: 'Script Isolation',
    required: true,
    status: 'ACTIVE',
    checksum: 'sha256-e82b71',
    repairAttempts: 1,
    lastOutcome: 'Repaired after manifest mismatch',
    failureReason: null,
    description: 'Prevents dynamic script injection and eval() execution on untrusted origins.'
  },
  {
    id: 'RULE-03',
    isDemo: true,
    name: 'IDN Homoglyph Normalization Hook',
    category: 'Lexical Analysis',
    required: true,
    status: 'ACTIVE',
    checksum: 'sha256-3c990a',
    repairAttempts: 0,
    lastOutcome: 'Operational',
    failureReason: null,
    description: 'Intercepts non-ASCII Punycode transformations before URL rendering.'
  },
  {
    id: 'RULE-04',
    isDemo: true,
    name: 'Chrome Storage Local Event Mirror',
    category: 'Persistence Integrity',
    required: true,
    status: 'ACTIVE',
    checksum: 'sha256-78d10b',
    repairAttempts: 2,
    lastOutcome: 'Verified auto-vacuum & schema sync',
    failureReason: null,
    description: 'Secures local storage partitions from unbounded expansion and tamper corruption.'
  },
  {
    id: 'RULE-05',
    isDemo: true,
    name: 'FastAPI Backend Telemetry Bridge',
    category: 'Remote Uplink',
    required: false,
    status: 'STANDBY',
    checksum: 'sha256-none',
    repairAttempts: 0,
    lastOutcome: 'Standby: Backend service not yet online',
    failureReason: 'Port 8000 connection timeout (Expected prior to backend startup)',
    description: 'Synchronizes edge security events with centralized EDITH AI FastAPI intelligence server.'
  }
];

export const DEMO_THREAT_INTEL = [
  {
    id: 'IOC-8821',
    isDemo: true,
    indicator: 'update-session-verification.top',
    type: 'Domain / FQDN',
    threatType: 'Phishing Campaign: FinTech Harvest',
    confidence: 96,
    firstSeen: '2026-10-25T11:00:00Z',
    severity: 'CRITICAL',
    source: 'Abuse.ch & EDITH AI Community Sensor'
  },
  {
    id: 'IOC-8819',
    isDemo: true,
    indicator: '194.38.20.119',
    type: 'IPv4 Address',
    threatType: 'Cobalt Strike C2 Beacon',
    confidence: 91,
    firstSeen: '2026-10-26T04:15:00Z',
    severity: 'HIGH',
    source: 'ThreatConnect Feed'
  },
  {
    id: 'IOC-8814',
    isDemo: true,
    indicator: 'CVE-2026-2189',
    type: 'Vulnerability CVE',
    threatType: 'V8 JIT Type Confusion Remote Code Execution',
    confidence: 99,
    firstSeen: '2026-10-24T18:30:00Z',
    severity: 'CRITICAL',
    source: 'NVD / Chromium Security Bulletins'
  },
  {
    id: 'IOC-8805',
    isDemo: true,
    indicator: 'e9b28a11f5d6092bb49320d911a30894f71a0b5c10',
    type: 'SHA1 Binary Hash',
    threatType: 'Infostealer Dropper Payload (StealC)',
    confidence: 95,
    firstSeen: '2026-10-26T09:40:00Z',
    severity: 'HIGH',
    source: 'VirusTotal Intelligence'
  }
];

export const DEMO_SECURITY_ALERTS = [
  {
    id: 'ALT-104',
    isDemo: true,
    title: 'High-Velocity Phishing Attempt Thwarted',
    summary: 'Active credential interceptor targeting paypal.com@verify-auth-session.xyz was contained by Dynamic Rule #4891.',
    severity: 'CRITICAL',
    acknowledged: false,
    timestamp: '2026-10-26T22:30:15Z'
  },
  {
    id: 'ALT-103',
    isDemo: true,
    title: 'Raw IP Command-and-Control Target Blocked',
    summary: 'Direct connection to suspicious IPv4 host 185.220.101.5 intercepted before payload transmission.',
    severity: 'HIGH',
    acknowledged: false,
    timestamp: '2026-10-26T21:45:00Z'
  },
  {
    id: 'ALT-102',
    isDemo: true,
    title: 'Self-Healing Auto-Repair Completed',
    summary: 'Content Security Policy (CSP) Auto-Shield rules were reconciled after detecting an out-of-sync local checksum.',
    severity: 'INFO',
    acknowledged: true,
    timestamp: '2026-10-26T21:10:00Z'
  },
  {
    id: 'ALT-101',
    isDemo: true,
    title: 'Zero-Trust Warning: Unverified Target Inspected',
    summary: 'Domain emerging-fintech-beta.io has no known negative markers but zero verified trust baseline; labeled UNKNOWN.',
    severity: 'WARNING',
    acknowledged: true,
    timestamp: '2026-10-26T16:22:30Z'
  }
];

export const DEMO_PERMISSIONS = [
  {
    id: 'PERM-01',
    isDemo: true,
    extensionName: 'EDITH AI - Threat Defense',
    permission: 'declarativeNetRequest',
    riskTier: 'CONTROLLED',
    justification: 'Enforces dynamic packet dropping for flagged threat hosts.',
    status: 'AUDITED_SECURE'
  },
  {
    id: 'PERM-02',
    isDemo: true,
    extensionName: 'EDITH AI - Threat Defense',
    permission: 'storage',
    riskTier: 'LOW',
    justification: 'Persists security event logs within sandboxed chrome.storage.local.',
    status: 'AUDITED_SECURE'
  },
  {
    id: 'PERM-03',
    isDemo: true,
    extensionName: 'EDITH AI - Threat Defense',
    permission: 'activeTab & tabs',
    riskTier: 'CONTROLLED',
    justification: 'Queries active tab URI for on-demand heuristic evaluation.',
    status: 'AUDITED_SECURE'
  },
  {
    id: 'PERM-04',
    isDemo: true,
    extensionName: 'Legacy PDF Reader Extension (Third-Party)',
    permission: '<all_urls> & webRequestBlocking',
    riskTier: 'HIGH_RISK',
    justification: 'Broad host permission allows full read/write of DOM across all browsing tabs.',
    status: 'ATTENTION_REQUIRED'
  }
];

export const DEMO_DOWNLOADS = [
  {
    id: 'DL-5091',
    isDemo: true,
    filename: 'invoice_october_statement.pdf.exe',
    sourceUrl: 'http://185.220.101.5/payload/dl',
    fileSize: '1.4 MB',
    detectedMime: 'application/x-dosexec (PE32)',
    claimedMime: 'application/pdf',
    entropy: '7.92 (High / Encrypted / Packed)',
    riskLevel: 'HIGH_RISK',
    action: 'QUARANTINED',
    timestamp: '2026-10-26T21:44:50Z'
  },
  {
    id: 'DL-5082',
    isDemo: true,
    filename: 'security_update_patch.scr',
    sourceUrl: 'https://verify-auth-session.xyz/setup',
    fileSize: '482 KB',
    detectedMime: 'application/x-msdownload',
    claimedMime: 'text/html',
    entropy: '7.85 (High)',
    riskLevel: 'HIGH_RISK',
    action: 'QUARANTINED',
    timestamp: '2026-10-26T20:30:10Z'
  },
  {
    id: 'DL-5070',
    isDemo: true,
    filename: 'quarterly_report_2026.pdf',
    sourceUrl: 'https://github.com/kubernetes/docs',
    fileSize: '3.8 MB',
    detectedMime: 'application/pdf',
    claimedMime: 'application/pdf',
    entropy: '5.10 (Normal)',
    riskLevel: 'LOW_RISK',
    action: 'ALLOWED',
    timestamp: '2026-10-26T14:15:22Z'
  }
];
