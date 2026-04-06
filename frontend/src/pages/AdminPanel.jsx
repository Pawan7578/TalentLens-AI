import { useState, useEffect } from 'react';
import { api } from '../api';
import Navbar from '../components/Navbar';
import StatusToggle from '../components/StatusToggle';

function ScoreCell({ score }) {
  const s = Math.round(score);
  const color = s >= 70 ? '#22c55e' : s >= 40 ? '#f59e0b' : '#ef4444';
  const bg = s >= 70 ? 'rgba(34,197,94,0.1)' : s >= 40 ? 'rgba(245,158,11,0.1)' : 'rgba(239,68,68,0.1)';
  const border = s >= 70 ? 'rgba(34,197,94,0.25)' : s >= 40 ? 'rgba(245,158,11,0.25)' : 'rgba(239,68,68,0.25)';
  return (
    <span className="font-mono text-sm font-bold px-3 py-1 rounded-lg" style={{ color, background: bg, border: `1px solid ${border}` }}>
      {s}
    </span>
  );
}

function Modal({ title, content, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}>
      <div className="card max-w-2xl w-full max-h-[80vh] overflow-y-auto animate-slide-up">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold">{title}</h3>
          <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-white/10" style={{ color: 'var(--text-muted)' }}>✕</button>
        </div>
        <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-subtle)' }}>{content}</p>
      </div>
    </div>
  );
}

export default function AdminPanel() {
  const [tab, setTab] = useState('submissions'); // 'submissions' | 'templates'
  const [submissions, setSubmissions] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modal, setModal] = useState(null);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [showCreateTemplate, setShowCreateTemplate] = useState(false);
  const [templateForm, setTemplateForm] = useState({ 
    job_role: '', 
    descMode: 'text', // 'text' | 'file'
    description: '', 
    descFile: null,
    resume: null 
  });
  const [templateLoading, setTemplateLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.adminSubmissions();
      setSubmissions(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadTemplates = async () => {
    try {
      const data = await api.listJobTemplatesAdmin();
      setTemplates(data || []);
    } catch (err) {
      console.error('Load templates error:', err);
      // Silently fail - templates not mandatory
    }
  };

  const handleCreateTemplate = async (e) => {
    e.preventDefault();
    if (!templateForm.job_role.trim()) {
      setError('Please enter a job role');
      return;
    }

    let description = templateForm.description;
    
    // If using file mode, extract text from file
    if (templateForm.descMode === 'file') {
      if (!templateForm.descFile) {
        setError('Please upload a job description file');
        return;
      }
      try {
        description = await templateForm.descFile.text();
      } catch (err) {
        setError('Failed to read description file');
        return;
      }
    }

    if (!description || !description.trim()) {
      setError('Please provide a job description');
      return;
    }

    setTemplateLoading(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('job_role', templateForm.job_role.trim());
      fd.append('description', description.trim());
      if (templateForm.resume) {
        fd.append('reference_resume', templateForm.resume);
      }
      
      console.log('Creating template with:', {
        role: templateForm.job_role,
        descLength: description.length,
        hasResume: !!templateForm.resume,
      });

      await api.createJobTemplate(fd);
      setShowCreateTemplate(false);
      setTemplateForm({ job_role: '', descMode: 'text', description: '', descFile: null, resume: null });
      await loadTemplates();
    } catch (err) {
      console.error('Template creation error:', err);
      // Extract error message from various possible error formats
      const errorMsg = 
        err?.message || 
        err?.detail || 
        (typeof err === 'string' ? err : 'Failed to create template');
      setError(errorMsg);
    } finally {
      setTemplateLoading(false);
    }
  };

  const handleDeleteTemplate = async (id) => {
    if (!confirm('Delete this job template? This cannot be undone.')) return;
    try {
      await api.deleteJobTemplate(id);
      await loadTemplates();
    } catch (err) {
      console.error('Delete template error:', err);
      const errorMsg = err?.message || 'Failed to delete template';
      setError(errorMsg);
    }
  };

  useEffect(() => { 
    load();
    loadTemplates();
  }, []);

  const handleUpdate = (id, status) => {
    setSubmissions(prev => prev.map(s => s.id === id ? { ...s, status, email_sent: true } : s));
  };

  const filtered = submissions.filter(s => {
    const matchFilter = filter === 'all' || s.status === filter;
    const matchSearch = !search || s.user_name.toLowerCase().includes(search.toLowerCase()) || s.user_email.toLowerCase().includes(search.toLowerCase());
    return matchFilter && matchSearch;
  });

  const stats = {
    total: submissions.length,
    selected: submissions.filter(s => s.status === 'selected').length,
    rejected: submissions.filter(s => s.status === 'rejected').length,
    pending: submissions.filter(s => s.status === 'pending').length,
    avgScore: submissions.length ? Math.round(submissions.reduce((a, s) => a + s.ats_score, 0) / submissions.length) : 0,
  };

  return (
    <div className="min-h-screen">
      <Navbar title="HR Admin Panel" />

      {modal && <Modal title="Job Description" content={modal} onClose={() => setModal(null)} />}

      {/* Create Template Modal */}
      {showCreateTemplate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in" style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}>
          <div className="card max-w-lg w-full animate-slide-up">
            <div className="flex items-center justify-between mb-5">
              <h3 className="font-semibold">Create Job Template</h3>
              <button onClick={() => setShowCreateTemplate(false)} className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-white/10" style={{ color: 'var(--text-muted)' }}>✕</button>
            </div>

            <form onSubmit={handleCreateTemplate} className="space-y-4">
              <div>
                <label className="label">Job Role *</label>
                <input
                  type="text"
                  placeholder="e.g., Senior Python Developer"
                  value={templateForm.job_role}
                  onChange={e => setTemplateForm({ ...templateForm, job_role: e.target.value })}
                  className="input-field"
                  required
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-3">
                  <label className="label">Job Description *</label>
                  <div className="flex rounded-lg overflow-hidden border text-xs" style={{ borderColor: 'var(--border)' }}>
                    {['text', 'file'].map(mode => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setTemplateForm({ ...templateForm, descMode: mode })}
                        className="px-3 py-1.5 capitalize transition-colors"
                        style={{
                          background: templateForm.descMode === mode ? 'var(--accent-dim)' : 'transparent',
                          color: templateForm.descMode === mode ? 'var(--accent)' : 'var(--text-muted)',
                        }}
                      >
                        {mode === 'text' ? 'Paste Text' : 'Upload File'}
                      </button>
                    ))}
                  </div>
                </div>

                {templateForm.descMode === 'text' ? (
                  <textarea
                    placeholder="Paste the full job description..."
                    value={templateForm.description}
                    onChange={e => setTemplateForm({ ...templateForm, description: e.target.value })}
                    rows={6}
                    className="input-field resize-none"
                    required
                  />
                ) : (
                  <div
                    onClick={() => document.getElementById('desc-file-input').click()}
                    className="relative rounded-xl cursor-pointer transition-all p-6 text-center"
                    style={{
                      border: `2px dashed ${templateForm.descFile ? 'var(--accent-border)' : 'var(--border)'}`,
                      background: templateForm.descFile ? 'rgba(34,197,94,0.04)' : 'rgba(255,255,255,0.02)',
                    }}
                  >
                    <input
                      id="desc-file-input"
                      type="file"
                      accept=".pdf,.txt"
                      onChange={e => setTemplateForm({ ...templateForm, descFile: e.target.files[0] || null })}
                      className="hidden"
                    />
                    {templateForm.descFile ? (
                      <p className="text-sm" style={{ color: 'var(--accent)' }}>✓ {templateForm.descFile.name}</p>
                    ) : (
                      <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Click to upload (PDF or TXT)</p>
                    )}
                  </div>
                )}
              </div>

              <div>
                <label className="label">Reference Resume File</label>
                <div
                  onClick={() => document.getElementById('resume-input').click()}
                  className="relative rounded-xl cursor-pointer transition-all p-6 text-center"
                  style={{
                    border: `2px dashed ${templateForm.resume ? 'var(--accent-border)' : 'var(--border)'}`,
                    background: templateForm.resume ? 'rgba(34,197,94,0.04)' : 'rgba(255,255,255,0.02)',
                  }}
                >
                  <input
                    id="resume-input"
                    type="file"
                    accept=".pdf,.docx"
                    onChange={e => setTemplateForm({ ...templateForm, resume: e.target.files[0] || null })}
                    className="hidden"
                  />
                  {templateForm.resume ? (
                    <p className="text-sm" style={{ color: 'var(--accent)' }}>✓ {templateForm.resume.name}</p>
                  ) : (
                    <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Click to upload (PDF or DOCX) - Optional</p>
                  )}
                </div>
              </div>

              {error && (
                <div className="text-xs px-3 py-2 rounded-lg" style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)' }}>
                  {error}
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateTemplate(false)}
                  className="btn-ghost flex-1"
                  disabled={templateLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary flex-1 justify-center"
                  disabled={templateLoading}
                >
                  {templateLoading ? 'Creating...' : 'Create Template'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto px-6 py-10">
        <div className="mb-8 animate-fade-in">
          <h2 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Playfair Display, serif' }}>HR Admin Panel</h2>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Manage candidates and job templates</p>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-8 animate-slide-up">
          {[
            { id: 'submissions', label: 'Candidate Submissions' },
            { id: 'templates', label: 'Job Templates' },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="px-5 py-2.5 rounded-lg font-medium text-sm transition-all"
              style={{
                background: tab === t.id ? 'var(--accent)' : 'rgba(255,255,255,0.05)',
                color: tab === t.id ? '#000' : 'var(--text-muted)',
                border: tab === t.id ? 'none' : `1px solid var(--border)`,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* SUBMISSIONS TAB */}
        {tab === 'submissions' && (
          <>
        {/* Stats row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8 animate-slide-up">
          {[
            { label: 'Total', value: stats.total, color: 'var(--text-primary)' },
            { label: 'Pending',  value: stats.pending,  color: '#94a3b8' },
            { label: 'Selected', value: stats.selected, color: '#22c55e' },
            { label: 'Rejected', value: stats.rejected, color: '#ef4444' },
          ].map(stat => (
            <div key={stat.label} className="card py-4">
              <p className="label">{stat.label}</p>
              <p className="text-3xl font-bold font-mono" style={{ color: stat.color, fontFamily: 'JetBrains Mono, monospace' }}>{stat.value}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-5 animate-fade-in">
          <input
            className="input-field max-w-xs"
            placeholder="Search by name or email…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
          <div className="flex rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border)' }}>
            {['all', 'pending', 'selected', 'rejected'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className="px-4 py-2 text-xs capitalize transition-colors"
                style={{
                  background: filter === f ? 'var(--accent-dim)' : 'transparent',
                  color: filter === f ? 'var(--accent)' : 'var(--text-muted)',
                }}
              >
                {f}
              </button>
            ))}
          </div>
          <button onClick={load} className="btn-ghost text-xs py-2">Refresh</button>
        </div>

        {/* Table */}
        {loading ? (
          <div className="card flex items-center justify-center py-16">
            <span className="w-6 h-6 border-2 border-green-500/30 border-t-green-500 rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="card text-center py-10" style={{ color: '#ef4444' }}>{error}</div>
        ) : (
          <div className="card overflow-hidden p-0 animate-slide-up">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
                    {['Candidate', 'Job Description', 'Resume', 'ATS Score', 'Status', 'Date', 'Action', ''].map(h => (
                      <th key={h} className="text-left px-5 py-3.5 text-xs font-medium whitespace-nowrap" style={{ color: 'var(--text-muted)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-5 py-12 text-center text-sm" style={{ color: 'var(--text-muted)' }}>No submissions found</td>
                    </tr>
                  ) : filtered.map(sub => {
                    const missing_skills = (() => { try { return JSON.parse(sub.missing_skills || '[]'); } catch { return []; } })();
                    return (
                      <>
                        <tr key={sub.id} className="border-b transition-colors" style={{ borderColor: 'var(--border)' }}>
                          {/* Candidate */}
                          <td className="px-5 py-4">
                            <p className="font-medium text-sm">{sub.user_name}</p>
                            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{sub.user_email}</p>
                          </td>

                          {/* JD */}
                          <td className="px-5 py-4 max-w-xs">
                            <p className="text-xs truncate w-40" style={{ color: 'var(--text-muted)' }}>{sub.jd_text}</p>
                            <button
                              onClick={() => setModal(sub.jd_text)}
                              className="text-xs mt-1"
                              style={{ color: 'var(--accent)' }}
                            >
                              View full
                            </button>
                          </td>

                          {/* Resume */}
                          <td className="px-5 py-4">
                            <a
                              href={`${api.downloadResume(sub.id)}?token=${localStorage.getItem('ats_token')}`}
                              target="_blank" rel="noreferrer"
                              className="text-xs flex items-center gap-1.5 transition-opacity hover:opacity-80"
                              style={{ color: 'var(--accent)' }}
                            >
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                                <polyline points="7 10 12 15 17 10"/>
                                <line x1="12" y1="15" x2="12" y2="3"/>
                              </svg>
                              Download
                            </a>
                          </td>

                          {/* Score */}
                          <td className="px-5 py-4"><ScoreCell score={sub.ats_score} /></td>

                          {/* Status */}
                          <td className="px-5 py-4">
                            <span className={`badge-${sub.status}`}>{sub.status}</span>
                            {sub.email_sent && <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Email sent</p>}
                          </td>

                          {/* Date */}
                          <td className="px-5 py-4 font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
                            {new Date(sub.created_at).toLocaleDateString()}
                          </td>

                          {/* Action */}
                          <td className="px-5 py-4">
                            <StatusToggle submission={sub} onUpdate={handleUpdate} />
                          </td>

                          {/* Details Toggle */}
                          <td className="px-5 py-4">
                            <button
                              onClick={() => setExpandedId(expandedId === sub.id ? null : sub.id)}
                              className="text-xs px-3 py-1.5 rounded-lg transition-colors"
                              style={{ color: 'var(--accent)', background: 'var(--accent-dim)', border: '1px solid var(--accent-border)' }}
                            >
                              {expandedId === sub.id ? 'Hide' : 'Details'}
                            </button>
                          </td>
                        </tr>

                        {/* Expandable Details Row */}
                        {expandedId === sub.id && (
                          <tr key={`${sub.id}-details`} className="animate-fade-in">
                            <td colSpan={9} className="px-5 pb-4">
                              <div className="rounded-xl p-4 space-y-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }}>
                                {/* Score Breakdown */}
                                <div>
                                  <p className="font-semibold text-sm mb-3" style={{ color: 'var(--accent)' }}>Score Breakdown</p>
                                  <div className="grid grid-cols-3 gap-3">
                                    <div>
                                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Skill Match</p>
                                      <p className="text-lg font-bold font-mono" style={{ color: '#22c55e' }}>{sub.skill_match ? Math.round(sub.skill_match) : '—'}%</p>
                                    </div>
                                    <div>
                                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Education Match</p>
                                      <p className="text-lg font-bold font-mono" style={{ color: '#22c55e' }}>{sub.education_match ? Math.round(sub.education_match) : '—'}%</p>
                                    </div>
                                    <div>
                                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Experience Match</p>
                                      <p className="text-lg font-bold font-mono" style={{ color: '#22c55e' }}>{sub.experience_match ? Math.round(sub.experience_match) : '—'}%</p>
                                    </div>
                                  </div>
                                </div>

                                {/* Missing Skills */}
                                {missing_skills?.length > 0 && (
                                  <div>
                                    <p className="font-semibold text-sm mb-2" style={{ color: 'var(--accent)' }}>Missing Skills & Keywords</p>
                                    <div className="flex flex-wrap gap-2">
                                      {missing_skills.map((skill, i) => (
                                        <span key={i} className="px-2.5 py-1 rounded-lg text-xs" style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.2)' }}>{skill}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Education Gap */}
                                {sub.education_gap && sub.education_gap !== 'None' && (
                                  <div>
                                    <p className="font-semibold text-sm mb-1" style={{ color: 'var(--accent)' }}>Education Gap</p>
                                    <p className="text-xs leading-relaxed" style={{ color: 'var(--text-subtle)' }}>{sub.education_gap}</p>
                                  </div>
                                )}

                                {/* Experience Gap */}
                                {sub.experience_gap && sub.experience_gap !== 'None' && (
                                  <div>
                                    <p className="font-semibold text-sm mb-1" style={{ color: 'var(--accent)' }}>Experience Gap</p>
                                    <p className="text-xs leading-relaxed" style={{ color: 'var(--text-subtle)' }}>{sub.experience_gap}</p>
                                  </div>
                                )}
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
            {filtered.length > 0 && (
              <div className="px-5 py-3 border-t" style={{ borderColor: 'var(--border)' }}>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Showing {filtered.length} of {submissions.length} submissions</p>
              </div>
            )}
          </div>
        )}
          </>
        )}

        {/* JOB TEMPLATES TAB */}
        {tab === 'templates' && (
          <>
            <div className="mb-6 flex items-center justify-between animate-slide-up">
              <div>
                <h3 className="font-semibold text-lg mb-1">Manage Job Templates</h3>
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{templates.length} template{templates.length !== 1 ? 's' : ''} available</p>
              </div>
              <button
                onClick={() => setShowCreateTemplate(true)}
                className="btn-primary text-sm py-2"
              >
                + Create Template
              </button>
            </div>

            {templates.length === 0 ? (
              <div className="card text-center py-16">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="mx-auto mb-4" style={{ opacity: 0.5 }}>
                  <path d="M9 11l3 3L22 4"/>
                  <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <p style={{ color: 'var(--text-muted)' }}>No job templates yet</p>
                <p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>Create one to make it available for users to select</p>
              </div>
            ) : (
              <div className="grid gap-4 animate-slide-up">
                {templates.map(t => (
                  <div key={t.id} className="card p-5 flex items-start justify-between hover:bg-white/[0.03] transition-colors">
                    <div className="flex-1">
                      <h4 className="font-semibold text-base mb-1">{t.job_role}</h4>
                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Created {new Date(t.created_at).toLocaleDateString()}</p>
                    </div>
                    <button
                      onClick={() => handleDeleteTemplate(t.id)}
                      className="px-3 py-2 rounded-lg text-xs transition-colors"
                      style={{
                        background: 'rgba(239,68,68,0.1)',
                        color: '#ef4444',
                        border: '1px solid rgba(239,68,68,0.2)',
                      }}
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}