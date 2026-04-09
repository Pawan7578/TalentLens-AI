/**
 * UserAnalysisCard - Candidate-facing analysis summary
 * Displays final ATS score plus key skill and suggestion insights.
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

export default function UserAnalysisCard({ result }) {
  const {
    final_score,
    ats_score,
    matched_skills,
    missing_skills,
    suggestions,
    feedback,
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
      {/* Final score */}
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
      </div>

      {/* Matched skills */}
      {ai_unavailable && (
        <div className="card">
          <p className="text-sm font-medium" style={{ color: '#f59e0b' }}>
            AI analysis unavailable, showing basic results
          </p>
        </div>
      )}

      <div className="card">
        <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-400 inline-block" />
          Matched Skills
        </h3>
        {matchedSkills.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {matchedSkills.map((skill, idx) => (
              <span
                key={`matched-${skill}-${idx}`}
                className="px-3 py-1.5 rounded-lg text-xs font-medium"
                style={{
                  background: 'rgba(34,197,94,0.1)',
                  color: '#22c55e',
                  border: '1px solid rgba(34,197,94,0.2)',
                }}
              >
                {skill}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-subtle)' }}>
            No strong direct skill matches were identified.
          </p>
        )}
      </div>

      {/* Missing skills */}
      <div className="card">
        <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-400 inline-block" />
          Missing Skills
        </h3>
        {missingSkills.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {missingSkills.map((skill, idx) => (
              <span
                key={`missing-${skill}-${idx}`}
                className="px-3 py-1.5 rounded-lg text-xs font-medium"
                style={{
                  background: 'rgba(245,158,11,0.1)',
                  color: '#f59e0b',
                  border: '1px solid rgba(245,158,11,0.2)',
                }}
              >
                {skill}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-subtle)' }}>
            No missing skills were flagged for this job description.
          </p>
        )}
      </div>

      {/* Suggestions */}
      <div className="card">
        <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-400 inline-block" />
          Suggestions
        </h3>
        {suggestionItems.length > 0 ? (
          <ul className="space-y-2 text-sm" style={{ color: 'var(--text-subtle)' }}>
            {suggestionItems.map((item, idx) => (
              <li key={`suggestion-${idx}`} className="flex items-start gap-2">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full" style={{ background: 'var(--text-muted)' }} />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-subtle)' }}>
            No additional suggestions were returned.
          </p>
        )}
      </div>

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
