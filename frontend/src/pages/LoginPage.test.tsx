import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { LoginPage } from './LoginPage'
import { AuthProvider } from '../auth/AuthContext'
import * as endpoints from '../api/endpoints'

// Mocks the API layer, not axios internals — LoginPage's contract with
// the rest of the app is "call login(), show the error extractErrorMessage
// produces on failure," not any particular HTTP mechanics. This mirrors
// how the backend's own tests mock AIServiceManager rather than the Groq
// client underneath it.
vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return { ...actual, login: vi.fn() }
})

function renderLoginPage() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(endpoints.login).mockReset()
})

describe('LoginPage', () => {
  it('renders email and password fields', () => {
    renderLoginPage()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('calls login() with the entered credentials on submit', async () => {
    vi.mocked(endpoints.login).mockResolvedValue({
      access_token: 'token',
      token_type: 'bearer',
      expires_in_minutes: 60,
      user_id: 'u1',
      company_id: 'c1',
      role: 'owner',
      email: 'admin@example.com',
      refresh_token: 'refresh',
      refresh_token_expires_in_days: 30,
      session_id: 's1',
    })
    const user = userEvent.setup()
    renderLoginPage()

    await user.type(screen.getByLabelText(/email/i), 'admin@example.com')
    await user.type(screen.getByLabelText(/password/i), 'Admin@123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(endpoints.login).toHaveBeenCalledWith('admin@example.com', 'Admin@123')
    })
  })

  it('shows an error message when login fails', async () => {
    vi.mocked(endpoints.login).mockRejectedValue({
      isAxiosError: true,
      response: { status: 401, data: { message: 'Incorrect email or password.' } },
    })
    const user = userEvent.setup()
    renderLoginPage()

    await user.type(screen.getByLabelText(/email/i), 'wrong@example.com')
    await user.type(screen.getByLabelText(/password/i), 'wrongpass')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect email or password/i)
  })

  it('links to the forgot-password page', () => {
    renderLoginPage()
    expect(screen.getByRole('link', { name: /forgot your password/i })).toHaveAttribute(
      'href',
      '/forgot-password',
    )
  })
})
