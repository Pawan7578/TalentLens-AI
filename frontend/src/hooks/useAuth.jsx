import { createContext, useContext, useState, useEffect } from 'react';
import { api } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('ats_user')); } catch { return null; }
  });
  const [loading, setLoading] = useState(true);

  // Validate token and restore auth state on app load
  useEffect(() => {
    const validateAuth = async () => {
      try {
        const token = localStorage.getItem('ats_token');
        const refreshToken = localStorage.getItem('ats_refresh_token');

        if (!token && !refreshToken) {
          setUser(null);
          setLoading(false);
          return;
        }

        try {
          const userData = await api.me();
          setUser({ name: userData.name, role: userData.role, id: userData.id });
          console.log(`✓ Auth restored: ${userData.name} (${userData.role})`);
        } catch (err) {
          // FIX: Only clear tokens on definitive auth failures (401/403).
          // Previously, ANY error (including network timeouts when the backend
          // is slow to start) wiped tokens, causing every subsequent request
          // to return 401 Unauthorized.
          const status = err?.status || err?.response?.status;
          const isAuthError =
            status === 401 ||
            status === 403 ||
            (err?.message || '').toLowerCase().includes('401') ||
            (err?.message || '').toLowerCase().includes('unauthorized') ||
            (err?.message || '').toLowerCase().includes('could not validate');

          if (isAuthError) {
            console.warn('Invalid token, clearing auth:', err?.message);
            localStorage.removeItem('ats_token');
            localStorage.removeItem('ats_refresh_token');
            localStorage.removeItem('ats_user');
            setUser(null);
          } else {
            // Network error or backend not ready — keep tokens, restore user
            // from localStorage so the UI stays logged in.
            console.warn('Auth check failed (network/server error), keeping session:', err?.message);
            const cached = localStorage.getItem('ats_user');
            if (cached) {
              try {
                setUser(JSON.parse(cached));
                console.log('✓ Auth restored from cache (backend unreachable)');
              } catch {
                setUser(null);
              }
            } else {
              setUser(null);
            }
          }
        }
      } catch (err) {
        console.error('Auth validation error:', err);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    validateAuth();
  }, []);

  const login = (tokenData) => {
    const accessToken = tokenData.access_token || tokenData.token;
    if (accessToken) {
      localStorage.setItem('ats_token', accessToken);
    }
    if (tokenData.refresh_token) {
      localStorage.setItem('ats_refresh_token', tokenData.refresh_token);
    }
    const u = { name: tokenData.name, role: tokenData.role, id: tokenData.id };
    localStorage.setItem('ats_user', JSON.stringify(u));
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem('ats_token');
    localStorage.removeItem('ats_refresh_token');
    localStorage.removeItem('ats_user');
    setUser(null);
    console.log('User logged out');
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
