import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DocumentsPanel } from './DocumentsPanel'
import * as endpoints from '../api/endpoints'
import type { GenerationOutputRead } from '../api/types'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return {
    ...actual,
    listGenerationOutputs: vi.fn(),
    triggerGeneration: vi.fn(),
  }
})

function makeOutput(overrides: Partial<GenerationOutputRead> = {}) {
  return {
    id: 'out-1',
    daily_log_id: 'log-1',
    service_type: 'daily_report' as const,
    content: '## Daily Site Report\n\nWork completed today.',
    is_valid: true,
    is_sent: false,
    model: 'openai/gpt-oss-120b',
    tokens_used: 500,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.mocked(endpoints.listGenerationOutputs).mockReset()
  vi.mocked(endpoints.triggerGeneration).mockReset()
})

describe('DocumentsPanel', () => {
  it('shows "no documents" when the log has none yet', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([])
    render(<DocumentsPanel logId="log-1" />)
    expect(await screen.findByText(/no documents generated yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /generate documents/i })).toBeInTheDocument()
  })

  it('lists each generated document by its label', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'a', service_type: 'daily_report' }),
      makeOutput({ id: 'b', service_type: 'customer_update' }),
      makeOutput({ id: 'c', service_type: 'safety_talk' }),
      makeOutput({ id: 'd', service_type: 'material_reminder' }),
    ])
    render(<DocumentsPanel logId="log-1" />)

    expect(await screen.findByText('Daily Report')).toBeInTheDocument()
    expect(screen.getByText('Customer Update')).toBeInTheDocument()
    expect(screen.getByText('Safety Toolbox Talk')).toBeInTheDocument()
    expect(screen.getByText('Material Reminder')).toBeInTheDocument()
  })

  it('does not render a project_qa output as one of the 4 documents', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'q', service_type: 'project_qa' }),
    ])
    render(<DocumentsPanel logId="log-1" />)
    await waitFor(() => {
      expect(screen.queryByText(/no documents generated yet/i)).not.toBeInTheDocument()
    })
    // It still renders (nothing filters it from the list), but under its
    // own label — this test guards against silently dropping unknown
    // service types rather than mislabeling them.
    expect(screen.getByText('Q&A Answer')).toBeInTheDocument()
  })

  it('expands a document to show its content when clicked', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([makeOutput()])
    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" />)

    const header = await screen.findByText('Daily Report')
    expect(screen.queryByText(/work completed today/i)).not.toBeInTheDocument()

    await user.click(header)
    expect(screen.getByText(/work completed today/i)).toBeInTheDocument()
  })

  it('shows an "Invalid" badge for a failed-validation output', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ is_valid: false }),
    ])
    render(<DocumentsPanel logId="log-1" />)
    expect(await screen.findByText('Invalid')).toBeInTheDocument()
  })

  it('shows a "Sent" badge for an already-sent output', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ is_sent: true }),
    ])
    render(<DocumentsPanel logId="log-1" />)
    expect(await screen.findByText('Sent')).toBeInTheDocument()
  })

  it('calls triggerGeneration and reloads when "Generate documents" is clicked', async () => {
    vi.mocked(endpoints.listGenerationOutputs)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([makeOutput()])
    vi.mocked(endpoints.triggerGeneration).mockResolvedValue({
      daily_log_id: 'log-1',
      outputs_generated: 4,
      service_types: ['daily_report', 'customer_update', 'safety_talk', 'material_reminder'],
    })
    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" />)

    await screen.findByText(/no documents generated yet/i)
    await user.click(screen.getByRole('button', { name: /generate documents/i }))

    await waitFor(() => {
      expect(endpoints.triggerGeneration).toHaveBeenCalledWith('log-1')
    })
    expect(await screen.findByText('Daily Report')).toBeInTheDocument()
  })

  it('shows an error message if generation fails', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([])
    vi.mocked(endpoints.triggerGeneration).mockRejectedValue({
      isAxiosError: true,
      response: { status: 429, data: {} },
    })
    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" />)

    await screen.findByText(/no documents generated yet/i)
    await user.click(screen.getByRole('button', { name: /generate documents/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/too many attempts/i)
  })
})
