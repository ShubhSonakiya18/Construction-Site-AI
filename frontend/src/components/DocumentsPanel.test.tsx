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
    markOutputSent: vi.fn(),
    downloadOutputPdf: vi.fn(),
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
  vi.mocked(endpoints.markOutputSent).mockReset()
  vi.mocked(endpoints.downloadOutputPdf).mockReset()
})

describe('DocumentsPanel', () => {
  it('shows "no documents" when the log has none yet', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([])
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)
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
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    expect(await screen.findByText('Daily Report')).toBeInTheDocument()
    expect(screen.getByText('Customer Update')).toBeInTheDocument()
    expect(screen.getByText('Safety Toolbox Talk')).toBeInTheDocument()
    expect(screen.getByText('Material Reminder')).toBeInTheDocument()
  })

  it('does not render a project_qa output as one of the 4 documents', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'q', service_type: 'project_qa' }),
    ])
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)
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
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    const header = await screen.findByText('Daily Report')
    expect(screen.queryByText(/work completed today/i)).not.toBeInTheDocument()

    await user.click(header)
    expect(screen.getByText(/work completed today/i)).toBeInTheDocument()
  })

  it('shows an "Invalid" badge for a failed-validation output', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ is_valid: false }),
    ])
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)
    expect(await screen.findByText('Invalid')).toBeInTheDocument()
  })

  it('shows a "Sent" badge for an already-sent output', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ is_sent: true }),
    ])
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)
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
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

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
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await screen.findByText(/no documents generated yet/i)
    await user.click(screen.getByRole('button', { name: /generate documents/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/too many attempts/i)
  })
})

describe('DocumentsPanel — mark as sent (Sprint 10)', () => {
  it('shows a "Mark as sent" button only for the customer_update document', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'a', service_type: 'daily_report' }),
      makeOutput({ id: 'b', service_type: 'customer_update' }),
    ])
    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await user.click(await screen.findByText('Daily Report'))
    expect(screen.queryByRole('button', { name: /mark as sent/i })).not.toBeInTheDocument()

    await user.click(screen.getByText('Customer Update'))
    expect(screen.getByRole('button', { name: /mark as sent/i })).toBeInTheDocument()
  })

  it('calls markOutputSent and shows the "Sent" badge on success', async () => {
    const unsent = makeOutput({ id: 'b', service_type: 'customer_update', is_sent: false })
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([unsent])
    vi.mocked(endpoints.markOutputSent).mockResolvedValue({ ...unsent, is_sent: true })

    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await user.click(await screen.findByText('Customer Update'))
    await user.click(screen.getByRole('button', { name: /mark as sent/i }))

    await waitFor(() => {
      expect(endpoints.markOutputSent).toHaveBeenCalledWith('log-1', 'b')
    })
    // Both the header's "Sent" badge and the button read "Sent" once
    // marked — scope to the button specifically to avoid ambiguity.
    expect(await screen.findByRole('button', { name: 'Sent' })).toBeDisabled()
    expect(screen.getAllByText('Sent').length).toBeGreaterThanOrEqual(1)
  })

  it('an already-sent document shows a disabled "Sent" button, not "Mark as sent"', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'b', service_type: 'customer_update', is_sent: true }),
    ])
    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await user.click(await screen.findByText('Customer Update'))
    const button = screen.getByRole('button', { name: 'Sent' })
    expect(button).toBeDisabled()
  })

  it('shows an error if marking as sent fails', async () => {
    const unsent = makeOutput({ id: 'b', service_type: 'customer_update', is_sent: false })
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([unsent])
    vi.mocked(endpoints.markOutputSent).mockRejectedValue({
      isAxiosError: true,
      response: { status: 404, data: { message: 'Generated document not found for this log.' } },
    })

    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await user.click(await screen.findByText('Customer Update'))
    await user.click(screen.getByRole('button', { name: /mark as sent/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/not found for this log/i)
  })
})

describe('DocumentsPanel — PDF export (Sprint 10)', () => {
  // jsdom does not implement URL.createObjectURL/revokeObjectURL — the
  // download flow (DocumentsPanel.tsx's handleDownloadPdf) needs them to
  // exist to run at all, so they're stubbed for this describe block only.
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:mock-url')
    URL.revokeObjectURL = vi.fn()
  })

  it('shows a "Download PDF" button only for the safety_talk document', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'a', service_type: 'daily_report' }),
      makeOutput({ id: 'c', service_type: 'safety_talk' }),
    ])
    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await user.click(await screen.findByText('Daily Report'))
    expect(screen.queryByRole('button', { name: /download pdf/i })).not.toBeInTheDocument()

    await user.click(screen.getByText('Safety Toolbox Talk'))
    expect(screen.getByRole('button', { name: /download pdf/i })).toBeInTheDocument()
  })

  it('calls downloadOutputPdf and triggers a browser download on success', async () => {
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'c', service_type: 'safety_talk' }),
    ])
    vi.mocked(endpoints.downloadOutputPdf).mockResolvedValue(
      new Blob(['%PDF-fake'], { type: 'application/pdf' }),
    )
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await user.click(await screen.findByText('Safety Toolbox Talk'))
    await user.click(screen.getByRole('button', { name: /download pdf/i }))

    await waitFor(() => {
      expect(endpoints.downloadOutputPdf).toHaveBeenCalledWith('log-1', 'c')
    })
    expect(clickSpy).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
    clickSpy.mockRestore()
  })

  it('shows the backend error message if the PDF export is rejected, reading a Blob-shaped error body', async () => {
    // The endpoint uses responseType: 'blob', so even a 400/404 error
    // response arrives as a Blob, not parsed JSON — this is the case
    // extractBlobErrorMessage() exists for. Simulated here even though
    // the button is only shown for safety_talk (matching the backend's
    // own scoping), since a stale UI state could still hit this path.
    vi.mocked(endpoints.listGenerationOutputs).mockResolvedValue([
      makeOutput({ id: 'c', service_type: 'safety_talk' }),
    ])
    vi.mocked(endpoints.downloadOutputPdf).mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 400,
        data: new Blob(
          [JSON.stringify({ message: "PDF export is only available for safety_talk documents in this sprint (got 'daily_report')." })],
          { type: 'application/json' },
        ),
      },
    })

    const user = userEvent.setup()
    render(<DocumentsPanel logId="log-1" logDate="2026-05-14" />)

    await user.click(await screen.findByText('Safety Toolbox Talk'))
    await user.click(screen.getByRole('button', { name: /download pdf/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/only available for safety_talk/i)
  })
})
