// sentinelx-ai/dashboard/src/components/views/IncidentTimelineView.jsx
import React, { useState } from 'react';
import { History, Download, Clock, ShieldAlert, ArrowRight, Activity } from 'lucide-react';

export default function IncidentTimelineView({ incidents = [], onSelectIncident }) {
  const [search, setSearch] = useState('');

  const filtered = incidents.filter(i =>
    i.url.toLowerCase().includes(search.toLowerCase()) ||
    i.domain.toLowerCase().includes(search.toLowerCase()) ||
    i.classification.toLowerCase().includes(search.toLowerCase())
  );

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(incidents, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', `edith_timeline_${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="view-container">
      <div className="view-toolbar">
        <div>
          <div className="view-title-row">
            <History className="title-icon" size={22} />
            <h2 className="view-heading">Chronological Incident Timeline</h2>
            <span className="mono-count">{filtered.length} FORENSIC RECORDS</span>
          </div>
          <p className="view-subheading">
            Audit-grade sequence of security inspections, threat classifications, and enforcement outcomes
          </p>
        </div>

        <div className="toolbar-controls">
          <input
            type="text"
            className="search-input"
            placeholder="Search timeline..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="btn-cyber-ghost btn-sm" onClick={handleExportJson}>
            <Download size={13} />
            <span>Export Forensic JSON</span>
          </button>
        </div>
      </div>

      <div className="timeline-container">
        <div className="timeline-line"></div>
        {filtered.map((item, idx) => (
          <div key={item.id} className="timeline-entry" onClick={() => onSelectIncident(item)}>
            <div className={`timeline-marker ${item.riskLevel}`}></div>
            <div className="timeline-card">
              <div className="timeline-card-header">
                <div className="t-meta">
                  <span className="t-time">
                    <Clock size={12} />
                    {new Date(item.timestamp).toLocaleString()}
                  </span>
                  <span className="mono-tag">{item.id}</span>
                </div>
                <span className={`badge-risk ${item.riskLevel}`}>
                  {item.riskLevel.replace('_', ' ')}
                </span>
              </div>

              <div className="t-title-row">
                <h4 className="t-title">{item.classification}</h4>
                <span className="t-domain">{item.domain}</span>
              </div>

              <div className="t-url-line">{item.url}</div>

              <div className="t-footer">
                <div className="t-action">
                  <strong>Enforcement:</strong> {item.actualActionTaken} ({item.actionStatus})
                </div>
                <button className="btn-cyber-ghost btn-xs">
                  <span>Full Evidence</span>
                  <ArrowRight size={11} />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
