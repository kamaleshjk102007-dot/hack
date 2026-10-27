// sentinelx-ai/dashboard/src/components/common/Header.jsx
import React from 'react';
import { Shield, ShieldAlert, Cpu, Activity, RefreshCw, Server, AlertTriangle } from 'lucide-react';

export default function Header({
  activeTab,
  engineHealthy = true,
  backendConnected = false,
  demoMode = true,
  onToggleDemoMode,
  onQuickScan
}) {
  const [quickUrl, setQuickUrl] = React.useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (quickUrl.trim() && onQuickScan) {
      onQuickScan(quickUrl.trim());
      setQuickUrl('');
    }
  };

  return (
    <header className="dashboard-header">
      <div className="header-left">
        <div className="header-brand">
          <div className="header-shield">
            <Shield className="shield-icon" size={20} />
          </div>
          <div>
            <div className="brand-title">
              EDITH <span className="brand-accent">AI</span>
              <span className="soc-tag">SOC COMMAND</span>
            </div>
            <div className="brand-sub">Autonomous Threat Interceptor & Self-Healing Engine</div>
          </div>
        </div>
      </div>

      {/* Quick URL Scanner in Header */}
      <form className="header-search-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="header-search-input"
          placeholder="Quick scan domain or URI (e.g. http://192.168.1.1/login)..."
          value={quickUrl}
          onChange={(e) => setQuickUrl(e.target.value)}
          spellCheck="false"
        />
        <button type="submit" className="header-scan-btn">
          <Activity size={13} />
          <span>Inspect</span>
        </button>
      </form>

      {/* Live Telemetry Badges */}
      <div className="header-telemetry">
        {/* Engine State Indicator */}
        <div className={`hud-badge ${engineHealthy ? 'healthy' : 'degraded'}`} title="Realtime Declarative Threat Engine Health">
          <span className="hud-pulse"></span>
          <span className="hud-label">
            {engineHealthy ? 'PROTECTION VERIFIED' : 'ENGINE DEGRADED'}
          </span>
        </div>

        {/* Backend Connectivity Status */}
        <div className={`hud-badge ${backendConnected ? 'backend-online' : 'backend-standby'}`} title="FastAPI Remote Intelligence Bridge">
          <Server size={12} />
          <span className="hud-label">
            {backendConnected ? 'FASTAPI LIVE' : 'LOCAL / STANDBY'}
          </span>
        </div>

        {/* Explicit Demo Mode Indicator (Phase 5 Requirement) */}
        <div className="demo-toggle-group" title="Phase 5 Transparency: Toggles between real stored extension data and labeled demo fixtures">
          <span className="demo-pill">
            <AlertTriangle size={11} />
            DEMO MODE
          </span>
          <label className="demo-switch">
            <input
              type="checkbox"
              checked={demoMode}
              onChange={(e) => onToggleDemoMode(e.target.checked)}
            />
            <span className="demo-slider"></span>
          </label>
        </div>
      </div>
    </header>
  );
}
