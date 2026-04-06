import { useState, useEffect } from 'react';
import { api } from '../api';
import { useAuth } from '../hooks/useAuth';
import Navbar from '../components/Navbar';
import FileDropzone from '../components/FileDropzone';
import UserAnalysisCard from '../components/UserAnalysisCard';
import AdminAnalysisCard from '../components/AdminAnalysisCard';
import HistoryTable from '../components/HistoryTable';

export default function UserDashboard() {
  const { user } = useAuth();
  const [jdMode, setJdMode] = useState('text'); // 'text' | 'file' | 'template'
  const [jdText, setJdText] = useState('');
  const [jdFile, setJdFile] = useState(null);
  const [resumeFile, setResumeFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState([]);
  const [histLoading, setHistLoading] = useState(true);
  const [jobTemplates, setJobTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [templatesLoading, setTemplatesLoading] = useState(false);

  const loadHistory = async () => {
    try {
      const data = await api.history();
      setHistory(data);
    } catch (_) {}
    finally { setHistLoading(false); }
  };

  const loadJobTemplates = async () => {
    // Only load if user is admin or if templates are publicly available
    try {
      setTemplatesLoading(true);
      const data = await api.listJobTemplates();
      setJobTemplates(data || []);
    } catch (_) {
      // Templates endpoint may not be available for regular users
      setJobTemplates([]);
    } finally {
      setTemplatesLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
    loadJobTemplates();
  }, []);

  const submit = async () => {
    setError('');
    if (!resumeFile) { setError('Please upload your resume'); return; }
    
    // Validate job description source
    if (jdMode === 'template') {
      if (!selectedTemplate) { setError('Please select a job template'); return; }
    } else if (jdMode === 'text') {
      if (!jdText.trim()) { setError('Please paste the job description'); return; }
    } else if (jdMode === 'file') {
      if (!jdFile) { setError('Please upload the job description file'); return; }
    }

    setLoading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append('resume', resumeFile);
      
      if (jdMode === 'template') {
        fd.append('job_template_id', selectedTemplate.id);
      } else if (jdMode === 'text') {
        fd.append('jd_text', jdText);
      } else {
        fd.append('jd_file', jdFile);
      }

      const data = await api.analyze(fd);
      setResult(data);
      loadHistory();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <Navbar title="TalentLens AI" />

      <main className="max-w-7xl mx-auto px-6 py-10">
        <div className="mb-8 animate-fade-in">
          <h2 className="text-2xl font-bold mb-1" style={{ fontFamily: 'Playfair Display, serif' }}>Analyze Your Resume</h2>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Upload your resume and select or paste a job description to get an ATS compatibility score</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Left — Upload form */}
          <div className="space-y-6 animate-slide-up">
            {/* Job Template Selector (Non-breaking, optional) */}
            {jobTemplates.length > 0 && (
              <div className="card">
                <h3 className="font-semibold text-sm mb-4">Quick Select: Use Job Template</h3>
                <div className="space-y-3">
                  <select
                    value={selectedTemplate?.id || ''}
                    onChange={(e) => {
                      const selected = jobTemplates.find(t => t.id === parseInt(e.target.value));
                      setSelectedTemplate(selected || null);
                      if (selected) setJdMode('template');
                    }}
                    className="w-full px-3 py-2.5 rounded-lg border transition-colors"
                    style={{
                      borderColor: 'var(--border)',
                      background: 'rgba(255,255,255,0.02)',
                      color: 'var(--text-main)',
                      fontSize: '0.875rem',
                    }}
                  >
                    <option value="">— Select a job role —</option>
                    {jobTemplates.map(t => (
                      <option key={t.id} value={t.id}>
                        {t.job_role} ({new Date(t.created_at).toLocaleDateString()})
                      </option>
                    ))}
                  </select>
                  {selectedTemplate && (
                    <div 
                      className="p-4 rounded-lg border text-sm"
                      style={{
                        borderColor: 'var(--accent-border)',
                        background: 'rgba(34,197,94,0.05)',
                      }}
                    >
                      <p className="font-semibold mb-2" style={{ color: 'var(--accent)' }}>📋 Job Description:</p>
                      <p className="leading-relaxed whitespace-pre-wrap text-xs" style={{ color: 'var(--text-subtle)' }}>
                        {selectedTemplate.description}
                      </p>
                    </div>
                  )}
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {selectedTemplate ? `✓ Ready to analyze` : 'Select a template or use manual entry below'}
                  </p>
                </div>
              </div>
            )}

            {/* JD section */}
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-sm">Job Description</h3>
                <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: 'var(--border)' }}>
                  {['text', 'file'].map(mode => (
                    <button
                      key={mode}
                      onClick={() => {
                        setJdMode(mode);
                        setSelectedTemplate(null);
                      }}
                      className="px-3 py-1.5 text-xs capitalize transition-colors"
                      style={{
                        background: jdMode === mode ? 'var(--accent-dim)' : 'transparent',
                        color: jdMode === mode ? 'var(--accent)' : 'var(--text-muted)',
                      }}
                    >
                      {mode === 'text' ? 'Paste Text' : 'Upload File'}
                    </button>
                  ))}
                </div>
              </div>

              {jdMode === 'text' ? (
                <div>
                  <label className="label">Paste job description</label>
                  <textarea
                    className="input-field resize-none"
                    rows={8}
                    placeholder="Paste the full job description here…"
                    value={jdText}
                    onChange={e => setJdText(e.target.value)}
                  />
                </div>
              ) : (
                <FileDropzone
                  label="Job Description File"
                  accept=".pdf,.txt"
                  file={jdFile}
                  onChange={setJdFile}
                  hint="PDF or TXT files accepted"
                />
              )}
            </div>

            {/* Resume section */}
            <div className="card">
              <h3 className="font-semibold text-sm mb-4">Your Resume</h3>
              <FileDropzone
                label="Upload Resume"
                accept=".pdf,.docx"
                file={resumeFile}
                onChange={setResumeFile}
                hint="PDF or DOCX files accepted"
              />
            </div>

            {error && (
              <div className="text-sm px-4 py-3 rounded-xl" style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.2)' }}>
                {error}
              </div>
            )}

            <button onClick={submit} disabled={loading} className="btn-primary w-full justify-center text-base py-4">
              {loading ? (
                <>
                  <span className="w-5 h-5 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                  Analyzing with AI… this may take a minute
                </>
              ) : (
                <>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                  </svg>
                  Analyze Resume
                </>
              )}
            </button>
          </div>

          {/* Right — Result */}
          <div>
            {result ? (
              user?.role === 'admin' ? (
                <AdminAnalysisCard result={result} />
              ) : (
                <UserAnalysisCard result={result} />
              )
            ) : (
              <div className="card h-full min-h-64 flex flex-col items-center justify-center text-center" style={{ opacity: 0.5 }}>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" className="mb-4">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12 6 12 12 16 14"/>
                </svg>
                <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Your ATS score and analysis will appear here after you click Analyze</p>
              </div>
            )}
          </div>
        </div>

        {/* History */}
        <div className="mt-12 animate-fade-in">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold" style={{ fontFamily: 'Playfair Display, serif' }}>Past Submissions</h2>
            <button onClick={loadHistory} className="btn-ghost text-xs py-2">Refresh</button>
          </div>
          {histLoading ? (
            <div className="card flex items-center justify-center py-10">
              <span className="w-5 h-5 border-2 border-green-500/30 border-t-green-500 rounded-full animate-spin" />
            </div>
          ) : (
            <HistoryTable submissions={history} />
          )}
        </div>
      </main>
    </div>
  );
}