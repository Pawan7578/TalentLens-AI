import { useState } from 'react';
import { api } from '../api';

export default function StatusToggle({ submission, onUpdate }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const isLocked = submission.email_sent || submission.status !== 'pending';

  const handleAction = async (status) => {
    if (isLocked || loading) return;
    setError('');
    setLoading(true);
    try {
      await api.updateStatus(submission.id, status);
      onUpdate(submission.id, status);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (isLocked) {
    return (
      <span className={submission.status === 'selected' ? 'badge-selected' : 'badge-rejected'}>
        {submission.status === 'selected' ? '✓ Selected' : '✗ Rejected'}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => handleAction('selected')}
        disabled={loading}
        title="Shortlist candidate"
        className="w-8 h-8 rounded-lg flex items-center justify-center transition-all"
        style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.25)', color: '#22c55e' }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(34,197,94,0.2)'; }}
        onMouseLeave={e => { e.currentTarget.style.background = 'rgba(34,197,94,0.1)'; }}
      >
        {loading ? <span className="w-3 h-3 border border-green-500/30 border-t-green-500 rounded-full animate-spin" /> : '✓'}
      </button>
      <button
        onClick={() => handleAction('rejected')}
        disabled={loading}
        title="Reject candidate"
        className="w-8 h-8 rounded-lg flex items-center justify-center transition-all"
        style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', color: '#ef4444' }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.2)'; }}
        onMouseLeave={e => { e.currentTarget.style.background = 'rgba(239,68,68,0.1)'; }}
      >
        {loading ? <span className="w-3 h-3 border border-red-500/30 border-t-red-500 rounded-full animate-spin" /> : '✗'}
      </button>
      {error && <span className="text-xs" style={{ color: '#ef4444' }}>{error}</span>}
    </div>
  );
}