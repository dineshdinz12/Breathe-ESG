import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: <GridIcon /> },
  { to: '/review', label: 'Review Queue', icon: <CheckIcon /> },
  { to: '/upload', label: 'Upload Data', icon: <UploadIcon /> },
  { to: '/batches', label: 'Batch History', icon: <LayersIcon /> },
];

export default function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => { await logout(); navigate('/login'); };
  const initials = user?.username?.slice(0, 2).toUpperCase() || '??';

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <circle cx="14" cy="14" r="14" fill="#22c55e" fillOpacity="0.15"/>
          <path d="M14 6c-1.5 3-5 5-5 9a5 5 0 0010 0c0-4-3.5-6-5-9z" fill="#22c55e"/>
        </svg>
        <div>
          <div className="sidebar-logo-text">Breathe</div>
          <div className="sidebar-logo-sub">ESG Platform</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Main</div>
        {NAV.map(({ to, label, icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
            {icon}{label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <div className="sidebar-avatar">{initials}</div>
          <div>
            <div className="sidebar-username">{user?.username}</div>
            <div className="sidebar-role">{user?.is_staff ? 'Admin' : 'Analyst'}</div>
          </div>
          <button className="btn-logout" onClick={handleLogout}>Sign out</button>
        </div>
      </div>
    </aside>
  );
}

function GridIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/><rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>;
}
function CheckIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M1.5 9L5.5 13L14.5 4"/><circle cx="8" cy="8" r="7"/></svg>;
}
function UploadIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 10V3M5 6l3-3 3 3M3 13h10"/></svg>;
}
function LayersIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 1L15 5L8 9L1 5L8 1z"/><path d="M1 11l7 4 7-4"/><path d="M1 8l7 4 7-4"/></svg>;
}
