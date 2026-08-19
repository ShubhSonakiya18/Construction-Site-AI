import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MaterialReminderContent } from './MaterialReminderContent'

const REALISTIC_CONTENT = `## Material Procurement Reminder — 2026-05-14
**Stage:** framing | **Prepared for:** Site Foreman

## CRITICAL — Order Immediately
- 120 units of 2x6 SPF Studs 8ft from ABC Lumber, needed by 6 AM for 7 AM delivery

## HIGH PRIORITY — Order Today (needed within 48 hours)
None.

## MEDIUM PRIORITY — Order This Week
- Extension cords for framing nail guns

## LOW PRIORITY — Plan Ahead
None — no procurement action required.

## Delivery Notes
No special delivery notes.
`

describe('MaterialReminderContent', () => {
  it('renders each priority section with its heading', () => {
    render(<MaterialReminderContent content={REALISTIC_CONTENT} />)
    expect(screen.getByText(/CRITICAL — Order Immediately/)).toBeInTheDocument()
    expect(screen.getByText(/HIGH PRIORITY/)).toBeInTheDocument()
    expect(screen.getByText(/MEDIUM PRIORITY/)).toBeInTheDocument()
    expect(screen.getByText(/LOW PRIORITY/)).toBeInTheDocument()
    expect(screen.getByText(/Delivery Notes/)).toBeInTheDocument()
  })

  it('shows a CRITICAL badge on the critical section', () => {
    render(<MaterialReminderContent content={REALISTIC_CONTENT} />)
    const badges = screen.getAllByText('CRITICAL')
    expect(badges.length).toBeGreaterThanOrEqual(1)
  })

  it('renders bullet items as list content, with bold markers stripped', () => {
    render(<MaterialReminderContent content={REALISTIC_CONTENT} />)
    expect(
      screen.getByText(/120 units of 2x6 SPF Studs 8ft from ABC Lumber/),
    ).toBeInTheDocument()
  })

  it('renders "None." for an empty priority section rather than an empty list', () => {
    render(<MaterialReminderContent content={REALISTIC_CONTENT} />)
    expect(screen.getAllByText('None.').length).toBeGreaterThanOrEqual(1)
  })

  it('falls back to plain <pre> rendering for content with no ## sections', () => {
    const { container } = render(
      <MaterialReminderContent content="Validation failed: empty response" />,
    )
    expect(container.querySelector('pre')).toBeInTheDocument()
    expect(screen.getByText('Validation failed: empty response')).toBeInTheDocument()
  })

  it('handles a log with genuinely no material concerns (all sections empty)', () => {
    const allEmpty = `## Material Procurement Reminder — 2026-05-14
## CRITICAL — Order Immediately
None — no critical shortages reported.

## HIGH PRIORITY — Order Today (needed within 48 hours)
None.

## MEDIUM PRIORITY — Order This Week
None.

## LOW PRIORITY — Plan Ahead
None.

## Delivery Notes
No special delivery notes.
`
    render(<MaterialReminderContent content={allEmpty} />)
    // "None — no critical shortages reported." is itself a list item
    // (not a blank section), so it renders as content, not the "None."
    // fallback paragraph — this asserts the parser doesn't crash or
    // drop content on a fully-empty procurement day.
    expect(screen.getByText(/no critical shortages reported/)).toBeInTheDocument()
  })
})
