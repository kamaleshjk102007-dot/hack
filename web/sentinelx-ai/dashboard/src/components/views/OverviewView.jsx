// sentinelx-ai/dashboard/src/components/views/OverviewView.jsx
import React from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  HelpCircle,
  Activity,
  Zap,
  ArrowUpRight,
  Radio,
  Clock,
  Terminal
} from 'lucide-react';

export default function OverviewView({
  incidents = [],
  onSelectIncident,
  onNavigateView,
  demoMode = true
}) {
  const highRiskCount = incidents.filter(i => i.riskLevel === 'HIGH_RISK').length;
  const unknownCount = incidents.filter(i => i.riskLevel === 'UNKNOWN').length;
  const blockedCount = incidents.filter(i => i.actualActionTaken === 'RULE_BLOCK_ENFORCED').length;
  const lowRiskCount = incidents.filter(i => i.riskLevel === 'LOW_RISK').length;

  return (
    <div className="view-container">
      {/* Top Banner Notice if in Demo Mode */}
      {demoMode && (
        <div className="demo-banner">
          <div className="demo-banner-content">
            <span className="demo-tag">DEMO MODE ACTIVE</span>
            <span>
              Displaying verified simulation fixtures. Live extension events are synchronized automatically when EDITH AI is active in Chrome.
            </span>
          </div>
          <button className="btn-cyber-ghost btn-sm" onClick={() => onNavigateView('settings')}>
            Configure FastAPI
          </button>
        </div>
      )}

      {/* Hero SOC Metrics Grid */}
      <div className="metrics-grid">
        {/* Analyzed Targets */}
        <div className="metric-box glow-cyan">
          <div className="metric-top">
            <span className="metric-title">TARGETS INSPECTED</span>
            <div className="metric-icon-wrap cyan">
              <Activity size={18} />
            </div>
          </div>
          <div className="metric-val">{incidents.length}</div>
          <div className="metric-footer">
            <span className="trend-pos">100% Zero-Trust Evaluated</span>
          </div>
        </div>

        {/* High Risk Intercepted */}
        <div className="metric-box glow-red">
          <div className="metric-top">
            <span className="metric-title">HIGH-RISK THREATS</span>
            <div className="metric-icon-wrap red">
              <ShieldAlert size={18} />
            </div>
          </div>
          <div className="metric-val red">{highRiskCount}</div>
          <div className="metric-footer">
            <span className="trend-neg">Phishing & C2 Signatures</span>
          </div>
        </div>

        {/* Unknown Assessments */}
        <div className="metric-box glow-blue">
          <div className="metric-top">
            <span className="metric-title">UNKNOWN ASSESSMENTS</span>
            <div className="metric-icon-wrap blue">
              <HelpCircle size={18} />
            </div>
          </div>
          <div className="metric-val blue">{unknownCount}</div>
          <div className="metric-footer">
            <span className="trend-neutral">Unverified Reputations</span>
          </div>
        </div>

        {/* Successfully Blocked */}
        <div className="metric-box glow-purple">
          <div className="metric-top">
            <span className="metric-title">CONTAINMENT BLOCKED</span>
            <div className="metric-icon-wrap purple">
              <Zap size={18} />
            </div>
          </div>
          <div className="metric-val purple">{blockedCount}</div>
          <div className="metric-footer">
            <span className="trend-verified">Dynamic Rules Enforced</span>
          </div>
        </div>
      </div>

      {/* Middle Layout: Attack Vector Stream & Interactive Threat Distribution */}
      <div className="two-col-grid">
        {/* Real-time Threat Stream */}
        <div className="cyber-card">
          <div className="cyber-card-header">
            <div>
              <div className="card-title">
                <Radio className="pulse-icon" size={16} />
                <span>Live Autonomous Threat Feed</span>
              </div>
              <div className="card-subtitle">Realtime declarative stream of active tab inspections</div>
            </div>
            <button className="btn-cyber-ghost btn-sm" onClick={() => onNavigateView('threat-monitor')}>
              Full Monitor
            </button>
          </div>

          <div className="threat-feed-list">
            {incidents.slice(0, 4).map((inc) => (
              <div key={inc.id} className="threat-feed-item" onClick={() => onSelectIncident(inc)}>
                <div className="feed-item-left">
                  <span className={`risk-indicator-dot ${inc.riskLevel}`}></span>
                  <div className="feed-info">
                    <span className="feed-url" title={inc.url}>{inc.domain || inc.url}</span>
                    <span className="feed-class">{inc.classification}</span>
                  </div>
                </div>
                <div className="feed-item-right">
                  <span className={`badge-risk ${inc.riskLevel}`}>{inc.riskLevel?.replace('_', ' ')}</span>
                  <ArrowUpRight size={14} className="hover-arrow" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Threat Distribution Chart & Defense Posture */}
        <div className="cyber-card">
          <div className="cyber-card-header">
            <div>
              <div className="card-title">
                <ShieldCheck size={16} />
                <span>Zero-Trust Defense Posture</span>
              </div>
              <div className="card-subtitle">Classification breakdown of inspected destinations</div>
            </div>
          </div>

          {/* SVG Vector Doughnut & Statistics */}
          <div className="posture-chart-row">
            <div className="svg-doughnut-wrap">
              <svg viewBox="0 0 100 100" className="posture-doughnut">
                {/* Background Ring */}
                <circle cx="50" cy="50" r="38" className="donut-bg" />
                {/* Segments (Simulated Scaled Arcs) */}
                <circle
                  cx="50" cy="50" r="38"
                  className="donut-seg red"
                  strokeDasharray={`${Math.max(10, (highRiskCount / (incidents.length || 1)) * 238)} 238`}
                  strokeDashoffset="0"
                />
                <circle
                  cx="50" cy="50" r="38"
                  className="donut-seg blue"
                  strokeDasharray={`${Math.max(10, (unknownCount / (incidents.length || 1)) * 238)} 238`}
                  strokeDashoffset={`-${(highRiskCount / (incidents.length || 1)) * 238}`}
                />
              </svg>
              <div className="donut-center-stat">
                <span className="donut-main-num">{incidents.length}</span>
                <span className="donut-lbl">EVENTS</span>
              </div>
            </div>

            <div className="posture-breakdown-list">
              <div className="breakdown-row">
                <div className="breakdown-lbl">
                  <span className="legend-dot red"></span>
                  <span>High Risk (Blocked/Flagged)</span>
                </div>
                <span className="breakdown-count red">{highRiskCount}</span>
              </div>
              <div className="breakdown-row">
                <div className="breakdown-lbl">
                  <span className="legend-dot blue"></span>
                  <span>Unknown (Neutral Zero-Trust)</span>
                </div>
                <span className="breakdown-count blue">{unknownCount}</span>
              </div>
              <div className="breakdown-row">
                <div className="breakdown-lbl">
                  <span className="legend-dot green"></span>
                  <span>Low Risk (Verified Infra)</span>
                </div>
                <span className="breakdown-count green">{lowRiskCount}</span>
              </div>
              <div className="breakdown-row">
                <div className="breakdown-lbl">
                  <span className="legend-dot purple"></span>
                  <span>Dynamic NetRules Enforced</span>
                </div>
                <span className="breakdown-count purple">{blockedCount}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Table: Recent Security Interceptions */}
      <div className="cyber-card">
        <div className="cyber-card-header">
          <div>
            <div className="card-title">
              <Clock size={16} />
              <span>Recent Interceptions & Investigations</span>
            </div>
            <div className="card-subtitle">Click any row to view complete forensic breakdown and AI explanation</div>
          </div>
        </div>

        <div className="cyber-table-container">
          <table className="cyber-table">
            <thead>
              <tr>
                <th>INCIDENT ID</th>
                <th>TARGET DOMAIN & URI</th>
                <th>CLASSIFICATION</th>
                <th>RISK LEVEL</th>
                <th>ACTION TAKEN</th>
                <th>TIMESTAMP</th>
                <th>DETAILS</th>
              </tr>
            </thead>
            <tbody>
              {incidents.slice(0, 5).map((inc) => (
                <tr key={inc.id} onClick={() => onSelectIncident(inc)} className="clickable-row">
                  <td>
                    <span className="mono-tag">{inc.id}</span>
                  </td>
                  <td>
                    <div className="table-url-cell" title={inc.url}>
                      <span className="table-domain">{inc.domain}</span>
                      <span className="table-path">{inc.url}</span>
                    </div>
                  </td>
                  <td>{inc.classification}</td>
                  <td>
                    <span className={`badge-risk ${inc.riskLevel}`}>{inc.riskLevel?.replace('_', ' ')}</span>
                  </td>
                  <td>
                    <span className="action-tag">{inc.actualActionTaken}</span>
                  </td>
                  <td>
                    <span className="table-time">{new Date(inc.timestamp).toLocaleTimeString()}</span>
                  </td>
                  <td>
                    <button className="btn-cyber-ghost btn-xs">
                      Inspect
                    </button>
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
