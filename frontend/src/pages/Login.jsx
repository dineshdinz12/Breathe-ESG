import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../components/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      await login(username, password);
      navigate('/dashboard');
    } catch {
      setError('Invalid credentials. Try admin/admin123 or analyst/analyst123');
    } finally { setLoading(false); }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-leaf">🌱</div>
          <div className="login-title">Breathe ESG</div>
          <div className="login-sub">Emissions Review Platform</div>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Username</label>
            <input id="username" className="form-input" value={username} onChange={e => setUsername(e.target.value)} placeholder="admin or analyst" autoFocus />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input id="password" type="password" className="form-input" value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
          </div>
          {error && <div style={{ color: 'var(--accent-red)', fontSize: 12, marginBottom: 10 }}>{error}</div>}
          <button id="login-btn" className="btn btn-primary btn-full" type="submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
        <div className="login-demo-hint">Demo: admin / admin123 &nbsp;·&nbsp; analyst / analyst123</div>
      </div>
    </div>
  );
}
