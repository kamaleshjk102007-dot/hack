// sentinelx-ai/dashboard/src/types/schema.js
/**
 * SentinelX AI - Core Data Schema Definitions
 * Establishes contract for Extension Events, SOC Incidents,
 * Self-Healing Rules, Threat Intelligence, and Gemma AI Investigations.
 */

/**
 * @typedef {'HIGH_RISK' | 'SUSPICIOUS' | 'UNKNOWN' | 'LOW_RISK'} RiskLevel
 * @typedef {'Healthy' | 'Degraded' | 'Repairing' | 'Verified' | 'Failed'} HealthState
 * @typedef {'INSPECTED' | 'RULE_BLOCK_ENFORCED' | 'QUARANTINED' | 'BYPASSED'} ActionTaken
 * @typedef {'ACTIVE' | 'ENFORCED' | 'PENDING' | 'CORRUPTED' | 'DISABLED'} RuleStatus
 */

export const RISK_LEVELS = {
  HIGH_RISK: 'HIGH_RISK',
  SUSPICIOUS: 'SUSPICIOUS',
  UNKNOWN: 'UNKNOWN',
  LOW_RISK: 'LOW_RISK'
};

export const HEALTH_STATES = {
  HEALTHY: 'Healthy',
  DEGRADED: 'Degraded',
  REPAIRING: 'Repairing',
  VERIFIED: 'Verified',
  FAILED: 'Failed'
};

export const DEFAULT_CONFIG = {
  apiBaseUrl: 'http://localhost:8000/api/v1',
  gemmaEndpoint: 'http://localhost:8000/api/v1/ai/gemma-investigate',
  zeroTrustStrictness: 'High (Neutral sites default UNKNOWN)',
  autoBlockScoreThreshold: 80,
  telemetryIngestion: true,
  demoMode: true
};
