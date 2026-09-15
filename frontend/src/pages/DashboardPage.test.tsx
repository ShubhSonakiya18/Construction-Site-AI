import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { AuthProvider } from '../auth/AuthContext'
import { DashboardPage } from './DashboardPage'
import * as endpoints from '../api/endpoints'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return {
    ...actual,
    listProjects: vi.fn(),
    listProjectDailyLogs: vi.fn(),
  }
})

const PROJECT_A = {
  id: 'proj-a',
  company_id: 'c1',
  name: 'Project A',
  project_type: null,
  status: 'active',
  client_name: null,
  project_start_date: null,
  planned_completion_date: null,
  contract_value_usd: null,
  created_at: '2026-01-01T00:00:00Z',
}
const PROJECT_B = { ...PROJECT_A, id: 'proj-b', name: 'Project B' }

// DashboardPage renders AnalyticsPanel (Sprint 10), which reads the
// current user's role via useAuth() as of Sprint 13, Deliverable 5
// (ADR-056) -- needs an AuthProvider ancestor same as production's
// App.tsx provides. Role is irrelevant to this file's own assertions
// (project picker / daily-log list), so a fixed 'owner' user is enough.
function renderDashboard() {
  localStorage.setItem('csa_access_token', 'fake-token')
  localStorage.setItem('csa_refresh_token', 'fake-refresh')
  localStorage.setItem(
    'csa_user',
    JSON.stringify({ userId: 'u1', companyId: 'c1', email: 'a@b.com', role: 'owner' }),
  )
  return render(
    <MemoryRouter>
      <AuthProvider>
        <DashboardPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
  vi.mocked(endpoints.listProjects).mockReset()
  vi.mocked(endpoints.listProjectDailyLogs).mockReset().mockResolvedValue([])
})

describe('DashboardPage — project picker (Sprint 10)', () => {
  it('renders every fetched project as an option, and auto-selects the first', async () => {
    vi.mocked(endpoints.listProjects).mockResolvedValue([PROJECT_A, PROJECT_B])
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByRole('option', { name: 'Project A' })).toBeInTheDocument()
    })
    expect(screen.getByRole('option', { name: 'Project B' })).toBeInTheDocument()
    await waitFor(() => {
      expect(endpoints.listProjectDailyLogs).toHaveBeenCalledWith('proj-a', undefined)
    })
  })

  it('shows a message when the company has no projects', async () => {
    vi.mocked(endpoints.listProjects).mockResolvedValue([])
    renderDashboard()
    expect(await screen.findByText(/no projects found/i)).toBeInTheDocument()
  })

  it('falls back to the first project when the remembered id no longer exists', async () => {
    localStorage.setItem('csa_active_project_id', 'stale-deleted-project-id')
    vi.mocked(endpoints.listProjects).mockResolvedValue([PROJECT_A, PROJECT_B])
    renderDashboard()

    await waitFor(() => {
      expect(endpoints.listProjectDailyLogs).toHaveBeenCalledWith('proj-a', undefined)
    })
  })

  it('keeps the remembered project selected when it is still valid', async () => {
    localStorage.setItem('csa_active_project_id', 'proj-b')
    vi.mocked(endpoints.listProjects).mockResolvedValue([PROJECT_A, PROJECT_B])
    renderDashboard()

    await waitFor(() => {
      expect(endpoints.listProjectDailyLogs).toHaveBeenCalledWith('proj-b', undefined)
    })
  })

  it('shows an error if the project list fails to load', async () => {
    vi.mocked(endpoints.listProjects).mockRejectedValue({
      isAxiosError: true,
      response: { status: 500, data: { message: 'Server error.' } },
    })
    renderDashboard()
    expect(await screen.findByRole('alert')).toHaveTextContent(/server error/i)
  })
})
