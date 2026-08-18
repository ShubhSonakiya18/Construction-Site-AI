import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from './ProtectedRoute'
import { AuthProvider } from '../auth/AuthContext'

function renderAtRoot() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/" element={<div>Protected Dashboard</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('ProtectedRoute', () => {
  it('redirects to /login when no access token is stored', async () => {
    renderAtRoot()
    expect(await screen.findByText('Login Page')).toBeInTheDocument()
  })

  it('renders the protected content when an access token and user are stored', async () => {
    localStorage.setItem('csa_access_token', 'fake-token')
    localStorage.setItem('csa_refresh_token', 'fake-refresh')
    localStorage.setItem(
      'csa_user',
      JSON.stringify({ userId: 'u1', companyId: 'c1', email: 'a@b.com', role: 'owner' }),
    )
    renderAtRoot()
    expect(await screen.findByText('Protected Dashboard')).toBeInTheDocument()
  })
})
