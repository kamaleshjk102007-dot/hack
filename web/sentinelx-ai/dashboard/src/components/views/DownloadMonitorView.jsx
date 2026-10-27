// sentinelx-ai/dashboard/src/components/views/DownloadMonitorView.jsx
import React from 'react';
import { DownloadCloud, ShieldAlert, FileText, CheckCircle2 } from 'lucide-react';
import { DEMO_DOWNLOADS } from '../../services/mockData.js';

export default function DownloadMonitorView() {
  return (
    <div className="view-container">
      <div className="view-toolbar">
        <div>
          <div className="view-title-row">
            <DownloadCloud className="title-icon" size={22} />
            <h2 className="view-heading">Download Risk Monitor</h2>
            <span className="demo-tag">MIME & ENTROPY SCANNER</span>
          </div>
          <p className="view-subheading">
            Pre-execution inspection of browser download payloads for extension spoofing and high-entropy packers
          </p>
        </div>
      </div>

      <div className="cyber-card">
        <div className="cyber-card-header">
          <div className="card-title">Inspected Download Streams</div>
        </div>

        <div className="cyber-table-container">
          <table className="cyber-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>FILENAME</th>
                <th>SOURCE HOST</th>
                <th>DETECTED MIME</th>
                <th>CLAIMED MIME</th>
                <th>ENTROPY</th>
                <th>RISK LEVEL</th>
                <th>CONTAINMENT ACTION</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_DOWNLOADS.map((dl) => (
                <tr key={dl.id}>
                  <td>
                    <span className="mono-tag">{dl.id}</span>
                  </td>
                  <td>
                    <div className="filename-cell">
                      <FileText size={14} className="file-icon" />
                      <strong>{dl.filename}</strong>
                    </div>
                  </td>
                  <td>
                    <span className="table-domain">{new URL(dl.sourceUrl).hostname}</span>
                  </td>
                  <td>
                    <span className={`mime-chip ${dl.detectedMime.includes('dosexec') ? 'danger' : ''}`}>
                      {dl.detectedMime}
                    </span>
                  </td>
                  <td>
                    <span className="mime-chip-claimed">{dl.claimedMime}</span>
                  </td>
                  <td>
                    <span className="entropy-val">{dl.entropy}</span>
                  </td>
                  <td>
                    <span className={`badge-risk ${dl.riskLevel}`}>{dl.riskLevel.replace('_', ' ')}</span>
                  </td>
                  <td>
                    <span className={`action-pill ${dl.action}`}>
                      {dl.action}
                    </span>
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
