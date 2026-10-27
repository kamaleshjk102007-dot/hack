// sentinelx-ai/dashboard/src/components/views/PermissionAuditorView.jsx
import React from 'react';
import { Lock, ShieldCheck, AlertOctagon, CheckCircle2 } from 'lucide-react';
import { DEMO_PERMISSIONS } from '../../services/mockData.js';

export default function PermissionAuditorView() {
  return (
    <div className="view-container">
      <div className="view-toolbar">
        <div>
          <div className="view-title-row">
            <Lock className="title-icon" size={22} />
            <h2 className="view-heading">Browser Permission Auditor</h2>
            <span className="state-badge Verified">LEAST-PRIVILEGE AUDIT</span>
          </div>
          <p className="view-subheading">
            Continuous blast-radius inspection ensuring zero unnecessary access to user credentials or host trees
          </p>
        </div>
      </div>

      {/* Philosophy Card */}
      <div className="permission-philosophy-card">
        <ShieldCheck size={28} className="shield-icon-cyan" />
        <div>
          <h4 className="card-title">EDITH AI Zero-Trust Permission Guarantee</h4>
          <p className="card-subtitle">
            EDITH AI strictly limits privileges to declarativeNetRequest, storage, and activeTab/tabs.
            Broad host authorizations (<code className="code-inline">&lt;all_urls&gt;</code>) and DOM credential access are intentionally barred.
          </p>
        </div>
      </div>

      {/* Permissions Table */}
      <div className="cyber-card">
        <div className="cyber-card-header">
          <div className="card-title">Audited Chrome Permissions & Risk Tiers</div>
        </div>

        <div className="cyber-table-container">
          <table className="cyber-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>EXTENSION / SERVICE</th>
                <th>GRANTED PERMISSION</th>
                <th>RISK TIER</th>
                <th>SECURITY JUSTIFICATION</th>
                <th>AUDIT STATUS</th>
              </tr>
            </thead>
            <tbody>
              {DEMO_PERMISSIONS.map((perm) => (
                <tr key={perm.id}>
                  <td>
                    <span className="mono-tag">{perm.id}</span>
                  </td>
                  <td>
                    <strong>{perm.extensionName}</strong>
                  </td>
                  <td>
                    <span className="mono-perm">{perm.permission}</span>
                  </td>
                  <td>
                    <span className={`risk-tier-pill ${perm.riskTier}`}>
                      {perm.riskTier}
                    </span>
                  </td>
                  <td>{perm.justification}</td>
                  <td>
                    {perm.status === 'AUDITED_SECURE' ? (
                      <span className="audit-secure">
                        <CheckCircle2 size={13} />
                        <span>Audited Secure</span>
                      </span>
                    ) : (
                      <span className="audit-warn">
                        <AlertOctagon size={13} />
                        <span>Action Recommended</span>
                      </span>
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
