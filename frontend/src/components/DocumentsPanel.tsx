import { useCallback, useEffect, useState } from 'react'
import { listGenerationOutputs, markOutputSent, triggerGeneration } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import type { GenerationOutputRead, ServiceType } from '../api/types'

// mark-sent is meaningful for any generated document, but "Preview and
// send" (docs/NEXT_SPRINT.md Deliverable 3) specifically names the
// customer-update email — the PM's own email client is where the actual
// send happens, this button only records that it did.
const SENDABLE_TYPES: ServiceType[] = ['customer_update']

const SERVICE_LABELS: Record<ServiceType, string> = {
  daily_report: 'Daily Report',
  customer_update: 'Customer Update',
  safety_talk: 'Safety Toolbox Talk',
  material_reminder: 'Material Reminder',
  project_qa: 'Q&A Answer',
}

// Sprint 5's four document-generating services, in the order the daily
// report / customer update / safety talk / material reminder are
// meaningfully read — project_qa is excluded, it's a per-question answer
// (Sprint 9), never one of the 4 documents /generate produces for a log.
const DOCUMENT_ORDER: ServiceType[] = [
  'daily_report',
  'customer_update',
  'safety_talk',
  'material_reminder',
]

export function DocumentsPanel({ logId }: { logId: string }) {
  const [outputs, setOutputs] = useState<GenerationOutputRead[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [sendingId, setSendingId] = useState<string | null>(null)

  const load = useCallback(() => {
    setIsLoading(true)
    setError(null)
    listGenerationOutputs(logId)
      .then(setOutputs)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false))
  }, [logId])

  useEffect(() => {
    load()
  }, [load])

  async function handleGenerate() {
    setIsGenerating(true)
    setError(null)
    try {
      await triggerGeneration(logId)
      load()
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsGenerating(false)
    }
  }

  async function handleMarkSent(outputId: string) {
    setSendingId(outputId)
    setError(null)
    try {
      const updated = await markOutputSent(logId, outputId)
      setOutputs((prev) => prev.map((o) => (o.id === updated.id ? updated : o)))
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setSendingId(null)
    }
  }

  const sorted = [...outputs].sort(
    (a, b) => DOCUMENT_ORDER.indexOf(a.service_type) - DOCUMENT_ORDER.indexOf(b.service_type),
  )

  return (
    <div className="card">
      <div className="card-header-row">
        <h2>Documents</h2>
        <button
          type="button"
          className="btn-secondary"
          disabled={isGenerating}
          onClick={() => void handleGenerate()}
        >
          {isGenerating ? 'Generating…' : outputs.length > 0 ? 'Regenerate' : 'Generate documents'}
        </button>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}
      {isLoading && <p className="hint">Loading…</p>}
      {!isLoading && outputs.length === 0 && !error && (
        <p className="hint">No documents generated yet for this log.</p>
      )}

      <ul className="document-list">
        {sorted.map((output) => (
          <li key={output.id} className="document-list-item">
            <button
              type="button"
              className="document-list-header"
              onClick={() => setExpandedId(expandedId === output.id ? null : output.id)}
              aria-expanded={expandedId === output.id}
            >
              <span>{SERVICE_LABELS[output.service_type] ?? output.service_type}</span>
              {!output.is_valid && <span className="badge badge-rejected">Invalid</span>}
              {output.is_sent && <span className="badge badge-approved">Sent</span>}
              <span className="document-toggle-icon">{expandedId === output.id ? '▾' : '▸'}</span>
            </button>
            {expandedId === output.id && (
              <div className="document-content">
                <pre>{output.content}</pre>
                {SENDABLE_TYPES.includes(output.service_type) && (
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={output.is_sent || sendingId === output.id}
                    onClick={() => void handleMarkSent(output.id)}
                  >
                    {output.is_sent
                      ? 'Sent'
                      : sendingId === output.id
                        ? 'Marking as sent…'
                        : 'Mark as sent'}
                  </button>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
