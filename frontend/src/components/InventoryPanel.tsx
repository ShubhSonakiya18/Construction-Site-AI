import { useEffect, useState, type FormEvent } from 'react'
import {
  createPurchaseOrder,
  getProjectInventory,
  updatePurchaseOrderStatus,
} from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import type { InventoryItemRead, ProjectInventoryResponseData } from '../api/types'

// Sprint 12, Deliverable 5: a dedicated panel rather than extending
// SchedulePanel.tsx — inventory has its own create-a-purchase-order
// interaction and a per-item expand/collapse for purchase-order history,
// which don't fit naturally into the Gantt chart's read-only layout. The
// two panels sit next to each other on the Dashboard instead, each doing
// one job well, matching how AnalyticsPanel and SchedulePanel are
// already two separate cards rather than one combined component.
//
// Reorder-point status badges reuse the existing badge-draft/
// badge-under_review/badge-rejected color classes MaterialReminderContent.tsx
// already established for priority levels (red/amber/gray) — same visual
// language, not a new one.

function reorderBadgeClass(item: InventoryItemRead): string {
  if (item.reorder_point == null) return 'badge-draft'
  if (item.quantity_on_hand <= item.reorder_point) return 'badge-rejected'
  if (item.quantity_on_hand <= item.reorder_point * 1.5) return 'badge-under_review'
  return 'badge-approved'
}

function reorderBadgeLabel(item: InventoryItemRead): string {
  if (item.reorder_point == null) return 'Not tracked'
  if (item.quantity_on_hand <= item.reorder_point) return 'Reorder now'
  if (item.quantity_on_hand <= item.reorder_point * 1.5) return 'Low'
  return 'OK'
}

function PurchaseOrderRow({
  po,
  onSubmit,
  isUpdating,
}: {
  po: InventoryItemRead['purchase_orders'][number]
  onSubmit: () => void
  isUpdating: boolean
}) {
  return (
    <li className="po-row">
      <span className={`badge badge-${po.status === 'draft' ? 'draft' : po.status === 'cancelled' ? 'rejected' : 'approved'}`}>
        {po.status}
      </span>
      <span>{po.quantity_ordered} units</span>
      {po.supplier && <span className="hint">{po.supplier}</span>}
      {po.auto_generated && <span className="hint">(auto-suggested)</span>}
      {po.status === 'draft' && (
        <button
          type="button"
          className="btn-link"
          disabled={isUpdating}
          onClick={onSubmit}
        >
          {isUpdating ? 'Submitting…' : 'Mark as submitted'}
        </button>
      )}
    </li>
  )
}

function CreatePurchaseOrderForm({
  onCreate,
}: {
  onCreate: (quantity: number, supplier: string) => Promise<void>
}) {
  const [quantity, setQuantity] = useState('')
  const [supplier, setSupplier] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const qty = Number(quantity)
    if (!qty || qty <= 0) return
    setIsCreating(true)
    try {
      await onCreate(qty, supplier)
      setQuantity('')
      setSupplier('')
    } finally {
      setIsCreating(false)
    }
  }

  return (
    <form className="inline-form" onSubmit={(e) => void handleSubmit(e)}>
      <input
        type="number"
        min="1"
        step="1"
        placeholder="Quantity"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        required
      />
      <input
        type="text"
        placeholder="Supplier (optional)"
        value={supplier}
        onChange={(e) => setSupplier(e.target.value)}
      />
      <button type="submit" className="btn-secondary" disabled={isCreating}>
        {isCreating ? 'Creating…' : 'Create purchase order'}
      </button>
    </form>
  )
}

export function InventoryPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<ProjectInventoryResponseData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [updatingPoId, setUpdatingPoId] = useState<string | null>(null)

  function load() {
    setIsLoading(true)
    setError(null)
    getProjectInventory(projectId)
      .then(setData)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false))
  }

  useEffect(load, [projectId])

  async function handleCreatePurchaseOrder(
    itemId: string,
    quantity: number,
    supplier: string,
  ) {
    setError(null)
    try {
      await createPurchaseOrder(projectId, itemId, {
        quantity_ordered: quantity,
        supplier: supplier || undefined,
      })
      load()
    } catch (err) {
      setError(extractErrorMessage(err))
    }
  }

  async function handleSubmitPurchaseOrder(itemId: string, poId: string) {
    setUpdatingPoId(poId)
    setError(null)
    try {
      await updatePurchaseOrderStatus(projectId, itemId, poId, 'submitted')
      load()
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setUpdatingPoId(null)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <h2>Inventory</h2>
        <p className="hint">Loading…</p>
      </section>
    )
  }

  if (error && !data) {
    return (
      <section className="card">
        <h2>Inventory</h2>
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      </section>
    )
  }

  if (!data || data.items.length === 0) {
    return (
      <section className="card">
        <h2>Inventory</h2>
        <p className="hint">
          No materials tracked yet — inventory items are created automatically the first time a
          material appears in an approved daily log.
        </p>
      </section>
    )
  }

  return (
    <section className="card">
      <h2>Inventory</h2>
      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {data.lead_time_warnings.length > 0 && (
        <div className="inventory-warnings">
          <h3>Lead-time warnings</h3>
          <ul>
            {data.lead_time_warnings.map((w) => (
              <li key={`${w.material_name}-${w.stage_id}`}>{w.message}</li>
            ))}
          </ul>
        </div>
      )}

      <ul className="inventory-list">
        {data.items.map((item) => {
          const isExpanded = expandedId === item.id
          return (
            <li key={item.id} className="inventory-item">
              <button
                type="button"
                className="inventory-item-header"
                onClick={() => setExpandedId(isExpanded ? null : item.id)}
                aria-expanded={isExpanded}
              >
                <span>{isExpanded ? '▾' : '▸'}</span>
                <span className="inventory-item-name">{item.material_name}</span>
                <span className="inventory-item-qty">
                  {item.quantity_on_hand} {item.unit}
                </span>
                <span className={`badge ${reorderBadgeClass(item)}`}>
                  {reorderBadgeLabel(item)}
                </span>
              </button>

              {isExpanded && (
                <div className="inventory-item-detail">
                  {item.purchase_orders.length > 0 && (
                    <ul className="po-list">
                      {item.purchase_orders.map((po) => (
                        <PurchaseOrderRow
                          key={po.id}
                          po={po}
                          isUpdating={updatingPoId === po.id}
                          onSubmit={() => void handleSubmitPurchaseOrder(item.id, po.id)}
                        />
                      ))}
                    </ul>
                  )}
                  <CreatePurchaseOrderForm
                    onCreate={(qty, supplier) =>
                      handleCreatePurchaseOrder(item.id, qty, supplier)
                    }
                  />
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
