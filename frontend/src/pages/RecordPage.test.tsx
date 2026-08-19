import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RecordPage } from './RecordPage'
import { AuthProvider } from '../auth/AuthContext'

function renderAsRole(role: string) {
  localStorage.setItem('csa_access_token', 'fake-token')
  localStorage.setItem('csa_refresh_token', 'fake-refresh')
  localStorage.setItem(
    'csa_user',
    JSON.stringify({ userId: 'u1', companyId: 'c1', email: 'a@b.com', role }),
  )
  return render(
    <MemoryRouter>
      <AuthProvider>
        <RecordPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('RecordPage — direct-navigation guard (Sprint 10, Deliverable 7)', () => {
  it('shows a permission message instead of the recorder for a client role', async () => {
    renderAsRole('client')
    expect(await screen.findByText(/does not have permission to upload/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start recording/i })).not.toBeInTheDocument()
  })

  it('shows the recorder for a foreman (has AUDIO_UPLOAD)', async () => {
    renderAsRole('foreman')
    expect(await screen.findByRole('button', { name: /start recording/i })).toBeInTheDocument()
  })
})
