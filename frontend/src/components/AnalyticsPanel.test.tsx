import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AnalyticsPanel } from './AnalyticsPanel'
import * as endpoints from '../api/endpoints'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return { ...actual, getProjectAnalytics: vi.fn() }
})

beforeEach(() => {
  vi.mocked(endpoints.getProjectAnalytics).mockReset()
})

describe('AnalyticsPanel', () => {
  it('shows an empty-state message when no approved logs exist yet', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue({
      completion_trend: [],
      delay_frequency: [],
      logs_analyzed: 0,
    })
    render(<AnalyticsPanel projectId="proj-1" />)
    expect(await screen.findByText(/analytics will appear once/i)).toBeInTheDocument()
  })

  it('renders the "based on N approved log(s)" summary once data loads', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue({
      completion_trend: [
        { log_date: '2026-05-14', overall_project_completion_percent: 28 },
        { log_date: '2026-05-15', overall_project_completion_percent: 32 },
      ],
      delay_frequency: [],
      logs_analyzed: 2,
    })
    render(<AnalyticsPanel projectId="proj-1" />)
    expect(await screen.findByText(/based on 2 approved log/i)).toBeInTheDocument()
    expect(screen.getByText('Completion trend')).toBeInTheDocument()
  })

  it('renders the delay-frequency section only when there is delay data', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue({
      completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
      delay_frequency: [],
      logs_analyzed: 1,
    })
    render(<AnalyticsPanel projectId="proj-1" />)
    await screen.findByText(/based on 1 approved log/i)
    expect(screen.queryByText('Delay frequency')).not.toBeInTheDocument()
  })

  it('renders the delay-frequency chart when delays are present', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue({
      completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
      delay_frequency: [
        { delay_type: 'material_shortage', occurrence_count: 3, total_hours_lost: 6.5 },
        { delay_type: 'weather', occurrence_count: 1, total_hours_lost: 0 },
      ],
      logs_analyzed: 1,
    })
    render(<AnalyticsPanel projectId="proj-1" />)
    expect(await screen.findByText('Delay frequency')).toBeInTheDocument()
  })

  it('shows an error message if the analytics request fails', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockRejectedValue({
      isAxiosError: true,
      response: { status: 404, data: { message: 'Project not found.' } },
    })
    render(<AnalyticsPanel projectId="proj-1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/project not found/i)
  })

  it('re-fetches when projectId changes', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue({
      completion_trend: [],
      delay_frequency: [],
      logs_analyzed: 0,
    })
    const { rerender } = render(<AnalyticsPanel projectId="proj-1" />)
    await screen.findByText(/analytics will appear once/i)

    rerender(<AnalyticsPanel projectId="proj-2" />)
    expect(endpoints.getProjectAnalytics).toHaveBeenCalledWith('proj-1')
    expect(endpoints.getProjectAnalytics).toHaveBeenCalledWith('proj-2')
  })
})
