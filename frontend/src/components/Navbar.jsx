import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

export default function Navbar({ title }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="border-b sticky top-0 z-40 backdrop-blur-md" style={{ borderColor: 'var(--border)', background: 'rgba(2,8,23,0.85)' }}>
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--accent-dim)', border: '1px solid var(--accent-border)' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <span className="font-semibold text-sm" style={{ fontFamily: 'Playfair Display, serif' }}>{title}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
            {user?.name}
            {user?.role === 'admin' && (
              <span className="ml-2 text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid var(--accent-border)' }}>Admin</span>
            )}
          </span>
          <button onClick={handleLogout} className="btn-ghost text-xs py-2">Sign out</button>
        </div>
      </div>
    </header>
  );
}