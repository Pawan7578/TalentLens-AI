const BulkEmailModal = ({ isOpen, onClose, onConfirm, candidates, emailType, loading }) => {
  if (!isOpen) return null;

  const emailTypeLabel = emailType === 'selected' ? 'Selection' : 'Rejection';
  const emailTypeColor = emailType === 'selected' ? '#22c55e' : '#ef4444';
  const emailTypeBg = emailType === 'selected' ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)';
  const emailTypeBorder = emailType === 'selected' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)';

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
    >
      <div className="card max-w-md w-full animate-slide-up">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-semibold">Send {emailTypeLabel} Emails</h3>
          <button
            onClick={onClose}
            disabled={loading}
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-white/10 disabled:opacity-50"
            style={{ color: 'var(--text-muted)' }}
          >
            ✕
          </button>
        </div>

        <div className="space-y-4">
          {/* Summary */}
          <div
            className="p-3 rounded-lg border"
            style={{
              background: emailTypeBg,
              borderColor: emailTypeBorder,
            }}
          >
            <p className="text-sm font-medium mb-2" style={{ color: emailTypeColor }}>
              {emailTypeLabel} Email
            </p>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              You are about to send <strong>{emailTypeLabel.toLowerCase()}</strong> emails to {candidates.length} candidate{candidates.length !== 1 ? 's' : ''}.
            </p>
          </div>

          {/* Recipient List */}
          <div>
            <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Recipients ({candidates.length})
            </p>
            <div
              className="max-h-48 overflow-y-auto rounded-lg p-3 space-y-1.5"
              style={{
                background: 'rgba(255,255,255,0.02)',
                border: '1px solid var(--border)',
              }}
            >
              {candidates.map((candidate) => (
                <div key={candidate.id} className="text-xs">
                  <p className="font-medium">{candidate.user_name}</p>
                  <p style={{ color: 'var(--text-muted)' }}>{candidate.user_email}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Warning */}
          <div
            className="p-3 rounded-lg border text-xs"
            style={{
              background: 'rgba(245,158,11,0.1)',
              borderColor: 'rgba(245,158,11,0.2)',
              color: '#f59e0b',
            }}
          >
            This action will send emails immediately and cannot be undone. Each email will have a 3-second delay to avoid rate limiting.
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={onClose}
              disabled={loading}
              className="flex-1 btn-ghost disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={loading}
              className="flex-1 btn-primary justify-center disabled:opacity-50"
              style={{
                background: emailTypeColor,
              }}
            >
              {loading ? 'Sending...' : `Send ${emailTypeLabel}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default BulkEmailModal;
