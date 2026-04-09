/**
 * AdminAnalysisCard - Full analysis view for admin users
 * Shows all detailed metrics: skill/education/experience match, gaps, missing skills
 * Same as the standard ATSScoreCard with all detail sections
 */

function scoreColor(score) {
  if (score >= 70) return { stroke: '#22c55e', text: 'score-green', label: 'Excellent' };
  if (score >= 40) return { stroke: '#f59e0b', text: 'score-amber', label: 'Average' };
  return { stroke: '#ef4444', text: 'score-red', label: 'Low' };
}

function toList(value) {
  if (!Array.isArray(value)) return [];
  return value.map(item => String(item).trim()).filter(Boolean);
}

function ScoreBar({ label, score }) {
  const colors = scoreColor(score);
  return (
    <div className="flex items-center gap-3 text-sm">
      <span style={{ color: 'var(--text-muted)', minWidth: '100px' }}>{label}</span>
      <div className="flex-1 h-2 rounded-full" style={{ background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${score}%`,
            background: colors.stroke,
            boxShadow: `0 0 8px ${colors.stroke}40`,
          }}
        />
      </div>
      <span className="font-semibold" style={{ color: colors.stroke, minWidth: '30px', textAlign: 'right' }}>{score}%</span>
    </div>
  );
}

export default function AdminAnalysisCard({ result }) {
  const {
    final_score,
    ats_score,
    skill_match,
    education_match,
    experience_match,
    matched_skills,
    missing_skills,
    suggestions,
    education_gap,
    experience_gap,
    feedback,
    provider,
    ai_unavailable,
  } = result;

  const rawScore = final_score ?? ats_score;
  const numericScore = Number(rawScore);
  const score = Number.isFinite(numericScore) ? Math.round(Math.max(0, Math.min(100, numericScore)) * 10) / 10 : 0;
  const matchedSkills = toList(matched_skills);
  const missingSkills = toList(missing_skills);
  const suggestionItems = toList(suggestions);
  const colors = scoreColor(score);

  // SVG circle animation
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="animate-slide-up space-y-5">
      {/* Score circle */}
      <div className="card flex flex-col items-center py-8">
        <p className="label mb-4">Final ATS Score</p>
        <div className="relative">
          <svg width="180" height="180" viewBox="0 0 180 180">
            {/* Track */}
            <circle cx="90" cy="90" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="12" />
            {/* Fill */}
            <circle
              cx="90" cy="90" r={radius}
              fill="none"
              stroke={colors.stroke}
              strokeWidth="12"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              transform="rotate(-90 90 90)"
              style={{
                transition: 'stroke-dashoffset 1.2s cubic-bezier(0.4,0,0.2,1)',
                filter: `drop-shadow(0 0 8px ${colors.stroke}60)`,
              }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-4xl font-bold font-mono ${colors.text}`}>{score}</span>
            <span className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{colors.label}</span>
          </div>
        </div>
        {provider && (
          <span className="mt-4 text-xs px-3 py-1 rounded-full flex items-center gap-1.5"
            style={{ background: provider === 'groq' ? 'rgba(251,191,36,0.1)' : 'var(--accent-dim)', color: provider === 'groq' ? '#fbbf24' : 'var(--accent)', border: `1px solid ${provider === 'groq' ? 'rgba(251,191,36,0.25)' : 'var(--accent-border)'}` }}>
            {provider === 'groq' ? '⚡' : '🖥️'} via {provider === 'groq' ? 'Groq Cloud' : 'Local Fallback'}
          </span>
        )}
      </div>

      {/* Detailed scores */}
      {ai_unavailable && (
        <div className="card">
          <p className="text-sm font-medium" style={{ color: '#f59e0b' }}>
            AI analysis unavailable, showing basic results
          </p>
        </div>
      )}

      {(skill_match !== undefined || education_match !== undefined || experience_match !== undefined) && (
        <div className="card">
          <h3 className="text-base font-semibold mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
            Detailed Analysis
          </h3>
          <div className="space-y-3">
            {skill_match !== undefined && <ScoreBar label="Skill Match" score={Math.round(Number(skill_match) * 10) / 10} />}
            {education_match !== undefined && <ScoreBar label="Education Match" score={Math.round(Number(education_match) * 10) / 10} />}
            {experience_match !== undefined && <ScoreBar label="Experience Match" score={Math.round(Number(experience_match) * 10) / 10} />}
          </div>
        </div>
      )}

      {/* Education and Experience Gaps */}
      {(education_gap || experience_gap) && (
        <div className="card">
          <h3 className="text-base font-semibold mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-400 inline-block" />
            Gaps & Improvements
          </h3>
          <div className="space-y-3 text-sm">
            {education_gap && education_gap !== 'None' && (
              <div>
                <p className="font-medium mb-1" style={{ color: 'var(--accent)' }}>Education Gap</p>
                <p style={{ color: 'var(--text-subtle)' }}>{education_gap}</p>
              </div>
            )}
            {experience_gap && experience_gap !== 'None' && (
              <div>
                <p className="font-medium mb-1" style={{ color: 'var(--accent)' }}>Experience Gap</p>
                <p style={{ color: 'var(--text-subtle)' }}>{experience_gap}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Matched skills */}
      {matchedSkills.length > 0 && (
        <div className="card">
          <h3 className="text-base font-semibold mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
            Matched Skills
          </h3>
          <div className="flex flex-wrap gap-2">
            {matchedSkills.map((skill, i) => (
              <span key={`${skill}-${i}`} className="px-3 py-1.5 rounded-lg text-xs font-medium" style={{ background: 'rgba(34,197,94,0.1)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.2)' }}>
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Missing skills */}
      {missingSkills.length > 0 && (
        <div className="card">
          <h3 className="text-base font-semibold mb-4 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
            Missing Skills & Keywords
          </h3>
          <div className="flex flex-wrap gap-2">
            {missingSkills.map((skill, i) => (
              <span key={`${skill}-${i}`} className="px-3 py-1.5 rounded-lg text-xs font-medium" style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.2)' }}>
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Suggestions */}
      {suggestionItems.length > 0 && (
        <div className="card">
          <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />
            Suggestions
          </h3>
          <ul className="space-y-2 text-sm" style={{ color: 'var(--text-subtle)' }}>
            {suggestionItems.map((item, idx) => (
              <li key={`suggestion-${idx}`} className="flex items-start gap-2">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full" style={{ background: 'var(--text-muted)' }} />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Feedback */}
      {feedback && (
        <div className="card">
          <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />
            AI Feedback
          </h3>
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-subtle)' }}>{feedback}</p>
        </div>
      )}
    </div>
  );
}
