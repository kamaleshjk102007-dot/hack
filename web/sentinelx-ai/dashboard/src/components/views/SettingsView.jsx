// sentinelx-ai/dashboard/src/components/views/SettingsView.jsx
import React, { useState } from 'react';
import { Settings, Server, BrainCircuit, ShieldAlert, Trash2, Save, CheckCircle2, RotateCcw } from 'lucide-react';
import { DEFAULT_CONFIG } from '../../types/schema.js';
import { dataProvider } from '../../services/dataProvider.js';

export default function SettingsView({ onClearAllEvents, onBackendStatusChange }) {
  const [config, setConfig] = useState({ ...DEFAULT_CONFIG });
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [testingBackend, setTestingBackend] = useState(false);
  const [backendResult, setBackendResult] = useState(null);

  const handleTestBackend = async () => {
    setTestingBackend(true);
    try {
      const isLive = await dataProvider.checkBackendHealth();
      setBackendResult(isLive ? 'CONNECTED' : 'UNREACHABLE');
      if (onBackendStatusChange) onBackendStatusChange(isLive);
    } catch (_) {
      setBackendResult('UNREACHABLE');
    } finally {
      setTestingBackend(false);
    }
  };

  const handleSave = (e) => {
    e.preventDefault();
    setSaving(true);
    dataProvider.config = { ...config };
    setTimeout(() => {
      setSaving(false);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    }, 400);
  };

  return (
    <div className="view-container">
      <div className="view-toolbar">
        <div>
          <div className="view-title-row">
            <Settings className="title-icon" size={22} />
            <h2 className="view-heading">Security Engine & Integration Settings</h2>
          </div>
          <p className="view-subheading">
            Configure FastAPI backend connectivity, Gemma AI inference endpoints, and zero-trust heuristic strictness
          </p>
        </div>
      </div>

      <form onSubmit={handleSave} className="settings-grid">
        {/* FastAPI Backend Settings */}
        <div className="cyber-card">
          <div className="cyber-card-header">
            <div className="card-title">
              <Server size={16} />
              <span>FastAPI Backend Uplink</span>
            </div>
            {backendResult && (
              <span className={`status-pill ${backendResult === 'CONNECTED' ? 'ACTIVE' : 'FAILED'}`}>
                {backendResult}
              </span>
            )}
          </div>

          <div className="form-field-group">
            <label className="field-label">FastAPI Base URL</label>
            <input
              type="text"
              className="field-input"
              value={config.apiBaseUrl}
              onChange={(e) => setConfig({ ...config, apiBaseUrl: e.target.value })}
              placeholder="http://localhost:8000/api/v1"
            />
            <span className="field-hint">
              Target endpoint for remote incident aggregation and threat intelligence synchronization.
            </span>
          </div>

          <div className="field-actions">
            <button
              type="button"
              className="btn-cyber-ghost btn-sm"
              onClick={handleTestBackend}
              disabled={testingBackend}
            >
              {testingBackend ? 'Probing :8000...' : 'Test Connection'}
            </button>
          </div>
        </div>

        {/* Gemma AI Engine Settings */}
        <div className="cyber-card">
          <div className="cyber-card-header">
            <div className="card-title">
              <BrainCircuit size={16} />
              <span>Gemma AI Inference Gateway</span>
            </div>
          </div>

          <div className="form-field-group">
            <label className="field-label">Gemma Investigation Endpoint</label>
            <input
              type="text"
              className="field-input"
              value={config.gemmaEndpoint}
              onChange={(e) => setConfig({ ...config, gemmaEndpoint: e.target.value })}
              placeholder="http://localhost:8000/api/v1/ai/gemma-investigate"
            />
            <span className="field-hint">
              Routes suspicious payloads to a quantized Gemma 2B model for deep semantic threat synthesis.
            </span>
          </div>
        </div>

        {/* Zero-Trust Strictness Thresholds */}
        <div className="cyber-card">
          <div className="cyber-card-header">
            <div className="card-title">
              <ShieldAlert size={16} />
              <span>Zero-Trust Strictness & Containment Policy</span>
            </div>
          </div>

          <div className="form-field-group">
            <label className="field-label">Automatic Block Score Threshold: {config.autoBlockScoreThreshold} / 100</label>
            <input
              type="range"
              min="50"
              max="100"
              value={config.autoBlockScoreThreshold}
              onChange={(e) => setConfig({ ...config, autoBlockScoreThreshold: parseInt(e.target.value, 10) })}
              className="range-slider"
            />
            <span className="field-hint">
              Targets scoring at or above this threshold will have dynamic declarative blocking enforced automatically.
            </span>
          </div>

          <div className="form-field-group">
            <label className="field-label">Unverified Target Policy</label>
            <select
              className="field-input"
              value={config.zeroTrustStrictness}
              onChange={(e) => setConfig({ ...config, zeroTrustStrictness: e.target.value })}
            >
              <option value="High (Neutral sites default UNKNOWN)">High: Neutral sites strictly marked UNKNOWN (Recommended)</option>
              <option value="Strict (Alert on all unverified)">Strict: Prompt user on every unverified domain</option>
              <option value="Permissive (Flag only overt attacks)">Permissive: Only flag overt attacks</option>
            </select>
          </div>
        </div>

        {/* Save & Danger Zone */}
        <div className="settings-bottom-actions">
          <button type="submit" className="btn-cyber-primary" disabled={saving}>
            <Save size={14} />
            <span>{saving ? 'Saving...' : 'Save Configuration'}</span>
          </button>
          {saveSuccess && (
            <span className="save-toast">
              <CheckCircle2 size={14} />
              <span>Configuration Persisted</span>
            </span>
          )}

          <div className="danger-zone-wrap">
            <button
              type="button"
              className="btn-cyber-danger btn-sm"
              onClick={onClearAllEvents}
            >
              <Trash2 size={14} />
              <span>Wipe Local Incident Logs</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
