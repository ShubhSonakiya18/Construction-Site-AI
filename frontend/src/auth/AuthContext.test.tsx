import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { AuthProvider, useAuth } from './AuthContext'
import * as endpoints from '../api/endpoints'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return { ...actual, login: vi.fn(), logout: vi.fn() }
})

function Probe() {
  const { user, isAuthenticated, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="authed">{String(isAuthenticated)}</span>
      <span data-testid="email">{user?.email ?? 'none'}</span>
      <button onClick={() => void login('a@b.com', 'pw')}>do-login</button>
      <button onClick={() => void logout()}>do-logout</button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(endpoints.login).mockReset()
  vi.mocked(endpoints.logout).mockReset()
})

describe('AuthProvider / useAuth', () => {
  it('starts unauthenticated with no stored token', async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('authed')).toHaveTextContent('false'))
  })

  it('becomes authenticated after login() resolves, and persists to localStorage', async () => {
    vi.mocked(endpoints.login).mockResolvedValue({
      access_token: 'tok',
      token_type: 'bearer',
      expires_in_minutes: 60,
      user_id: 'u1',
      company_id: 'c1',
      role: 'owner',
      email: 'a@b.com',
      refresh_token: 'ref',
      refresh_token_expires_in_days: 30,
      session_id: 's1',
    })
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await act(async () => {
      screen.getByText('do-login').click()
    })
    await waitFor(() => expect(screen.getByTestId('authed')).toHaveTextContent('true'))
    expect(screen.getByTestId('email')).toHaveTextContent('a@b.com')
    expect(localStorage.getItem('csa_access_token')).toBe('tok')
  })

  it('clears state and localStorage after logout()', async () => {
    localStorage.setItem('csa_access_token', 'tok')
    localStorage.setItem('csa_refresh_token', 'ref')
    localStorage.setItem(
      'csa_user',
      JSON.stringify({ userId: 'u1', companyId: 'c1', email: 'a@b.com', role: 'owner' }),
    )
    vi.mocked(endpoints.logout).mockResolvedValue(undefined)

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('authed')).toHaveTextContent('true'))

    await act(async () => {
      screen.getByText('do-logout').click()
    })
    await waitFor(() => expect(screen.getByTestId('authed')).toHaveTextContent('false'))
    expect(localStorage.getItem('csa_user')).toBeNull()
  })
})
