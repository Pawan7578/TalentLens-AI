import { createContext, useContext, useState, useEffect } from 'react';

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

        // Try to validate token with /auth/me endpoint
        const res = await fetch('/auth/me', {
          headers: { 'Authorization': `Bearer ${token}` }
        });

        if (res.ok) {
          const userData = await res.json();
          setUser({ name: userData.name, role: userData.role, id: userData.id });
          console.log(`✓ Auth restored: ${userData.name} (${userData.role})`);
        } else {
          // Token invalid
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
    
    // Set global auth header
    const token = tokenData.access_token;
    if (token) {
      fetch('/auth/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      }).catch(err => console.error('Failed to set global auth:', err));
    }
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