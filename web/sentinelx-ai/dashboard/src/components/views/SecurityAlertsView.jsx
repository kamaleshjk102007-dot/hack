// sentinelx-ai/dashboard/src/components/views/SecurityAlertsView.jsx
import React, { useState } from 'react';
import { Bell, CheckCircle2, AlertTriangle, ShieldAlert, Check, Trash2 } from 'lucide-react';
import { DEMO_SECURITY_ALERTS } from '../../services/mockData.js';

export default function SecurityAlertsView({ onAcknowledgeAlert }) {
  const [alerts, setAlerts] = useState(DEMO_SECURITY_ALERTS);
  const [filterSeverity, setFilterSeverity] = useState('ALL');

  const handleAck = (id) => {
    setAlerts(alerts.map(a => a.id === id ? { ...a, acknowledged: true } : a));
    if (onAcknowledgeAlert) onAcknowledgeAlert(id);
  };

  const handleDismissAll = () => {
    setAlerts(alerts.map(a => ({ ...a, acknowledged: true })));
  };

  const filtered = alerts.filter(a =>
    filterSeverity === 'ALL' || a.severity === filterSeverity
  );

  return (
    <div className="view-container">
      <div className="view-toolbar">
        <div>
          <div className="view-title-row">
            <Bell className="title-icon" size={22} />
            <h2 className="view-heading">Security Incident Alerts</h2>
            <span className="alert-count-pill">{alerts.filter(a => !a.acknowledged).length} PENDING</span>
          </div>
          <p className="view-subheading">
            Actionable high-priority notifications emitted by the autonomous browser defense engine
          </p>
        </div>

        <div className="toolbar-controls">
          <div className="filter-pills">
            {['ALL', 'CRITICAL', 'HIGH', 'WARNING', 'INFO'].map(sev => (
              <button
                key={sev}
                className={`filter-pill ${filterSeverity === sev ? 'active' : ''}`}
                onClick={() => setFilterSeverity(sev)}
              >
                {sev}
              </button>
            ))}
          </div>

          <button className="btn-cyber-ghost btn-sm" onClick={handleDismissAll}>
            <Check size={14} />
            <span>Acknowledge All</span>
          </button>
        </div>
      </div>

      <div className="alerts-stack">
        {filtered.map((alt) => (
          <div key={alt.id} className={`alert-card ${alt.severity} ${alt.acknowledged ? 'ack' : ''}`}>
            <div className="alert-card-left">
              <div className={`alert-severity-badge ${alt.severity}`}>
                {alt.severity === 'CRITICAL' && <ShieldAlert size={16} />}
                {alt.severity === 'HIGH' && <ShieldAlert size={16} />}
                {alt.severity === 'WARNING' && <AlertTriangle size={16} />}
                {alt.severity === 'INFO' && <CheckCircle2 size={16} />}
                <span>{alt.severity}</span>
              </div>
              <div className="alert-content">
                <div className="alert-title-row">
                  <h4 className="alert-title">{alt.title}</h4>
                  <span className="mono-tag">{alt.id}</span>
                </div>
                <p className="alert-summary">{alt.summary}</p>
                <div className="alert-timestamp">
                  {new Date(alt.timestamp).toLocaleTimeString()} • {new Date(alt.timestamp).toLocaleDateString()}
                </div>
              </div>
            </div>

            <div className="alert-card-right">
              {!alt.acknowledged ? (
                <button className="btn-cyber-primary btn-sm" onClick={() => handleAck(alt.id)}>
                  Acknowledge
                </button>
              ) : (
                <span className="ack-status">✓ Acknowledged</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
