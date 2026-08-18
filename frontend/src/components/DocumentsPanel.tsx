import { useCallback, useEffect, useState } from 'react'
import { listGenerationOutputs, triggerGeneration } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import type { GenerationOutputRead, ServiceType } from '../api/types'

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
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
