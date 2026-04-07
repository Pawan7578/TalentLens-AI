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
        if (!token) {
          setUser(null);
          setLoading(false);
          return;
        }

        try {
          const userData = await api.me();
          setUser({ name: userData.name, role: userData.role, id: userData.id });
          console.log(`✓ Auth restored: ${userData.name} (${userData.role})`);
        } catch {
          console.warn('Invalid token, clearing auth');
          localStorage.removeItem('ats_token');
          localStorage.removeItem('ats_user');
          setUser(null);
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
    localStorage.setItem('ats_token', tokenData.access_token);
    const u = { name: tokenData.name, role: tokenData.role, id: tokenData.id };
    localStorage.setItem('ats_user', JSON.stringify(u));
    setUser(u);
  };

  const logout = () => {
    localStorage.removeItem('ats_token');
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