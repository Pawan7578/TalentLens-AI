import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';

function ScoreBadge({ score }) {
  const s = Math.round(score);
  if (s >= 70) return <span className="font-mono text-sm font-bold score-green">{s}</span>;
  if (s >= 40) return <span className="font-mono text-sm font-bold score-amber">{s}</span>;
  return <span className="font-mono text-sm font-bold score-red">{s}</span>;
}

export default function HistoryTable({ submissions }) {
  const { user } = useAuth();
  const [expanded, setExpanded] = useState(null);
  const isAdmin = user?.role === 'admin';

  if (!submissions?.length) return (
    <div className="card text-center py-12">
      <div className="w-12 h-12 rounded-xl mx-auto mb-4 flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)' }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>
      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No submissions yet. Analyze your first resume above.</p>
    </div>
  );

  return (
    <div className="card overflow-hidden p-0">
      <div className="px-6 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-sm">Submission History</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
              {isAdmin ? (
                ['Date', 'ATS Score', 'Skill Match', 'Education', 'Experience', 'Status', 'Feedback', ''].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-xs font-medium" style={{ color: 'var(--text-muted)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>{h}</th>
                ))
              ) : (
                ['Date', 'ATS Score', 'Status', 'Feedback', ''].map(h => (
                  <th key={h} className="text-left px-5 py-3 text-xs font-medium" style={{ color: 'var(--text-muted)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>{h}</th>
                ))
              )}
            </tr>
          </thead>
          <tbody>
            {submissions.map(sub => {
              const skills = (() => { try { return JSON.parse(sub.missing_skills); } catch { return []; } })();
              return (
                <>
                  <tr key={sub.id}>
                    <td className="px-5 py-3 font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                      {new Date(sub.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3"><ScoreBadge score={sub.ats_score} /></td>
                    
                    {isAdmin && (
                      <>
                        <td className="px-5 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                          {sub.skill_match ? Math.round(sub.skill_match) + '%' : '—'}
                        </td>
                        <td className="px-5 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                          {sub.education_match ? Math.round(sub.education_match) + '%' : '—'}
                        </td>
                        <td className="px-5 py-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                          {sub.experience_match ? Math.round(sub.experience_match) + '%' : '—'}
                        </td>
                      </>
                    )}
                    
                    <td className="px-5 py-3">
                      <span className={`badge-${sub.status}`}>{sub.status}</span>
                    </td>
                    
                    <td className="px-5 py-3 max-w-xs">
                      <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>{sub.feedback}</p>
                    </td>
                    <td className="px-5 py-3">
                      {isAdmin && (
                        <button
                          onClick={() => setExpanded(expanded === sub.id ? null : sub.id)}
                          className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                          style={{ color: 'var(--accent)', background: 'var(--accent-dim)', border: '1px solid var(--accent-border)' }}
                        >
                          {expanded === sub.id ? 'Hide' : 'Details'}
                        </button>
                      )}
                    </td>
                  </tr>
                  
                  {isAdmin && expanded === sub.id && (
                    <tr key={`${sub.id}-detail`} className="animate-fade-in">
                      <td colSpan={8} className="px-5 pb-4">
                        <div className="rounded-xl p-4 space-y-3" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }}>
                          <div>
                            <p className="label mb-2">Missing Skills</p>
                            {skills.length > 0 ? (
                              <div className="flex flex-wrap gap-2">
                                {skills.map((s, i) => (
                                  <span key={i} className="px-2.5 py-1 rounded-lg text-xs" style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.2)' }}>{s}</span>
                                ))}
                              </div>
                            ) : <p className="text-xs" style={{ color: 'var(--text-muted)' }}>None</p>}
                          </div>
                          {sub.education_gap && sub.education_gap !== 'None' && (
                            <div>
                              <p className="label mb-1">Education Gap</p>
                              <p className="text-xs" style={{ color: 'var(--text-subtle)' }}>{sub.education_gap}</p>
                            </div>
                          )}
                          {sub.experience_gap && sub.experience_gap !== 'None' && (
                            <div>
                              <p className="label mb-1">Experience Gap</p>
                              <p className="text-xs" style={{ color: 'var(--text-subtle)' }}>{sub.experience_gap}</p>
                            </div>
                          )}
                          <div>
                            <p className="label mb-1">Full Feedback</p>
                            <p className="text-xs leading-relaxed" style={{ color: 'var(--text-subtle)' }}>{sub.feedback}</p>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}