import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { AUDIO_UPLOAD_ROLES } from '../auth/roles'

export function AppLayout() {
  const { user, logout } = useAuth()
  // Permission.AUDIO_UPLOAD (app/core/permissions.py) — a role without it
  // (safety_officer, client) 403s on POST /audio/upload, so the nav item
  // to a page whose only real action is that upload is hidden rather than
  // offering a dead end. Sprint 10, Deliverable 7 (client-portal RBAC).
  const canRecord = AUDIO_UPLOAD_ROLES.has(user?.role ?? '')

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-brand">Construction Site AI</div>
        <nav className="app-nav">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Dashboard
          </NavLink>
          {canRecord && (
            <NavLink to="/record" className={({ isActive }) => (isActive ? 'active' : '')}>
              Record
            </NavLink>
          )}
        </nav>
        <div className="app-header-user">
          <span className="app-header-email">{user?.email}</span>
          <button type="button" className="btn-link" onClick={() => void logout()}>
            Log out
          </button>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
