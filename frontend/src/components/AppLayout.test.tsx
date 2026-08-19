import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AppLayout } from './AppLayout'
import { AuthProvider } from '../auth/AuthContext'

function renderAsRole(role: string) {
  localStorage.setItem('csa_access_token', 'fake-token')
  localStorage.setItem('csa_refresh_token', 'fake-refresh')
  localStorage.setItem(
    'csa_user',
    JSON.stringify({ userId: 'u1', companyId: 'c1', email: 'a@b.com', role }),
  )
  return render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<div>Dashboard content</div>} />
            <Route path="/record" element={<div>Record content</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('AppLayout — Record nav gating (Sprint 10, Deliverable 7)', () => {
  it('shows the Record nav link for a project_manager', async () => {
    renderAsRole('project_manager')
    expect(await screen.findByRole('link', { name: 'Record' })).toBeInTheDocument()
  })

  it('shows the Record nav link for a foreman (has AUDIO_UPLOAD)', async () => {
    renderAsRole('foreman')
    expect(await screen.findByRole('link', { name: 'Record' })).toBeInTheDocument()
  })

  it('hides the Record nav link for a client', async () => {
    renderAsRole('client')
    await screen.findByText('Dashboard content')
    expect(screen.queryByRole('link', { name: 'Record' })).not.toBeInTheDocument()
  })

  it('hides the Record nav link for a safety_officer', async () => {
    renderAsRole('safety_officer')
    await screen.findByText('Dashboard content')
    expect(screen.queryByRole('link', { name: 'Record' })).not.toBeInTheDocument()
  })

  it('always shows the Dashboard nav link regardless of role', async () => {
    renderAsRole('client')
    expect(await screen.findByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  })
})
