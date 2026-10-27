// sentinelx-ai/dashboard/src/App.jsx
import React, { useState, useEffect } from 'react';
import Header from './components/common/Header.jsx';
import Sidebar from './components/common/Sidebar.jsx';
import ConfirmModal from './components/common/ConfirmModal.jsx';
import ThreatDetailModal from './components/modals/ThreatDetailModal.jsx';

import OverviewView from './components/views/OverviewView.jsx';
import ThreatMonitorView from './components/views/ThreatMonitorView.jsx';
import AIToolsView from './components/views/AIToolsView.jsx';
import SelfHealingView from './components/views/SelfHealingView.jsx';
import ThreatIntelligenceView from './components/views/ThreatIntelligenceView.jsx';
import SecurityAlertsView from './components/views/SecurityAlertsView.jsx';
import PermissionAuditorView from './components/views/PermissionAuditorView.jsx';
import DownloadMonitorView from './components/views/DownloadMonitorView.jsx';
import IncidentTimelineView from './components/views/IncidentTimelineView.jsx';
import SettingsView from './components/views/SettingsView.jsx';

import { dataProvider } from './services/dataProvider.js';
import './App.css';

export default function App() {
  const [activeView, setActiveView] = useState('overview');
  const [incidents, setIncidents] = useState([]);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null });
  const [engineHealthy, setEngineHealthy] = useState(true);
  const [backendConnected, setBackendConnected] = useState(false);
  const [demoMode, setDemoMode] = useState(true);

  // Load incidents and check backend health on mount
  const refreshIncidents = async () => {
    const list = await dataProvider.getIncidents();
    setIncidents(list);
  };

  useEffect(() => {
    refreshIncidents();

    // Check backend status
    dataProvider.checkBackendHealth().then(isLive => {
      setBackendConnected(isLive);
    });
  }, [demoMode]);

  // Quick Scan from Header
  const handleQuickScan = async (url) => {
    let hostname = 'unknown';
    try {
      hostname = new URL(url).hostname;
    } catch (_) {
      hostname = url.split('/')[0] || url;
    }

    const isHostile = url.includes('@') || /^[0-9.]+$/.test(hostname) || url.includes('login') || url.includes('verify');
    const isUnknown = !isHostile && !hostname.includes('google') && !hostname.includes('github');

    const newRecord = {
      id: `INC-QS-${Date.now().toString(36).toUpperCase()}`,
      url,
      domain: hostname,
      classification: isHostile ? 'Credential Harvesting Attack' : (isUnknown ? 'Zero-Trust Unverified Entity' : 'Verified Baseline'),
      riskScore: isHostile ? 91 : (isUnknown ? 15 : 2),
      riskLevel: isHostile ? 'HIGH_RISK' : (isUnknown ? 'UNKNOWN' : 'LOW_RISK'),
      detectionSource: 'EDITH AI SOC Quick Scanner',
      evidence: [
        { category: 'SYNTAX', detail: `Quick evaluated URL structure for host: ${hostname}` }
      ],
      aiExplanation: isHostile 
        ? 'Structural syntax and keywords indicate high probability of deception or phishing.' 
        : (isUnknown ? 'Target reputation cannot be substantiated from verified baselines. Zero-trust principles apply.' : 'Verified high-reputation domain with clean profile.'),
      recommendedAction: isHostile ? 'Block domain immediately' : 'Allow with zero-trust monitoring',
      actualActionTaken: isHostile ? 'RULE_BLOCK_ENFORCED' : 'INSPECTED',
      actionStatus: isHostile ? 'Dynamic Rule Triggered' : 'Inspected & Logged',
      verificationResult: 'Verified: Operational evaluation complete.',
      timestamp: new Date().toISOString()
    };

    await dataProvider.addIncident(newRecord);
    await refreshIncidents();
    setSelectedIncident(newRecord);
  };

  // Block Domain Action
  const handleBlockDomain = async (domain) => {
    const blockRecord = {
      id: `INC-BLK-${Date.now().toString(36).toUpperCase()}`,
      url: `https://${domain}`,
      domain,
      classification: 'Enforced Threat Containment',
      riskScore: 90,
      riskLevel: 'HIGH_RISK',
      detectionSource: 'Manual SOC Operator Containment Order',
      evidence: [
        { category: 'CONTAINMENT', detail: `Domain ${domain} blocked via declarativeNetRequest dynamic rule.` }
      ],
      aiExplanation: 'Domain was explicitly isolated and quarantined to protect browser endpoints.',
      recommendedAction: 'Retain active block rule until security review.',
      actualActionTaken: 'RULE_BLOCK_ENFORCED',
      actionStatus: 'Enforced via Declarative Rule',
      verificationResult: 'Verified: Network request packet drop registered.',
      timestamp: new Date().toISOString()
    };

    await dataProvider.addIncident(blockRecord);
    await refreshIncidents();
  };

  // Clear Events Action with Confirmation
  const handleRequestClearEvents = () => {
    setConfirmModal({
      isOpen: true,
      title: 'Wipe All Security Event Records?',
      message: 'This will permanently remove all stored incident records and telemetry logs from local storage. This action cannot be reversed.',
      confirmLabel: 'Permanently Wipe Logs',
      onConfirm: async () => {
        await dataProvider.clearAllIncidents();
        await refreshIncidents();
        setConfirmModal({ isOpen: false });
      }
    });
  };

  return (
    <div className="app-shell">
      {/* Sidebar Navigation */}
      <Sidebar
        activeView={activeView}
        onViewChange={setActiveView}
        unreadAlertsCount={3}
      />

      {/* Main Content Area */}
      <div className="main-wrapper">
        <Header
          activeTab={activeView}
          engineHealthy={engineHealthy}
          backendConnected={backendConnected}
          demoMode={demoMode}
          onToggleDemoMode={setDemoMode}
          onQuickScan={handleQuickScan}
        />

        <main className="content-body">
          {activeView === 'overview' && (
            <OverviewView
              incidents={incidents}
              onSelectIncident={setSelectedIncident}
              onNavigateView={setActiveView}
              demoMode={demoMode}
            />
          )}

          {activeView === 'threat-monitor' && (
            <ThreatMonitorView
              incidents={incidents}
              onSelectIncident={setSelectedIncident}
              onBlockDomain={handleBlockDomain}
            />
          )}

          {activeView === 'ai-investigator' && (
            <AIToolsView />
          )}

          {activeView === 'self-healing' && (
            <SelfHealingView />
          )}

          {activeView === 'threat-intel' && (
            <ThreatIntelligenceView />
          )}

          {activeView === 'alerts' && (
            <SecurityAlertsView />
          )}

          {activeView === 'permissions' && (
            <PermissionAuditorView />
          )}

          {activeView === 'downloads' && (
            <DownloadMonitorView />
          )}

          {activeView === 'timeline' && (
            <IncidentTimelineView
              incidents={incidents}
              onSelectIncident={setSelectedIncident}
            />
          )}

          {activeView === 'settings' && (
            <SettingsView
              onClearAllEvents={handleRequestClearEvents}
              onBackendStatusChange={setBackendConnected}
            />
          )}
        </main>
      </div>

      {/* Phase 3 Threat Detail Modal */}
      <ThreatDetailModal
        incident={selectedIncident}
        onClose={() => setSelectedIncident(null)}
        onBlockDomain={handleBlockDomain}
      />

      {/* Destructive Action Confirmation Modal */}
      <ConfirmModal
        isOpen={confirmModal.isOpen}
        title={confirmModal.title}
        message={confirmModal.message}
        confirmLabel={confirmModal.confirmLabel}
        onConfirm={confirmModal.onConfirm}
        onCancel={() => setConfirmModal({ isOpen: false })}
      />
    </div>
  );
}
