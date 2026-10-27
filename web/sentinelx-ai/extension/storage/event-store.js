// sentinelx-ai/extension/storage/event-store.js
/**
 * SentinelX AI - Local Security Event Store & Persistence Subsystem
 * Handles safe, privacy-preserving persistence of URL security analyses,
 * risk assessments, blocking actions, and self-healing verification records
 * using Chrome Storage API (chrome.storage.local).
 */

const STORAGE_KEYS = {
  EVENTS: 'sentinelx_security_events',
  PROTECTION_STATUS: 'sentinelx_protection_status',
  MANAGED_BLOCKLIST: 'sentinelx_managed_blocklist',
  CONFIG: 'sentinelx_config'
};

const MAX_STORED_EVENTS = 100;
const DEDUPLICATION_WINDOW_MS = 4000; // 4 second window to prevent duplicate event spam

// Sensitive query parameters that MUST be redacted for user privacy
const SENSITIVE_PARAM_KEYS = new Set([
  'password', 'passwd', 'pass', 'pwd',
  'token', 'auth', 'key', 'apikey', 'api_key',
  'secret', 'session', 'sessionid', 'session_id',
  'jwt', 'code', 'access_token', 'refresh_token',
  'pin', 'credit_card', 'card', 'cvv'
]);

class EventStore {
  /**
   * Check if chrome.storage is available in the current context
   */
  static isAvailable() {
    return typeof chrome !== 'undefined' && Boolean(chrome.storage?.local);
  }

  /**
   * Privacy Safeguard: Safely sanitize URL before storage or transmission.
   * Strips embedded credentials (user:pass@) and redacts sensitive query values.
   * @param {string} rawUrl
   * @returns {string} Sanitized URL
   */
  static sanitizeUrl(rawUrl) {
    if (!rawUrl || typeof rawUrl !== 'string') {
      return 'unknown';
    }

    // Pass internal system schemes untouched
    if (rawUrl.startsWith('chrome://') || rawUrl.startsWith('chrome-extension://') || rawUrl.startsWith('about:')) {
      return rawUrl;
    }

    try {
      const parsed = new URL(rawUrl);

      // 1. Strip userinfo authentication credentials
      parsed.username = '';
      parsed.password = '';

      // 2. Redact sensitive query parameters
      if (parsed.search) {
        const params = new URLSearchParams(parsed.search);
        let modified = false;

        for (const key of params.keys()) {
          const lowerKey = key.toLowerCase();
          if (SENSITIVE_PARAM_KEYS.has(lowerKey)) {
            params.set(key, '[REDACTED]');
            modified = true;
          }
        }

        if (modified) {
          parsed.search = '?' + params.toString();
        }
      }

      return parsed.toString();
    } catch (_) {
      // If unparseable by URL parser, strip anything looking like auth or query credentials
      return rawUrl.replace(/:\/\/[^@]+@/, '://[REDACTED]@').split('?')[0];
    }
  }

  /**
   * Record a new security event with full audit metadata and deduplication
   * @param {Object} eventData
   * @returns {Promise<Object>} The stored event record
   */
  static async recordEvent(eventData = {}) {
    const sanitizedUrl = this.sanitizeUrl(eventData.url);
    const domain = (eventData.domain || '').trim().toLowerCase() || 'unknown';
    const actionAttempted = eventData.actionAttempted || (eventData.blocked ? 'BLOCK_RULE_REQUESTED' : 'INSPECT');
    const actualActionResult = eventData.actualActionResult || (eventData.blocked ? 'RULE_VERIFIED' : 'INSPECTED');
    const verificationStatus = eventData.verificationStatus || (eventData.blocked ? 'VERIFIED' : 'NOT_APPLICABLE');

    const record = {
      id: eventData.id || 'sec_inc_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7),
      timestamp: eventData.timestamp || new Date().toISOString(),
      url: sanitizedUrl,
      domain,
      riskScore: typeof eventData.riskScore === 'number' ? Math.max(0, Math.min(100, eventData.riskScore)) : 0,
      riskLevel: eventData.riskLevel || 'UNKNOWN',
      verdictReason: eventData.verdictReason || 'Standard heuristic inspection',
      findings: Array.isArray(eventData.findings) ? eventData.findings : [],
      actionAttempted,
      actualActionResult,
      verificationStatus,
      blocked: Boolean(eventData.blocked),
      blockRuleId: typeof eventData.blockRuleId === 'number' ? eventData.blockRuleId : null,
      error: eventData.error || null
    };

    if (!this.isAvailable()) {
      return record;
    }

    try {
      const existing = await this.getEvents(MAX_STORED_EVENTS);
      const now = Date.now();

      // Deduplication check: check if the most recent event is identical within DEDUPLICATION_WINDOW_MS
      if (existing.length > 0) {
        const latest = existing[0];
        const latestTime = new Date(latest.timestamp).getTime();
        const isRecent = (now - latestTime) < DEDUPLICATION_WINDOW_MS;

        if (isRecent && latest.url === record.url && latest.actionAttempted === record.actionAttempted) {
          // Update the existing record's timestamp and return it to avoid duplicate record spam
          latest.timestamp = record.timestamp;
          await chrome.storage.local.set({ [STORAGE_KEYS.EVENTS]: existing });
          return latest;
        }
      }

      // Prepend the new record, limited to MAX_STORED_EVENTS
      const updated = [record, ...existing].slice(0, MAX_STORED_EVENTS);
      await chrome.storage.local.set({ [STORAGE_KEYS.EVENTS]: updated });

      // Non-blocking background sync to local gateway if available
      if (typeof fetch !== 'undefined') {
        try {
          fetch('http://127.0.0.1:8787/api/sync', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ event: record })
          }).catch(() => {});
        } catch (_) {}
      }

      return record;
    } catch (err) {
      console.error('[SentinelX EventStore] Failed to record event:', err);
      return record;
    }
  }

  /**
   * Retrieve stored security events
   * @param {number} [limit=50]
   * @returns {Promise<Array>}
   */
  static async getEvents(limit = 50) {
    if (!this.isAvailable()) {
      return [];
    }

    try {
      const data = await chrome.storage.local.get(STORAGE_KEYS.EVENTS);
      const events = data[STORAGE_KEYS.EVENTS];
      if (!Array.isArray(events)) {
        return [];
      }
      return events.slice(0, limit);
    } catch (err) {
      console.error('[SentinelX EventStore] Failed to load events:', err);
      return [];
    }
  }

  /**
   * Clear all stored security events
   * @returns {Promise<boolean>}
   */
  static async clearEvents() {
    if (!this.isAvailable()) {
      return false;
    }

    try {
      await chrome.storage.local.set({ [STORAGE_KEYS.EVENTS]: [] });
      return true;
    } catch (err) {
      console.error('[SentinelX EventStore] Failed to clear events:', err);
      return false;
    }
  }

  /**
   * Retrieve aggregate statistics from stored events
   * @returns {Promise<Object>}
   */
  static async getEventStats() {
    const events = await this.getEvents(100);
    const stats = {
      totalAnalyzed: events.length,
      highRiskCount: 0,
      suspiciousCount: 0,
      unknownCount: 0,
      lowRiskCount: 0,
      blockedCount: 0
    };

    for (const evt of events) {
      if (evt.blocked) stats.blockedCount++;
      if (evt.riskLevel === 'HIGH_RISK') stats.highRiskCount++;
      else if (evt.riskLevel === 'SUSPICIOUS') stats.suspiciousCount++;
      else if (evt.riskLevel === 'LOW_RISK') stats.lowRiskCount++;
      else stats.unknownCount++;
    }

    return stats;
  }

  /**
   * Get the current protection status (enabled/disabled)
   * @returns {Promise<boolean>}
   */
  static async getProtectionStatus() {
    if (!this.isAvailable()) {
      return true;
    }

    try {
      const data = await chrome.storage.local.get(STORAGE_KEYS.PROTECTION_STATUS);
      // Default to enabled if not explicitly false
      return data[STORAGE_KEYS.PROTECTION_STATUS] !== false;
    } catch (err) {
      console.error('[SentinelX EventStore] Failed to get protection status:', err);
      return true;
    }
  }

  /**
   * Set protection active status
   * @param {boolean} enabled
   * @returns {Promise<boolean>}
   */
  static async setProtectionStatus(enabled) {
    if (!this.isAvailable()) {
      return false;
    }

    try {
      await chrome.storage.local.set({ [STORAGE_KEYS.PROTECTION_STATUS]: Boolean(enabled) });
      return true;
    } catch (err) {
      console.error('[SentinelX EventStore] Failed to set protection status:', err);
      return false;
    }
  }

  /**
   * Retrieve list of user-managed blocked domains for self-healing restoration
   * @returns {Promise<Array<{domain: string, ruleId: number, addedAt: string}>>}
   */
  static async getManagedBlocklist() {
    if (!this.isAvailable()) {
      return [];
    }
    try {
      const data = await chrome.storage.local.get(STORAGE_KEYS.MANAGED_BLOCKLIST);
      return Array.isArray(data[STORAGE_KEYS.MANAGED_BLOCKLIST]) ? data[STORAGE_KEYS.MANAGED_BLOCKLIST] : [];
    } catch (_) {
      return [];
    }
  }

  /**
   * Persist a domain in the managed blocklist
   * @param {string} domain
   * @param {number} ruleId
   * @returns {Promise<boolean>}
   */
  static async addManagedBlocklist(domain, ruleId) {
    if (!this.isAvailable()) return false;
    try {
      const list = await this.getManagedBlocklist();
      const existing = list.filter(item => item.domain !== domain && item.ruleId !== ruleId);
      existing.push({ domain, ruleId, addedAt: new Date().toISOString() });
      await chrome.storage.local.set({ [STORAGE_KEYS.MANAGED_BLOCKLIST]: existing });
      return true;
    } catch (_) {
      return false;
    }
  }

  /**
   * Remove a domain from the managed blocklist
   * @param {number} ruleId
   * @returns {Promise<boolean>}
   */
  static async removeManagedBlocklist(ruleId) {
    if (!this.isAvailable()) return false;
    try {
      const list = await this.getManagedBlocklist();
      const updated = list.filter(item => item.ruleId !== ruleId);
      await chrome.storage.local.set({ [STORAGE_KEYS.MANAGED_BLOCKLIST]: updated });
      return true;
    } catch (_) {
      return false;
    }
  }
}

// Export for Node.js unit tests and attach to global scope for extension contexts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { EventStore, STORAGE_KEYS };
}
if (typeof globalThis !== 'undefined') {
  globalThis.EventStore = EventStore;
}
