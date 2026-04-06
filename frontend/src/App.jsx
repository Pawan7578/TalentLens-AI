import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './hooks/useAuth';
import Login from './pages/Login';
import Signup from './pages/Signup';
import UserDashboard from './pages/UserDashboard';
import AdminPanel from './pages/AdminPanel';

function PrivateRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuth();
  
  if (loading) return <div className="flex items-center justify-center h-screen">Loading...</div>;
  
  if (!user) {
    console.warn('PrivateRoute: No user, redirecting to /login');
    return <Navigate to="/login" replace />;
  }
  
  if (adminOnly && user.role !== 'admin') {
    console.warn(`PrivateRoute: User role "${user.role}" not admin, redirecting to /dashboard`);
    return <Navigate to="/dashboard" replace />;
  }
  
  return children;
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth();
  
  if (loading) return <div className="flex items-center justify-center h-screen">Loading...</div>;
  
  if (user) {
    const redirectTo = user.role === 'admin' ? '/admin' : '/dashboard';
    console.log(`PublicRoute: User already logged in as ${user.role}, redirecting to ${redirectTo}`);
    return <Navigate to={redirectTo} replace />;
  }
  
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="/login"  element={<PublicRoute><Login /></PublicRoute>} />
          <Route path="/signup" element={<PublicRoute><Signup /></PublicRoute>} />
          <Route path="/dashboard" element={<PrivateRoute><UserDashboard /></PrivateRoute>} />
          <Route path="/admin"     element={<PrivateRoute adminOnly><AdminPanel /></PrivateRoute>} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}