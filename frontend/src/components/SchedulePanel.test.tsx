import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SchedulePanel } from './SchedulePanel'
import * as endpoints from '../api/endpoints'
import type { ProjectScheduleResponseData } from '../api/types'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return { ...actual, getProjectSchedule: vi.fn(), createProjectSchedule: vi.fn() }
})

beforeEach(() => {
  vi.mocked(endpoints.getProjectSchedule).mockReset()
  vi.mocked(endpoints.createProjectSchedule).mockReset()
})

function makeSchedule(
  overrides: Partial<ProjectScheduleResponseData> = {},
): ProjectScheduleResponseData {
  return {
    schedule_id: 'sched-1',
    project_id: 'proj-1',
    schedule_start_date: '2026-03-10',
    critical_path_total_days: 108,
    projected_completion_date: '2026-06-26',
    tasks: [
      {
        id: 'task-1', stage_id: 'site_preparation', stage_label: 'Site Preparation',
        sequence_order: 0, planned_start_date: '2026-03-10', planned_end_date: '2026-03-15',
        planned_duration_days: 5, actual_start_date: null, actual_end_date: null,
        is_on_critical_path: true,
      },
      {
        id: 'task-2', stage_id: 'concrete_flatwork', stage_label: 'Concrete Flatwork',
        sequence_order: 2, planned_start_date: '2026-03-25', planned_end_date: '2026-03-30',
        planned_duration_days: 5, actual_start_date: '2026-03-26', actual_end_date: null,
        is_on_critical_path: false,
      },
    ],
    variance: [
      { stage_id: 'site_preparation', label: 'Site Preparation', status: 'behind', days_behind: 10, message: "You're 10 day(s) behind on site preparation." },
      { stage_id: 'concrete_flatwork', label: 'Concrete Flatwork', status: 'on_track', days_behind: 0, message: 'In progress, on schedule.' },
    ],
    delay_adjusted_completion_date: '2026-06-26',
    delay_impact_days: 0,
    ...overrides,
  }
}

describe('SchedulePanel', () => {
  it('shows a "create schedule" prompt when none exists yet', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(null)
    render(<SchedulePanel projectId="proj-1" />)
    expect(await screen.findByRole('button', { name: /create schedule/i })).toBeInTheDocument()
    expect(screen.getByText(/no schedule exists for this project yet/i)).toBeInTheDocument()
  })

  it('clicking "Create schedule" calls createProjectSchedule and renders the result', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(null)
    vi.mocked(endpoints.createProjectSchedule).mockResolvedValue(makeSchedule())
    render(<SchedulePanel projectId="proj-1" />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /create schedule/i }))

    expect(endpoints.createProjectSchedule).toHaveBeenCalledWith('proj-1')
    expect(await screen.findByText('2026-06-26')).toBeInTheDocument()
  })

  it('renders the projected completion date and critical path length once loaded', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(makeSchedule())
    render(<SchedulePanel projectId="proj-1" />)
    expect(await screen.findByText('2026-06-26')).toBeInTheDocument()
    expect(screen.getByText('108 days')).toBeInTheDocument()
  })

  it('renders the Gantt SVG with one row per task', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(makeSchedule())
    render(<SchedulePanel projectId="proj-1" />)
    await screen.findByText('108 days')
    expect(screen.getByRole('img', { name: /gantt chart/i })).toBeInTheDocument()
    expect(screen.getByText('Site Preparation')).toBeInTheDocument()
    expect(screen.getByText('Concrete Flatwork')).toBeInTheDocument()
  })

  it('lists behind-schedule tasks with their variance message', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(makeSchedule())
    render(<SchedulePanel projectId="proj-1" />)
    expect(await screen.findByText(/behind schedule/i)).toBeInTheDocument()
    expect(
      screen.getByText("You're 10 day(s) behind on site preparation."),
    ).toBeInTheDocument()
    // On-track tasks must not appear in the behind-schedule list.
    expect(screen.queryByText('In progress, on schedule.')).not.toBeInTheDocument()
  })

  it('does not show "Behind schedule" section when nothing is behind', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(
      makeSchedule({
        variance: [
          { stage_id: 'site_preparation', label: 'Site Preparation', status: 'on_track', days_behind: 0, message: 'In progress, on schedule.' },
        ],
      }),
    )
    render(<SchedulePanel projectId="proj-1" />)
    await screen.findByText('108 days')
    expect(screen.queryByText(/behind schedule/i)).not.toBeInTheDocument()
  })

  it('shows the delay-adjusted completion date only when a delay has pushed it out', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(
      makeSchedule({ delay_adjusted_completion_date: '2026-07-02', delay_impact_days: 6 }),
    )
    render(<SchedulePanel projectId="proj-1" />)
    expect(await screen.findByText(/2026-07-02 \(\+6d\)/)).toBeInTheDocument()
  })

  it('hides the delay-adjusted row when delay_impact_days is 0', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockResolvedValue(makeSchedule())
    render(<SchedulePanel projectId="proj-1" />)
    await screen.findByText('108 days')
    expect(screen.queryByText(/delay-adjusted completion/i)).not.toBeInTheDocument()
  })

  it('shows an error message if the schedule request fails', async () => {
    vi.mocked(endpoints.getProjectSchedule).mockRejectedValue({
      isAxiosError: true,
      response: { status: 500, data: { message: 'Something broke.' } },
    })
    render(<SchedulePanel projectId="proj-1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/something broke/i)
  })
})
