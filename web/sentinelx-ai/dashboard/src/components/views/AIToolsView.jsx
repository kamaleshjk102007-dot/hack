// sentinelx-ai/dashboard/src/components/views/AIToolsView.jsx
import React, { useState } from 'react';
import {
  BrainCircuit,
  Sparkles,
  Terminal,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Code2,
  Shield,
  Send
} from 'lucide-react';
import { dataProvider } from '../../services/dataProvider.js';

export default function AIToolsView() {
  const [targetUrl, setTargetUrl] = useState('https://paypal.com@verify-auth-session.xyz/account/login');
  const [analyzing, setAnalyzing] = useState(false);
  const [investigation, setInvestigation] = useState(null);
  const [showRawJson, setShowRawJson] = useState(false);

  const handleInvestigate = async (e) => {
    if (e) e.preventDefault();
    if (!targetUrl.trim()) return;

    setAnalyzing(true);
    try {
      const result = await dataProvider.investigateTargetWithAI(targetUrl.trim());
      setInvestigation(result);
    } catch (err) {
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  };

  const setPreset = (url) => {
    setTargetUrl(url);
  };

  return (
    <div className="view-container">
      <div className="view-toolbar">
        <div>
          <div className="gemma-title-row">
            <BrainCircuit className="gemma-pulse-icon" size={22} />
            <h2 className="view-heading">AI Threat Investigator</h2>
            <span className="gemma-badge">GEMMA 2B ARCHITECTURE</span>
          </div>
          <p className="view-subheading">
            Neural semantic inspection and behavioral hypothesis modeling for deceptive web artifacts
          </p>
        </div>
      </div>

      {/* Target Input Section */}
      <div className="cyber-card">
        <form onSubmit={handleInvestigate} className="ai-input-form">
          <label className="input-form-label">TARGET RESOURCE FOR NEURAL FORENSICS:</label>
          <div className="ai-input-wrap">
            <input
              type="text"
              className="ai-url-input"
              value={targetUrl}
              onChange={(e) => setTargetUrl(e.target.value)}
              placeholder="Enter suspicious URL or host (e.g. http://192.168.1.1/admin/login)..."
              spellCheck="false"
            />
            <button
              type="submit"
              className="btn-cyber-primary ai-submit-btn"
              disabled={analyzing}
            >
              {analyzing ? (
                <>
                  <Sparkles className="spin-icon" size={15} />
                  <span>Synthesizing...</span>
                </>
              ) : (
                <>
                  <Send size={15} />
                  <span>Investigate Target</span>
                </>
              )}
            </button>
          </div>
        </form>

        {/* Quick presets */}
        <div className="ai-presets-row">
          <span className="presets-label">Quick Presets:</span>
          <button
            type="button"
            className="preset-tag"
            onClick={() => setPreset('https://paypal.com@verify-auth-session.xyz/login')}
          >
            Authority Spoofing Phishing
          </button>
          <button
            type="button"
            className="preset-tag"
            onClick={() => setPreset('http://185.220.101.5/admin/login')}
          >
            Raw IP Infrastructure
          </button>
          <button
            type="button"
            className="preset-tag"
            onClick={() => setPreset('https://emerging-fintech-beta.io/app')}
          >
            Unverified Neutral (Zero-Trust)
          </button>
          <button
            type="button"
            className="preset-tag"
            onClick={() => setPreset('https://github.com/kubernetes/kubernetes')}
          >
            Verified Baseline
          </button>
        </div>
      </div>

      {/* Analysis Output Section */}
      {investigation && (
        <div className="ai-results-card">
          <div className="ai-results-header">
            <div className="ai-model-tag">
              <BrainCircuit size={14} />
              <span>{investigation.model}</span>
              <span className="demo-tag">{investigation.source}</span>
            </div>
            <button
              className="btn-cyber-ghost btn-xs"
              onClick={() => setShowRawJson(!showRawJson)}
            >
              <Code2 size={12} />
              <span>{showRawJson ? 'Formatted View' : 'Raw JSON Schema'}</span>
            </button>
          </div>

          {!showRawJson ? (
            <div className="ai-results-body">
              {/* Verdict Banner */}
              <div className="verdict-highlight-row">
                <div className="verdict-col">
                  <span className="lbl">FORENSIC VERDICT:</span>
                  <span className={`verdict-val ${investigation.verdict}`}>
                    {investigation.verdict}
                  </span>
                </div>
                <div className="verdict-col">
                  <span className="lbl">CONFIDENCE SCORE:</span>
                  <span className="confidence-num">{investigation.confidence}%</span>
                </div>
                <div className="verdict-col">
                  <span className="lbl">RECOMMENDED PLAYBOOK:</span>
                  <span className="playbook-tag">{investigation.recommendedPlaybook}</span>
                </div>
              </div>

              {/* Threat Hypothesis */}
              <div className="hypothesis-box">
                <h4 className="box-title">Gemma Threat Hypothesis:</h4>
                <p className="hypothesis-text">{investigation.threatHypothesis}</p>
              </div>

              {/* Forensic Evidence Graph Nodes */}
              <div className="evidence-nodes-box">
                <h4 className="box-title">Extracted Lexical & Structural Tokens:</h4>
                <div className="nodes-grid">
                  {investigation.evidenceNodes.map((node, i) => (
                    <div key={i} className="node-item">
                      <span className="node-key">{node.key}</span>
                      <span className="node-val">{node.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <pre className="json-dump">
              {JSON.stringify(investigation, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
