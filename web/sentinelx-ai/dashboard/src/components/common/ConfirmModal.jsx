// sentinelx-ai/dashboard/src/components/common/ConfirmModal.jsx
import React from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function ConfirmModal({ isOpen, title, message, confirmLabel = 'Confirm Action', onConfirm, onCancel }) {
  if (!isOpen) return null;

  return (
    <div className="threat-modal-backdrop" onClick={onCancel}>
      <div className="confirm-dialog-card" onClick={(e) => e.stopPropagation()}>
        <div className="confirm-dialog-header">
          <div className="confirm-title-group">
            <div className="confirm-icon-box">
              <AlertTriangle size={18} />
            </div>
            <h3 className="confirm-dialog-title">{title || 'Confirm Destructive Action'}</h3>
          </div>
          <button className="btn-modal-close" onClick={onCancel}>
            <X size={16} />
          </button>
        </div>

        <p className="confirm-dialog-desc">
          {message || 'This action cannot be undone. Are you sure you wish to proceed?'}
        </p>

        <div className="confirm-dialog-actions">
          <button className="btn-cyber-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button className="btn-cyber-danger" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
