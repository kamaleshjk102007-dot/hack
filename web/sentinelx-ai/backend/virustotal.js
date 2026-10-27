// web/sentinelx-ai/backend/virustotal.js
/**
 * SentinelX AI — VirusTotal v3 Threat Intelligence Gateway Subsystem
 *
 * Provides privacy-preserving, zero-dependency VirusTotal v3 URL reputation lookups.
 * Key Security & Architectural Principles:
 * 1. Strict Privacy: Never sends internal/localhost, private IP, or confidential token-bearing URLs.
 * 2. Key Isolation: Holds VT_API_KEY strictly in backend environment; never leaks to browser/logs.
 * 3. Bounded Caching: In-memory LRU/TTL cache reduces external quota consumption.
 * 4. Rate-Limit Resilience: Gracefully detects HTTP 429 and applies backoff without failing the pipeline.
 * 5. Advisory Only: Reputation results are supporting evidence and NEVER override mandatory local blocks.
 */

const https = require('https');
const url = require('url');

// Sensitive parameter patterns that MUST be stripped before any lookup
const SENSITIVE_PARAM_KEYS = new Set([
  'password', 'passwd', 'pass', 'pwd',
  'token', 'auth', 'key', 'apikey', 'api_key',
  'secret', 'session', 'sessionid', 'session_id',
  'jwt', 'code', 'access_token', 'refresh_token',
  'pin', 'credit_card', 'card', 'cvv'
]);

// Internal and private domain suffixes to reject
const PRIVATE_DOMAIN_SUFFIXES = [
  '.local', '.internal', '.localhost', '.test', '.invalid',
  '.example', '.lan', '.home', '.corp', '.intra'
];

// In-memory bounded cache: key (urlId) -> { data, cachedAt, expiresAt }
const MAX_CACHE_SIZE = 500;
const CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes
const reputationCache = new Map();

// Rate-limiting backoff tracker
let rateLimitedUntil = 0;

/**
 * Check if an IP address string belongs to a private / reserved range
 * @param {string} ip
 * @returns {boolean}
 */
function isPrivateIpAddress(ip) {
  if (!ip || typeof ip !== 'string') return false;

  // IPv4 Private & Loopback Checks
  const ipv4Parts = ip.split('.').map(Number);
  if (ipv4Parts.length === 4 && ipv4Parts.every(p => !isNaN(p) && p >= 0 && p <= 255)) {
    // 127.0.0.0/8 (Loopback)
    if (ipv4Parts[0] === 127) return true;
    // 10.0.0.0/8 (Private)
    if (ipv4Parts[0] === 10) return true;
    // 172.16.0.0/12 (Private: 172.16.0.0 - 172.31.255.255)
    if (ipv4Parts[0] === 172 && ipv4Parts[1] >= 16 && ipv4Parts[1] <= 31) return true;
    // 192.168.0.0/16 (Private)
    if (ipv4Parts[0] === 192 && ipv4Parts[1] === 168) return true;
    // 169.254.0.0/16 (Link-local)
    if (ipv4Parts[0] === 169 && ipv4Parts[1] === 254) return true;
    // 0.0.0.0
    if (ipv4Parts[0] === 0) return true;
  }

  // IPv6 Loopback / Private / Link-local Checks
  const lowerIp = ip.toLowerCase();
  if (lowerIp === '::1' || lowerIp === '::' || lowerIp.startsWith('fe80:') || lowerIp.startsWith('fc00:') || lowerIp.startsWith('fd00:')) {
    return true;
  }

  return false;
}

/**
 * Validate and sanitize URL for safe external VirusTotal lookup
 * Strips credentials, redacts sensitive query keys, and rejects private/unsupported hosts.
 *
 * @param {string} rawUrl
 * @returns {{ valid: boolean, normalizedUrl?: string, error?: string, errorCode?: string }}
 */
function validateAndSanitizeUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') {
    return { valid: false, error: 'Empty or invalid URL input.', errorCode: 'INVALID_INPUT' };
  }

  let parsed;
  try {
    parsed = new URL(rawUrl.trim());
  } catch (_) {
    return { valid: false, error: 'Malformed URL could not be parsed.', errorCode: 'MALFORMED_URL' };
  }

  // 1. Enforce strict HTTP/HTTPS protocols
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return {
      valid: false,
      error: `Unsupported protocol "${parsed.protocol}". Only HTTP and HTTPS destinations are supported.`,
      errorCode: 'UNSUPPORTED_PROTOCOL'
    };
  }

  const hostname = parsed.hostname.toLowerCase();

  // 2. Reject localhost and reserved hostnames
  if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '[::1]' || hostname === '0.0.0.0') {
    return {
      valid: false,
      error: 'Localhost and loopback destinations are excluded from VirusTotal lookups.',
      errorCode: 'PRIVATE_OR_INTERNAL_DESTINATION'
    };
  }

  // 3. Reject private IP subnets
  if (isPrivateIpAddress(hostname)) {
    return {
      valid: false,
      error: 'Private internal IP addresses are excluded from VirusTotal lookups.',
      errorCode: 'PRIVATE_OR_INTERNAL_DESTINATION'
    };
  }

  // 4. Reject private domain suffixes (.local, .internal, etc.)
  for (const suffix of PRIVATE_DOMAIN_SUFFIXES) {
    if (hostname.endsWith(suffix) || hostname === suffix.slice(1)) {
      return {
        valid: false,
        error: `Internal domain suffix "${suffix}" is excluded from VirusTotal lookups.`,
        errorCode: 'PRIVATE_OR_INTERNAL_DESTINATION'
      };
    }
  }

  // 5. Privacy Safeguard: Strip userinfo (username / password)
  parsed.username = '';
  parsed.password = '';

  // 6. Privacy Safeguard: Strip sensitive query parameters
  if (parsed.search) {
    const params = new URLSearchParams(parsed.search);
    let modified = false;
    for (const key of Array.from(params.keys())) {
      const lowerKey = key.toLowerCase();
      if (SENSITIVE_PARAM_KEYS.has(lowerKey)) {
        params.delete(key);
        modified = true;
      }
    }
    parsed.search = modified ? (params.toString() ? '?' + params.toString() : '') : parsed.search;
  }

  // 7. Normalize destination (strip trailing slash for root URL, lowercase scheme and host)
  let cleanUrl = parsed.toString();
  if (cleanUrl.endsWith('/') && parsed.pathname === '/' && !parsed.search && !parsed.hash) {
    cleanUrl = cleanUrl.slice(0, -1);
  }

  return {
    valid: true,
    normalizedUrl: cleanUrl,
    hostname
  };
}

/**
 * Generate standard VirusTotal v3 URL Identifier
 * (URL-safe base64 encoding without padding)
 *
 * @param {string} normalizedUrl
 * @returns {string} VirusTotal v3 URL ID
 */
function generateVirusTotalUrlId(normalizedUrl) {
  return Buffer.from(normalizedUrl).toString('base64url');
}

/**
 * Bounded Cache Lookup Helper
 */
function getCachedReputation(urlId) {
  if (!reputationCache.has(urlId)) return null;

  const entry = reputationCache.get(urlId);
  if (Date.now() > entry.expiresAt) {
    reputationCache.delete(urlId);
    return null;
  }

  // Return clone with cached: true
  return { ...entry.data, cached: true };
}

/**
 * Bounded Cache Storage Helper
 */
function setCachedReputation(urlId, data) {
  // Evict oldest if limit reached
  if (reputationCache.size >= MAX_CACHE_SIZE) {
    const oldestKey = reputationCache.keys().next().value;
    if (oldestKey) reputationCache.delete(oldestKey);
  }

  reputationCache.set(urlId, {
    data,
    cachedAt: Date.now(),
    expiresAt: Date.now() + CACHE_TTL_MS
  });
}

/**
 * Clear in-memory cache (useful for automated testing)
 */
function clearReputationCache() {
  reputationCache.clear();
  rateLimitedUntil = 0;
}

/**
 * Map VirusTotal v3 last_analysis_stats into clear, distinct verdict states
 *
 * @param {Object} stats - { harmless, malicious, suspicious, undetected, timeout }
 * @returns {"malicious"|"suspicious"|"clean/no detections"|"unknown"}
 */
function computeReputationVerdict(stats) {
  if (!stats || typeof stats !== 'object') {
    return 'unknown';
  }

  const malicious = Number(stats.malicious) || 0;
  const suspicious = Number(stats.suspicious) || 0;
  const harmless = Number(stats.harmless) || 0;
  const undetected = Number(stats.undetected) || 0;

  if (malicious > 0) {
    return 'malicious';
  }
  if (suspicious > 0) {
    return 'suspicious';
  }
  if (harmless > 0 || undetected > 0) {
    return 'clean/no detections';
  }

  return 'unknown';
}

/**
 * Perform VirusTotal v3 URL Report Lookup
 *
 * @param {string} targetUrl - Raw target URL
 * @param {Object} [options] - Optional override parameters (e.g. for testing)
 * @param {string} [options.apiKey] - Optional custom API key
 * @param {boolean} [options.enabled] - Optional enable flag
 * @param {number} [options.timeoutMs] - Request timeout (default: 10000ms)
 * @param {Function} [options.httpTransport] - Optional mock transport for testing
 * @returns {Promise<Object>} Sanitized reputation outcome
 */
async function lookupUrlReputation(targetUrl, options = {}) {
  const envKey = options.apiKey !== undefined ? options.apiKey : (process.env.VT_API_KEY || '');
  const isEnabled = options.enabled !== undefined
    ? Boolean(options.enabled)
    : (process.env.VT_ENABLED !== 'false' && Boolean(envKey));

  // 1. Sanitize & validate destination first (before inspecting keys or spending network)
  const validation = validateAndSanitizeUrl(targetUrl);
  if (!validation.valid) {
    return {
      success: false,
      provider: 'VirusTotal v3',
      status: 'rejected',
      verdict: 'unavailable',
      lookupStatus: validation.errorCode || 'REJECTED',
      error: validation.error,
      checkedAt: new Date().toISOString()
    };
  }

  const normalizedUrl = validation.normalizedUrl;
  const urlId = generateVirusTotalUrlId(normalizedUrl);

  // 2. Check Bounded Memory Cache
  const cached = getCachedReputation(urlId);
  if (cached) {
    return cached;
  }

  // 3. Check if VirusTotal is configured and enabled
  if (!isEnabled || !envKey) {
    return {
      success: false,
      provider: 'VirusTotal v3',
      status: 'disabled',
      verdict: 'unavailable',
      lookupStatus: 'DISABLED_OR_UNCONFIGURED',
      error: !envKey
        ? 'VT_API_KEY is not configured in backend environment.'
        : 'VirusTotal integration is disabled (VT_ENABLED=false).',
      checkedAt: new Date().toISOString(),
      normalizedTarget: normalizedUrl
    };
  }

  // 4. Check active rate-limit backoff
  if (Date.now() < rateLimitedUntil) {
    const remainingSec = Math.ceil((rateLimitedUntil - Date.now()) / 1000);
    return {
      success: false,
      provider: 'VirusTotal v3',
      status: 'rate_limited',
      verdict: 'unavailable',
      lookupStatus: 'RATE_LIMITED',
      error: `VirusTotal API rate limit active. Retry in ${remainingSec}s.`,
      checkedAt: new Date().toISOString(),
      normalizedTarget: normalizedUrl
    };
  }

  // 5. Execute HTTP Request to VirusTotal v3 endpoint
  const timeoutMs = options.timeoutMs || 10000;

  try {
    const rawResult = await (options.httpTransport
      ? options.httpTransport(urlId, envKey, timeoutMs)
      : executeVirusTotalRequest(urlId, envKey, timeoutMs));

    // Handle 404 Not Found (URL not yet analyzed in VirusTotal)
    if (rawResult.statusCode === 404) {
      const notFoundResult = {
        success: true,
        provider: 'VirusTotal v3',
        status: 'unknown',
        verdict: 'unknown',
        lookupStatus: 'NOT_FOUND_IN_DATASET',
        stats: { harmless: 0, malicious: 0, suspicious: 0, undetected: 0, timeout: 0 },
        totalEngines: 0,
        reputation: 0,
        cached: false,
        checkedAt: new Date().toISOString(),
        normalizedTarget: normalizedUrl,
        notice: 'Target has no prior analysis report in VirusTotal v3 dataset. Treated as unverified under zero-trust policy.'
      };
      setCachedReputation(urlId, notFoundResult);
      return notFoundResult;
    }

    // Handle 429 Rate Limit / Quota Exceeded
    if (rawResult.statusCode === 429) {
      rateLimitedUntil = Date.now() + 60000; // 60s cooldown
      return {
        success: false,
        provider: 'VirusTotal v3',
        status: 'rate_limited',
        verdict: 'unavailable',
        lookupStatus: 'RATE_LIMITED',
        error: 'VirusTotal v3 API quota or rate limit exceeded (HTTP 429).',
        checkedAt: new Date().toISOString(),
        normalizedTarget: normalizedUrl
      };
    }

    // Handle non-200 responses
    if (rawResult.statusCode !== 200) {
      return {
        success: false,
        provider: 'VirusTotal v3',
        status: 'error',
        verdict: 'error',
        lookupStatus: `HTTP_${rawResult.statusCode}`,
        error: `VirusTotal API returned HTTP ${rawResult.statusCode}`,
        checkedAt: new Date().toISOString(),
        normalizedTarget: normalizedUrl
      };
    }

    // Parse valid JSON body
    let parsedBody;
    try {
      parsedBody = typeof rawResult.body === 'string' ? JSON.parse(rawResult.body) : rawResult.body;
    } catch (parseErr) {
      return {
        success: false,
        provider: 'VirusTotal v3',
        status: 'error',
        verdict: 'error',
        lookupStatus: 'PARSE_ERROR',
        error: 'Failed to parse VirusTotal response JSON.',
        checkedAt: new Date().toISOString(),
        normalizedTarget: normalizedUrl
      };
    }

    const attributes = parsedBody?.data?.attributes || {};
    const stats = attributes.last_analysis_stats || {
      harmless: 0,
      malicious: 0,
      suspicious: 0,
      undetected: 0,
      timeout: 0
    };

    const verdict = computeReputationVerdict(stats);
    const totalEngines = Object.values(stats).reduce((acc, val) => acc + (Number(val) || 0), 0);

    const result = {
      success: true,
      provider: 'VirusTotal v3',
      status: 'ok',
      verdict, // "malicious", "suspicious", "clean/no detections", "unknown"
      stats: {
        harmless: Number(stats.harmless) || 0,
        malicious: Number(stats.malicious) || 0,
        suspicious: Number(stats.suspicious) || 0,
        undetected: Number(stats.undetected) || 0,
        timeout: Number(stats.timeout) || 0
      },
      totalEngines,
      reputation: typeof attributes.reputation === 'number' ? attributes.reputation : 0,
      lastAnalysisDate: attributes.last_analysis_date
        ? new Date(attributes.last_analysis_date * 1000).toISOString()
        : null,
      cached: false,
      lookupStatus: 'COMPLETED',
      checkedAt: new Date().toISOString(),
      normalizedTarget: normalizedUrl
    };

    // Cache successful evaluation
    setCachedReputation(urlId, result);
    return result;

  } catch (err) {
    const isTimeout = err.name === 'AbortError' || err.message?.includes('timeout') || err.message?.includes('timed out');
    return {
      success: false,
      provider: 'VirusTotal v3',
      status: isTimeout ? 'timeout' : 'error',
      verdict: 'error',
      lookupStatus: isTimeout ? 'TIMEOUT' : 'NETWORK_ERROR',
      error: isTimeout ? 'VirusTotal API request timed out.' : `Network error: ${err.message}`,
      checkedAt: new Date().toISOString(),
      normalizedTarget: normalizedUrl
    };
  }
}

/**
 * Execute real HTTPS GET to VirusTotal v3
 */
function executeVirusTotalRequest(urlId, apiKey, timeoutMs) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'www.virustotal.com',
      port: 443,
      path: `/api/v3/urls/${encodeURIComponent(urlId)}`,
      method: 'GET',
      headers: {
        'x-apikey': apiKey,
        'Accept': 'application/json',
        'User-Agent': 'EDITH-SentinelX-CyberDefense/1.0'
      },
      timeout: timeoutMs
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => { body += chunk; });
      res.on('end', () => {
        resolve({ statusCode: res.statusCode, body });
      });
    });

    req.on('timeout', () => {
      req.destroy();
      reject(new Error(`VirusTotal API request timed out after ${timeoutMs}ms`));
    });

    req.on('error', (err) => {
      reject(err);
    });

    req.end();
  });
}

module.exports = {
  validateAndSanitizeUrl,
  generateVirusTotalUrlId,
  computeReputationVerdict,
  lookupUrlReputation,
  clearReputationCache,
  clearVirusTotalCache: clearReputationCache,
  isPrivateIpAddress,
  MAX_CACHE_SIZE,
  CACHE_TTL_MS
};
