import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './components/AuthContext';
import Sidebar from './components/Sidebar';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Review from './pages/Review';
import Upload from './pages/Upload';
import Batches from './pages/Batches';
import './index.css';

function ProtectedLayout({ children }) {
  const { user } = useAuth();
  if (user === undefined) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}><div className="spinner" /></div>;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-area">{children}</div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/dashboard" element={<ProtectedLayout><Dashboard /></ProtectedLayout>} />
          <Route path="/review"    element={<ProtectedLayout><Review /></ProtectedLayout>} />
          <Route path="/upload"    element={<ProtectedLayout><Upload /></ProtectedLayout>} />
          <Route path="/batches"   element={<ProtectedLayout><Batches /></ProtectedLayout>} />
          <Route path="*"          element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
