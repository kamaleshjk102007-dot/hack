// sentinelx-ai/dashboard/src/components/views/SelfHealingView.jsx
import React, { useState, useEffect } from 'react';
import {
  Wrench,
  ShieldCheck,
  AlertTriangle,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Activity,
  Layers,
  Cpu
} from 'lucide-react';
import { dataProvider } from '../../services/dataProvider.js';

export default function SelfHealingView() {
  const [rules, setRules] = useState([]);
  const [state, setState] = useState('Healthy'); // Healthy | Degraded | Repairing | Verified | Failed
  const [repairLog, setRepairLog] = useState(null);
  const [simulateFailure, setSimulateFailure] = useState(false);
  const [loading, setLoading] = useState(false);

  const loadRules = async () => {
    const list = await dataProvider.getSelfHealingRules();
    setRules(list);
    const hasFailure = list.some(r => r.status === 'FAILED');
    if (hasFailure) {
      setState('Failed');
    } else {
      setState('Healthy');
    }
  };

  useEffect(() => {
    loadRules();
  }, []);

  const handleRunDiagnostic = async () => {
    setState('Repairing');
    setLoading(true);

    try {
      const outcome = await dataProvider.runSelfHealingDiagnostic(simulateFailure);
      setState(outcome.status);
      setRepairLog(outcome);
      await loadRules();
    } catch (err) {
      setState('Failed');
      setRepairLog({
        status: 'Failed',
        failureExplanation: err.message || 'Diagnostic execution aborted.'
      });
    } finally {
      setLoading(false);
    }
  };

  const missingRules = rules.filter(r => r.required && r.status !== 'ACTIVE');

  return (
    <div className="view-container">
      {/* Header */}
      <div className="view-toolbar">
        <div>
          <div className="view-title-row">
            <Wrench className="title-icon" size={22} />
            <h2 className="view-heading">Self-Healing Defense Center</h2>
            <span className={`state-badge ${state}`}>STATE: {state.toUpperCase()}</span>
          </div>
          <p className="view-subheading">
            Continuous autonomous reconciliation for Chrome declarativeNetRequest rules, CSP hooks, and storage mirrors
          </p>
        </div>

        <div className="toolbar-controls">
          <label className="failure-sim-toggle" title="Test error handling without fabricating false success">
            <input
              type="checkbox"
              checked={simulateFailure}
              onChange={(e) => setSimulateFailure(e.target.checked)}
            />
            <span>Simulate Corruption</span>
          </label>

          <button
            className="btn-cyber-primary"
            onClick={handleRunDiagnostic}
            disabled={loading}
          >
            <RotateCcw className={loading ? 'spin-icon' : ''} size={14} />
            <span>{loading ? 'Reconciling Rules...' : 'Run Integrity Diagnostic'}</span>
          </button>
        </div>
      </div>

      {/* Missing Rules Warning Banner */}
      {missingRules.length > 0 && (
        <div className="warning-banner-callout">
          <AlertTriangle size={20} className="warn-icon" />
          <div className="warn-text-wrap">
            <h4 className="warn-title">Critical Protection Rule Degradation Detected</h4>
            <p className="warn-desc">
              {missingRules.length} mandatory defense policy is currently not ACTIVE. Threat interception capabilities may be degraded.
            </p>
          </div>
        </div>
      )}

      {/* Verification Outcome Card if recently executed */}
      {repairLog && (
        <div className={`repair-outcome-card ${repairLog.status}`}>
          <div className="outcome-header">
            {repairLog.status === 'Verified' ? (
              <CheckCircle2 size={18} className="icon-green" />
            ) : (
              <XCircle size={18} className="icon-red" />
            )}
            <h3 className="outcome-title">
              Verification Outcome: {repairLog.status}
            </h3>
            <span className="outcome-time">{repairLog.verifiedAt}</span>
          </div>
          <p className="outcome-desc">
            {repairLog.verificationResult || repairLog.failureExplanation}
          </p>
          {repairLog.failureExplanation && (
            <div className="failure-reason-box">
              <strong>Failure Diagnostics:</strong> {repairLog.failureExplanation}
            </div>
          )}
        </div>
      )}

      {/* Required Protection Rules Table */}
      <div className="cyber-card">
        <div className="cyber-card-header">
          <div>
            <div className="card-title">
              <Layers size={16} />
              <span>Required Protection Rules & Checksum Matrix</span>
            </div>
            <div className="card-subtitle">
              Live status, cryptographic checksums, and repair history for all core protection components
            </div>
          </div>
        </div>

        <div className="cyber-table-container">
          <table className="cyber-table">
            <thead>
              <tr>
                <th>RULE ID</th>
                <th>PROTECTION SUBSYSTEM</th>
                <th>CATEGORY</th>
                <th>MANDATORY</th>
                <th>STATUS</th>
                <th>CHECKSUM</th>
                <th>REPAIRS</th>
                <th>OUTCOME / FAILURE REASON</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>
                    <span className="mono-tag">{rule.id}</span>
                  </td>
                  <td>
                    <div className="rule-name-cell">
                      <span className="rule-name">{rule.name}</span>
                      <span className="rule-desc">{rule.description}</span>
                    </div>
                  </td>
                  <td>
                    <span className="category-chip">{rule.category}</span>
                  </td>
                  <td>
                    {rule.required ? (
                      <span className="req-tag required">Required</span>
                    ) : (
                      <span className="req-tag optional">Optional</span>
                    )}
                  </td>
                  <td>
                    <span className={`status-pill ${rule.status}`}>
                      {rule.status}
                    </span>
                  </td>
                  <td>
                    <span className="checksum-code">{rule.checksum}</span>
                  </td>
                  <td>
                    <span className="repairs-num">{rule.repairAttempts}</span>
                  </td>
                  <td>
                    {rule.failureReason ? (
                      <span className="failure-chip" title={rule.failureReason}>
                        {rule.failureReason}
                      </span>
                    ) : (
                      <span className="outcome-chip">{rule.lastOutcome}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
