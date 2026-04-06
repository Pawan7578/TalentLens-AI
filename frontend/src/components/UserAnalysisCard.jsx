/**
 * UserAnalysisCard - Minimal view for regular users
 * Shows only ATS score + feedback
 * Hides detailed analysis (skill/education/experience match, gaps, missing skills)
 */

function scoreColor(score) {
  if (score >= 70) return { stroke: '#22c55e', text: 'score-green', label: 'Excellent' };
  if (score >= 40) return { stroke: '#f59e0b', text: 'score-amber', label: 'Average' };
  return { stroke: '#ef4444', text: 'score-red', label: 'Low' };
}

export default function UserAnalysisCard({ result }) {
  const { ats_score, feedback } = result;
  const score = Math.round(ats_score || 50);
  const colors = scoreColor(score);

  // SVG circle animation
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="animate-slide-up space-y-5">
      {/* Score circle - Main focus */}
      <div className="card flex flex-col items-center py-8">
        <p className="label mb-4">ATS Compatibility Score</p>
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

      {/* Feedback only */}
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
