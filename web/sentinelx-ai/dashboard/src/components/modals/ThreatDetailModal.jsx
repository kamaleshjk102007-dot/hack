// sentinelx-ai/dashboard/src/components/modals/ThreatDetailModal.jsx
import React from 'react';
import {
  X,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  BrainCircuit,
  ExternalLink,
  Lock,
  Terminal,
  Activity
} from 'lucide-react';

export default function ThreatDetailModal({ incident, onClose, onBlockDomain }) {
  if (!incident) return null;

  return (
    <div className="threat-modal-backdrop" onClick={onClose}>
      <div className="threat-modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="threat-modal-header">
          <div className="header-meta">
            <div className="incident-id-badge">
              <ShieldAlert size={14} />
              <span>{incident.id || 'INCIDENT'}</span>
              {incident.isDemo && <span className="demo-tag">DEMO FIXTURE</span>}
            </div>
            <h2 className="threat-modal-title">{incident.classification || 'Threat Analysis'}</h2>
          </div>
          <button className="btn-modal-close" onClick={onClose} title="Close inspection">
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="threat-modal-body">
          {/* Target Resource Banner */}
          <div className="threat-target-banner">
            <div className="banner-top">
              <span className="banner-lbl">TARGET URI & DOMAIN:</span>
              <span className={`badge-risk ${incident.riskLevel}`}>
                {incident.riskLevel?.replace('_', ' ')} • SCORE {incident.riskScore}/100
              </span>
            </div>
            <div className="target-url-code">{incident.url}</div>
            <div className="target-domain-sub">
              <strong>Domain Authority:</strong> {incident.domain}
            </div>
          </div>

          {/* Grid of Forensic Attributes */}
          <div className="forensic-grid">
            {/* Detection Source */}
            <div className="forensic-item">
              <div className="forensic-lbl">
                <Activity size={13} />
                <span>Detection Source</span>
              </div>
              <div className="forensic-val">{incident.detectionSource || 'EDITH AI Zero-Trust Engine'}</div>
            </div>

            {/* Timestamp */}
            <div className="forensic-item">
              <div className="forensic-lbl">
                <Terminal size={13} />
                <span>Incident Timestamp</span>
              </div>
              <div className="forensic-val mono">{incident.timestamp || new Date().toISOString()}</div>
            </div>

            {/* Action Status */}
            <div className="forensic-item">
              <div className="forensic-lbl">
                <Lock size={13} />
                <span>Action Status</span>
              </div>
              <div className="forensic-val">{incident.actionStatus || 'Inspected'}</div>
            </div>

            {/* Verification Result */}
            <div className="forensic-item">
              <div className="forensic-lbl">
                <CheckCircle2 size={13} />
                <span>Verification Result</span>
              </div>
              <div className="forensic-val highlight-green">{incident.verificationResult || 'Verified: Operational'}</div>
            </div>
          </div>

          {/* Evidence Panel */}
          <div className="modal-section">
            <h3 className="section-heading">Observed Threat Evidence:</h3>
            <div className="evidence-items-list">
              {incident.evidence && incident.evidence.length > 0 ? (
                incident.evidence.map((ev, idx) => (
                  <div key={idx} className="evidence-row">
                    <span className="evidence-badge">{ev.category || 'FINDING'}</span>
                    <span className="evidence-desc">{ev.detail || ev.toString()}</span>
                  </div>
                ))
              ) : (
                <div className="evidence-empty">No specific structural anomalies recorded.</div>
              )}
            </div>
          </div>

          {/* AI Explanation & Reasoning */}
          <div className="modal-section gemma-section">
            <div className="gemma-header">
              <BrainCircuit size={16} className="gemma-icon" />
              <h3 className="section-heading">Gemma AI Forensic Analysis:</h3>
            </div>
            <p className="gemma-text">
              {incident.aiExplanation || 'Deterministic zero-trust heuristics evaluated. Target exhibits structural signatures that violate safe browsing baselines.'}
            </p>
          </div>

          {/* Remediation & Action Taken */}
          <div className="remediation-box">
            <div className="remedy-col">
              <span className="remedy-lbl">RECOMMENDED ACTION:</span>
              <span className="remedy-val">{incident.recommendedAction || 'Enforce containment'}</span>
            </div>
            <div className="remedy-col">
              <span className="remedy-lbl">ACTUAL ACTION TAKEN:</span>
              <span className="remedy-val highlight-cyan">{incident.actualActionTaken || 'INSPECTED'}</span>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="threat-modal-footer">
          <button className="btn-cyber-ghost" onClick={onClose}>
            Close Inspection
          </button>
          {incident.domain && incident.domain !== 'Browser Internal' && (
            <button
              className="btn-cyber-danger"
              onClick={() => {
                if (onBlockDomain) onBlockDomain(incident.domain);
                onClose();
              }}
            >
              <ShieldAlert size={14} />
              Enforce Dynamic Block on {incident.domain}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
