// sentinelx-ai/dashboard/src/components/views/ThreatIntelligenceView.jsx
import React, { useState } from 'react';
import { Radio, Search, ShieldAlert, Globe, Database, ExternalLink, Activity } from 'lucide-react';
import { DEMO_THREAT_INTEL } from '../../services/mockData.js';

export default function ThreatIntelligenceView() {
  const [intelList] = useState(DEMO_THREAT_INTEL);
  const [search, setSearch] = useState('');
  const [lookupTarget, setLookupTarget] = useState('');
  const [lookupResult, setLookupResult] = useState(null);

  const filtered = intelList.filter(item =>
    item.indicator.toLowerCase().includes(search.toLowerCase()) ||
    item.threatType.toLowerCase().includes(search.toLowerCase()) ||
    item.type.toLowerCase().includes(search.toLowerCase())
  );

  const handleLookup = (e) => {
    e.preventDefault();
    if (!lookupTarget.trim()) return;

    const query = lookupTarget.trim().toLowerCase();
    const match = intelList.find(i => i.indicator.toLowerCase().includes(query));
    if (match) {
      setLookupResult(match);
    } else {
      setLookupResult({
        indicator: lookupTarget.trim(),
        type: 'Domain / URI',
        threatType: 'No Known IOC Records in Local Threat Feed',
        confidence: 0,
        severity: 'UNKNOWN',
        source: 'Global EDITH AI Intel Database',
        firstSeen: new Date().toISOString()
      });
    }
  };

  return (
    <div className="view-container">
      <div className="view-toolbar">
        <div>
          <div className="view-title-row">
            <Radio className="title-icon pulse" size={22} />
            <h2 className="view-heading">Threat Intelligence Center</h2>
            <span className="demo-tag">CURATED FEEDS</span>
          </div>
          <p className="view-subheading">
            Live indicators of compromise (IOCs), high-abuse registrars, and CVE threat signatures
          </p>
        </div>

        <div className="toolbar-controls">
          <div className="search-box">
            <Search size={14} className="search-icon" />
            <input
              type="text"
              placeholder="Search IOCs, CVEs, or hashes..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="search-input"
            />
          </div>
        </div>
      </div>

      {/* Interactive Quick Indicator Reputation Lookup */}
      <div className="cyber-card">
        <form onSubmit={handleLookup} className="lookup-form">
          <span className="input-form-label">INSTANT REPUTATION LOOKUP:</span>
          <div className="ai-input-wrap">
            <input
              type="text"
              className="ai-url-input"
              placeholder="Enter IP, domain, or CVE (e.g. update-session-verification.top or CVE-2026-2189)..."
              value={lookupTarget}
              onChange={(e) => setLookupTarget(e.target.value)}
            />
            <button type="submit" className="btn-cyber-primary">
              <Database size={14} />
              <span>Query Intelligence</span>
            </button>
          </div>
        </form>

        {lookupResult && (
          <div className="lookup-result-box">
            <div className="lookup-res-top">
              <span className="lookup-indicator">{lookupResult.indicator}</span>
              <span className={`badge-risk ${lookupResult.severity}`}>
                {lookupResult.severity}
              </span>
            </div>
            <div className="lookup-desc">
              <strong>Threat Classification:</strong> {lookupResult.threatType}
            </div>
            <div className="lookup-meta">
              <span><strong>Source:</strong> {lookupResult.source}</span>
              <span><strong>Confidence:</strong> {lookupResult.confidence}%</span>
            </div>
          </div>
        )}
      </div>

      {/* Global IOC Table */}
      <div className="cyber-card">
        <div className="cyber-card-header">
          <div className="card-title">
            <Globe size={16} />
            <span>Active Indicators of Compromise (IOC Feed)</span>
          </div>
        </div>

        <div className="cyber-table-container">
          <table className="cyber-table">
            <thead>
              <tr>
                <th>INDICATOR ID</th>
                <th>IOC ARTIFACT</th>
                <th>TYPE</th>
                <th>THREAT PROFILE</th>
                <th>SEVERITY</th>
                <th>CONFIDENCE</th>
                <th>TELEMETRY SOURCE</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id}>
                  <td>
                    <span className="mono-tag">{item.id}</span>
                  </td>
                  <td>
                    <span className="ioc-artifact-text">{item.indicator}</span>
                  </td>
                  <td>
                    <span className="category-chip">{item.type}</span>
                  </td>
                  <td>{item.threatType}</td>
                  <td>
                    <span className={`badge-risk ${item.severity}`}>
                      {item.severity}
                    </span>
                  </td>
                  <td>
                    <span className="confidence-pill">{item.confidence}%</span>
                  </td>
                  <td>
                    <span className="source-lbl">{item.source}</span>
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
