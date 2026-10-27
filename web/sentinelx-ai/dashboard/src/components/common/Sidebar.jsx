// sentinelx-ai/dashboard/src/components/common/Sidebar.jsx
import React from 'react';
import {
  LayoutDashboard,
  ShieldAlert,
  BrainCircuit,
  Wrench,
  Radio,
  Bell,
  Lock,
  DownloadCloud,
  History,
  Settings
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, badge: 'Live' },
  { id: 'threat-monitor', label: 'Threat Monitor', icon: ShieldAlert, badge: null },
  { id: 'ai-investigator', label: 'AI Investigator', icon: BrainCircuit, badge: 'Gemma' },
  { id: 'self-healing', label: 'Self-Healing Center', icon: Wrench, badge: 'Auto' },
  { id: 'threat-intel', label: 'Threat Intelligence', icon: Radio, badge: null },
  { id: 'alerts', label: 'Security Alerts', icon: Bell, badge: '4' },
  { id: 'permissions', label: 'Permission Auditor', icon: Lock, badge: null },
  { id: 'downloads', label: 'Download Monitor', icon: DownloadCloud, badge: null },
  { id: 'timeline', label: 'Incident Timeline', icon: History, badge: null },
  { id: 'settings', label: 'Security Settings', icon: Settings, badge: null },
];

export default function Sidebar({ activeView, onViewChange, unreadAlertsCount = 4 }) {
  return (
    <aside className="dashboard-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-category">SOC NAVIGATION</div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = activeView === item.id;
          const badgeValue = item.id === 'alerts' && unreadAlertsCount > 0 ? unreadAlertsCount : item.badge;

          return (
            <button
              key={item.id}
              className={`sidebar-nav-btn ${isActive ? 'active' : ''}`}
              onClick={() => onViewChange(item.id)}
            >
              <div className="nav-btn-content">
                <Icon className="nav-icon" size={17} />
                <span className="nav-label">{item.label}</span>
              </div>
              {badgeValue && (
                <span className={`nav-pill ${item.id === 'alerts' ? 'pill-alert' : ''}`}>
                  {badgeValue}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Sidebar Footer System Health */}
      <div className="sidebar-system-box">
        <div className="sys-status-row">
          <span className="sys-label">ENGINE SPEC</span>
          <span className="sys-val">Manifest V3</span>
        </div>
        <div className="sys-status-row">
          <span className="sys-label">ZERO TRUST</span>
          <span className="sys-val sys-green">ENFORCED</span>
        </div>
        <div className="sys-status-row">
          <span className="sys-label">AI ASSIST</span>
          <span className="sys-val sys-cyan">READY</span>
        </div>
      </div>
    </aside>
  );
}
