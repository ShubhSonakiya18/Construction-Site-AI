import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InventoryPanel } from './InventoryPanel'
import * as endpoints from '../api/endpoints'
import type { InventoryItemRead, ProjectInventoryResponseData } from '../api/types'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return {
    ...actual,
    getProjectInventory: vi.fn(),
    createPurchaseOrder: vi.fn(),
    updatePurchaseOrderStatus: vi.fn(),
  }
})

beforeEach(() => {
  vi.mocked(endpoints.getProjectInventory).mockReset()
  vi.mocked(endpoints.createPurchaseOrder).mockReset()
  vi.mocked(endpoints.updatePurchaseOrderStatus).mockReset()
})

function makeItem(overrides: Partial<InventoryItemRead> = {}): InventoryItemRead {
  return {
    id: 'item-1',
    project_id: 'proj-1',
    material_name: 'Cement bags',
    category: null,
    unit: 'bags',
    quantity_on_hand: 40,
    reorder_point: 10,
    typical_lead_time_days: null,
    preferred_supplier: null,
    applicable_stage_id: null,
    last_counted_at: null,
    purchase_orders: [],
    ...overrides,
  }
}

function makeResponse(
  overrides: Partial<ProjectInventoryResponseData> = {},
): ProjectInventoryResponseData {
  return {
    project_id: 'proj-1',
    items: [makeItem()],
    lead_time_warnings: [],
    ...overrides,
  }
}

describe('InventoryPanel', () => {
  it('shows an empty-state message when no materials are tracked yet', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(
      makeResponse({ items: [] }),
    )
    render(<InventoryPanel projectId="proj-1" />)
    expect(await screen.findByText(/no materials tracked yet/i)).toBeInTheDocument()
  })

  it('renders each item with its quantity and unit', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(makeResponse())
    render(<InventoryPanel projectId="proj-1" />)
    expect(await screen.findByText('Cement bags')).toBeInTheDocument()
    expect(screen.getByText('40 bags')).toBeInTheDocument()
  })

  it('shows a "Reorder now" badge when quantity is at or below reorder_point', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(
      makeResponse({ items: [makeItem({ quantity_on_hand: 5, reorder_point: 10 })] }),
    )
    render(<InventoryPanel projectId="proj-1" />)
    expect(await screen.findByText('Reorder now')).toBeInTheDocument()
  })

  it('shows an "OK" badge when quantity is comfortably above reorder_point', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(
      makeResponse({ items: [makeItem({ quantity_on_hand: 100, reorder_point: 10 })] }),
    )
    render(<InventoryPanel projectId="proj-1" />)
    expect(await screen.findByText('OK')).toBeInTheDocument()
  })

  it('shows "Not tracked" when reorder_point is unset', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(
      makeResponse({ items: [makeItem({ reorder_point: null })] }),
    )
    render(<InventoryPanel projectId="proj-1" />)
    expect(await screen.findByText('Not tracked')).toBeInTheDocument()
  })

  it('renders lead-time warnings when present', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(
      makeResponse({
        lead_time_warnings: [
          {
            material_name: 'Countertops', stage_id: 'cabinets_and_countertops',
            status: 'order_now', days_until_stage_start: 5,
            order_by_date: '2026-06-01',
            message: 'Order Countertops now — 21-day lead time, cabinets_and_countertops starts in 5 day(s).',
          },
        ],
      }),
    )
    render(<InventoryPanel projectId="proj-1" />)
    expect(await screen.findByText('Lead-time warnings')).toBeInTheDocument()
    expect(screen.getByText(/order countertops now/i)).toBeInTheDocument()
  })

  it('does not render a lead-time warnings section when there are none', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(makeResponse())
    render(<InventoryPanel projectId="proj-1" />)
    await screen.findByText('Cement bags')
    expect(screen.queryByText('Lead-time warnings')).not.toBeInTheDocument()
  })

  it('expanding an item reveals its purchase orders and the create-PO form', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(
      makeResponse({
        items: [makeItem({
          purchase_orders: [{
            id: 'po-1', inventory_item_id: 'item-1', status: 'draft',
            quantity_ordered: 20, unit_cost_usd: null, supplier: 'ABC Supply',
            auto_generated: true, ordered_at: null,
            expected_delivery_date: null, actual_delivery_date: null,
            notes: null, created_at: '2026-01-01T00:00:00Z',
          }],
        })],
      }),
    )
    render(<InventoryPanel projectId="proj-1" />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /cement bags/i }))

    expect(screen.getByText('ABC Supply')).toBeInTheDocument()
    expect(screen.getByText('(auto-suggested)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create purchase order/i })).toBeInTheDocument()
  })

  it('clicking "Mark as submitted" calls updatePurchaseOrderStatus with "submitted"', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(
      makeResponse({
        items: [makeItem({
          purchase_orders: [{
            id: 'po-1', inventory_item_id: 'item-1', status: 'draft',
            quantity_ordered: 20, unit_cost_usd: null, supplier: null,
            auto_generated: true, ordered_at: null,
            expected_delivery_date: null, actual_delivery_date: null,
            notes: null, created_at: '2026-01-01T00:00:00Z',
          }],
        })],
      }),
    )
    vi.mocked(endpoints.updatePurchaseOrderStatus).mockResolvedValue({
      id: 'po-1', inventory_item_id: 'item-1', status: 'submitted',
      quantity_ordered: 20, unit_cost_usd: null, supplier: null,
      auto_generated: true, ordered_at: '2026-01-02T00:00:00Z',
      expected_delivery_date: null, actual_delivery_date: null,
      notes: null, created_at: '2026-01-01T00:00:00Z',
    })
    render(<InventoryPanel projectId="proj-1" />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /cement bags/i }))
    await user.click(screen.getByRole('button', { name: /mark as submitted/i }))

    expect(endpoints.updatePurchaseOrderStatus).toHaveBeenCalledWith(
      'proj-1', 'item-1', 'po-1', 'submitted',
    )
  })

  it('submitting the create-PO form calls createPurchaseOrder with the entered quantity', async () => {
    vi.mocked(endpoints.getProjectInventory).mockResolvedValue(makeResponse())
    vi.mocked(endpoints.createPurchaseOrder).mockResolvedValue({
      id: 'po-2', inventory_item_id: 'item-1', status: 'draft',
      quantity_ordered: 30, unit_cost_usd: null, supplier: 'XYZ Co',
      auto_generated: false, ordered_at: null,
      expected_delivery_date: null, actual_delivery_date: null,
      notes: null, created_at: '2026-01-01T00:00:00Z',
    })
    render(<InventoryPanel projectId="proj-1" />)
    const user = userEvent.setup()

    await user.click(await screen.findByRole('button', { name: /cement bags/i }))
    await user.type(screen.getByPlaceholderText('Quantity'), '30')
    await user.type(screen.getByPlaceholderText(/supplier/i), 'XYZ Co')
    await user.click(screen.getByRole('button', { name: /create purchase order/i }))

    expect(endpoints.createPurchaseOrder).toHaveBeenCalledWith('proj-1', 'item-1', {
      quantity_ordered: 30,
      supplier: 'XYZ Co',
    })
  })

  it('shows an error message if the inventory request fails', async () => {
    vi.mocked(endpoints.getProjectInventory).mockRejectedValue({
      isAxiosError: true,
      response: { status: 500, data: { message: 'Something broke.' } },
    })
    render(<InventoryPanel projectId="proj-1" />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/something broke/i)
  })
})
