import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AnalyticsPanel } from './AnalyticsPanel'
import * as endpoints from '../api/endpoints'
import type { ProjectAnalyticsResponseData } from '../api/types'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return { ...actual, getProjectAnalytics: vi.fn() }
})

beforeEach(() => {
  vi.mocked(endpoints.getProjectAnalytics).mockReset()
})

function makeResponse(
  overrides: Partial<ProjectAnalyticsResponseData> = {},
): ProjectAnalyticsResponseData {
  return {
    completion_trend: [],
    delay_frequency: [],
    delay_frequency_by_trade: [],
    logs_analyzed: 0,
    projected_completion_date: null,
    delay_adjusted_completion_date: null,
    ...overrides,
  }
}

describe('AnalyticsPanel', () => {
  it('shows an empty-state message when no approved logs exist yet', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse())
    render(<AnalyticsPanel projectId="proj-1" />)
    expect(await screen.findByText(/analytics will appear once/i)).toBeInTheDocument()
  })

  it('renders the "based on N approved log(s)" summary once data loads', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
      completion_trend: [
        { log_date: '2026-05-14', overall_project_completion_percent: 28 },
        { log_date: '2026-05-15', overall_project_completion_percent: 32 },
      ],
      logs_analyzed: 2,
    }))
    render(<AnalyticsPanel projectId="proj-1" />)
    expect(await screen.findByText(/based on 2 approved log/i)).toBeInTheDocument()
    expect(screen.getByText('Completion trend')).toBeInTheDocument()
  })

  it('renders the delay-frequency section only when there is delay data', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
      completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
      logs_analyzed: 1,
    }))
    render(<AnalyticsPanel projectId="proj-1" />)
    await screen.findByText(/based on 1 approved log/i)
    expect(screen.queryByText('Delay frequency')).not.toBeInTheDocument()
  })

  it('renders the delay-frequency chart when delays are present', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
      completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
      delay_frequency: [
        { delay_type: 'material_shortage', occurrence_count: 3, total_hours_lost: 6.5 },
        { delay_type: 'weather', occurrence_count: 1, total_hours_lost: 0 },
      ],
      logs_analyzed: 1,
    }))
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
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse())
    const { rerender } = render(<AnalyticsPanel projectId="proj-1" />)
    await screen.findByText(/analytics will appear once/i)

    rerender(<AnalyticsPanel projectId="proj-2" />)
    expect(endpoints.getProjectAnalytics).toHaveBeenCalledWith('proj-1')
    expect(endpoints.getProjectAnalytics).toHaveBeenCalledWith('proj-2')
  })

  describe('projected completion (Sprint 13, Deliverable 1)', () => {
    it('shows no projection line when the project has no schedule yet', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      render(<AnalyticsPanel projectId="proj-1" />)
      await screen.findByText('Completion trend')
      expect(screen.queryByText(/planned completion/i)).not.toBeInTheDocument()
    })

    it('shows no delay-frequency-by-trade section when the array is empty', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      render(<AnalyticsPanel projectId="proj-1" />)
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Delay frequency by trade')).not.toBeInTheDocument()
    })

    it('renders the delay-frequency-by-trade chart when data is present', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        delay_frequency_by_trade: [
          { trade: 'electrical', delay_count: 2, total_hours_lost: 5 },
          { trade: 'framing', delay_count: 1, total_hours_lost: 2 },
        ],
      }))
      render(<AnalyticsPanel projectId="proj-1" />)
      expect(await screen.findByText('Delay frequency by trade')).toBeInTheDocument()
    })

    it('shows the planned completion date when a schedule exists', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        projected_completion_date: '2026-06-26',
      }))
      render(<AnalyticsPanel projectId="proj-1" />)
      expect(await screen.findByText(/planned completion: 2026-06-26/i)).toBeInTheDocument()
    })

    it('shows a separate delay-adjusted date only when it differs from the planned date', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        projected_completion_date: '2026-06-26',
        delay_adjusted_completion_date: '2026-07-02',
      }))
      render(<AnalyticsPanel projectId="proj-1" />)
      expect(await screen.findByText(/delay-adjusted: 2026-07-02/i)).toBeInTheDocument()
    })

    it('does not repeat the date when delay_adjusted_completion_date equals projected_completion_date', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        projected_completion_date: '2026-06-26',
        delay_adjusted_completion_date: '2026-06-26',
      }))
      render(<AnalyticsPanel projectId="proj-1" />)
      await screen.findByText(/planned completion: 2026-06-26/i)
      expect(screen.queryByText(/delay-adjusted/i)).not.toBeInTheDocument()
    })
  })
})
