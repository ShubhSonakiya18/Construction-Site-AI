import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-brand">Construction Site AI</div>
        <nav className="app-nav">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>
            Dashboard
          </NavLink>
          <NavLink to="/record" className={({ isActive }) => (isActive ? 'active' : '')}>
            Record
          </NavLink>
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
