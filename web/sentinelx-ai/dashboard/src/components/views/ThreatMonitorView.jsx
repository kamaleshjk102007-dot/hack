// sentinelx-ai/dashboard/src/components/views/ThreatMonitorView.jsx
import React, { useState } from 'react';
import {
  ShieldAlert,
  Search,
  Filter,
  CheckCircle2,
  ExternalLink,
  Ban,
  Activity,
  Layers
} from 'lucide-react';

export default function ThreatMonitorView({ incidents = [], onSelectIncident, onBlockDomain }) {
  const [filterLevel, setFilterLevel] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  const filteredIncidents = incidents.filter(inc => {
    const matchesFilter = filterLevel === 'ALL' || inc.riskLevel === filterLevel;
    const matchesSearch =
      searchTerm === '' ||
      inc.url.toLowerCase().includes(searchTerm.toLowerCase()) ||
      inc.domain.toLowerCase().includes(searchTerm.toLowerCase()) ||
      inc.classification.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  return (
    <div className="view-container">
      {/* Header and Filter Toolbar */}
      <div className="view-toolbar">
        <div>
          <h2 className="view-heading">Realtime Threat Monitor</h2>
          <p className="view-subheading">Continuously evaluates active tab network connections and domain heuristics</p>
        </div>

        <div className="toolbar-controls">
          {/* Search */}
          <div className="search-box">
            <Search size={14} className="search-icon" />
            <input
              type="text"
              placeholder="Filter by domain or keyword..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="search-input"
            />
          </div>

          {/* Filter Pills */}
          <div className="filter-pills">
            {['ALL', 'HIGH_RISK', 'SUSPICIOUS', 'UNKNOWN', 'LOW_RISK'].map(level => (
              <button
                key={level}
                className={`filter-pill ${filterLevel === level ? 'active' : ''}`}
                onClick={() => setFilterLevel(level)}
              >
                {level.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Threats Grid / List */}
      <div className="threats-list-grid">
        {filteredIncidents.length > 0 ? (
          filteredIncidents.map(inc => (
            <div key={inc.id} className="threat-item-card">
              <div className="threat-item-header">
                <div className="threat-domain-group">
                  <span className="threat-domain-title">{inc.domain}</span>
                  <span className="mono-id">{inc.id}</span>
                </div>
                <span className={`badge-risk ${inc.riskLevel}`}>
                  {inc.riskLevel.replace('_', ' ')}
                </span>
              </div>

              <div className="threat-url-text" title={inc.url}>
                {inc.url}
              </div>

              {/* Threat Score Bar */}
              <div className="threat-meter-row">
                <div className="threat-meter-bar">
                  <div
                    className={`threat-meter-fill ${inc.riskLevel}`}
                    style={{ width: `${Math.max(5, inc.riskScore)}%` }}
                  ></div>
                </div>
                <span className="threat-meter-score">{inc.riskScore} / 100</span>
              </div>

              {/* Evidence Tags Preview */}
              <div className="evidence-tags-row">
                {inc.evidence && inc.evidence.slice(0, 2).map((ev, i) => (
                  <span key={i} className="evidence-chip">
                    {ev.category || 'INDICATOR'}
                  </span>
                ))}
              </div>

              {/* Action Buttons */}
              <div className="threat-card-actions">
                <button
                  className="btn-cyber-ghost btn-sm"
                  onClick={() => onSelectIncident(inc)}
                >
                  <Activity size={13} />
                  <span>Inspect Details</span>
                </button>
                {inc.domain && inc.domain !== 'Browser Internal' && (
                  <button
                    className="btn-cyber-danger btn-sm"
                    onClick={() => onBlockDomain(inc.domain)}
                    title="Add declarativeNetRequest block rule"
                  >
                    <Ban size={13} />
                    <span>Block Domain</span>
                  </button>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state-box">
            <ShieldAlert size={36} className="empty-icon" />
            <h3 className="empty-title">No Threats Match Criteria</h3>
            <p className="empty-desc">No events found matching your current filter and search parameters.</p>
            <button className="btn-cyber-ghost" onClick={() => { setFilterLevel('ALL'); setSearchTerm(''); }}>
              Reset Filters
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
