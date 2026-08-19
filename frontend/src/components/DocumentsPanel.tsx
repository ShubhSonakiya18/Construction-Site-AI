import { useCallback, useEffect, useState } from 'react'
import {
  downloadOutputPdf,
  listGenerationOutputs,
  markOutputSent,
  triggerGeneration,
} from '../api/endpoints'
import { extractBlobErrorMessage, extractErrorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { GENERATE_ROLES, SEND_OUTPUT_ROLES } from '../auth/roles'
import { MaterialReminderContent } from './MaterialReminderContent'
import type { GenerationOutputRead, ServiceType } from '../api/types'

// mark-sent is meaningful for any generated document, but "Preview and
// send" (docs/NEXT_SPRINT.md Deliverable 3) specifically names the
// customer-update email — the PM's own email client is where the actual
// send happens, this button only records that it did.
const SENDABLE_TYPES: ServiceType[] = ['customer_update']

// PDF export (Deliverable 4) is scoped to safety_talk only in this
// sprint — matches the backend's own 400 for any other type. See
// app/services/pdf_export.py's module docstring for why the renderer
// itself is generic even though only this one type has a button for it.
const PDF_EXPORTABLE_TYPES: ServiceType[] = ['safety_talk']

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

export function DocumentsPanel({ logId, logDate }: { logId: string; logDate: string }) {
  const { user } = useAuth()
  const canGenerate = GENERATE_ROLES.has(user?.role ?? '')
  const canSendOutput = SEND_OUTPUT_ROLES.has(user?.role ?? '')

  const [outputs, setOutputs] = useState<GenerationOutputRead[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [sendingId, setSendingId] = useState<string | null>(null)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)

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

  async function handleDownloadPdf(outputId: string) {
    setDownloadingId(outputId)
    setError(null)
    try {
      const blob = await downloadOutputPdf(logId, outputId)
      // The download itself: a temporary, invisible <a download> click —
      // the only reliable cross-browser way to save a Blob to disk from
      // JS without a server redirect. Revoke the object URL right after
      // to avoid leaking memory across repeated downloads in one session.
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `safety-talk-${logDate}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(await extractBlobErrorMessage(err))
    } finally {
      setDownloadingId(null)
    }
  }

  const sorted = [...outputs].sort(
    (a, b) => DOCUMENT_ORDER.indexOf(a.service_type) - DOCUMENT_ORDER.indexOf(b.service_type),
  )

  return (
    <div className="card">
      <div className="card-header-row">
        <h2>Documents</h2>
        {canGenerate && (
          <button
            type="button"
            className="btn-secondary"
            disabled={isGenerating}
            onClick={() => void handleGenerate()}
          >
            {isGenerating ? 'Generating…' : outputs.length > 0 ? 'Regenerate' : 'Generate documents'}
          </button>
        )}
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
                {output.service_type === 'material_reminder' ? (
                  <MaterialReminderContent content={output.content} />
                ) : (
                  <pre>{output.content}</pre>
                )}
                {canSendOutput && SENDABLE_TYPES.includes(output.service_type) && (
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
                {PDF_EXPORTABLE_TYPES.includes(output.service_type) && (
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={downloadingId === output.id}
                    onClick={() => void handleDownloadPdf(output.id)}
                  >
                    {downloadingId === output.id ? 'Downloading…' : 'Download PDF'}
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
