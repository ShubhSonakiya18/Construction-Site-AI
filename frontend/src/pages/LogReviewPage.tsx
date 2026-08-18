import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { approveDailyLog, getDailyLog, rejectDailyLog } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import type { DailyLogRead } from '../api/types'

// Sprint 8 RBAC (Permission.DAILY_LOG_APPROVE / DAILY_LOG_REJECT) is the
// real authorization boundary — the backend 403s a role without it
// regardless of what this page shows. Hiding the buttons here is a UX
// nicety (don't offer an action that will just fail), not the security
// control itself.
const REVIEWER_ROLES = new Set(['owner', 'admin', 'project_manager', 'system_admin'])

export function LogReviewPage() {
  const { logId } = useParams<{ logId: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [log, setLog] = useState<DailyLogRead | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rejectNotes, setRejectNotes] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const loadLog = useCallback(() => {
    if (!logId) return
    setIsLoading(true)
    setError(null)
    getDailyLog(logId)
      .then(setLog)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false))
  }, [logId])

  useEffect(() => {
    loadLog()
  }, [loadLog])

  async function handleApprove() {
    if (!logId) return
    setIsSubmitting(true)
    setError(null)
    try {
      const updated = await approveDailyLog(logId)
      setLog(updated)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleReject() {
    if (!logId || !rejectNotes.trim()) return
    setIsSubmitting(true)
    setError(null)
    try {
      const updated = await rejectDailyLog(logId, rejectNotes.trim())
      setLog(updated)
      setShowRejectForm(false)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) return <p className="hint">Loading…</p>
  if (error && !log) {
    return (
      <div className="card">
        <div className="alert alert-error">{error}</div>
        <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>
          Back
        </button>
      </div>
    )
  }
  if (!log) return null

  const canReview = REVIEWER_ROLES.has(user?.role ?? '') && log.review_status === 'under_review'

  return (
    <div className="log-review">
      <Link to="/" className="back-link">
        ← Back to dashboard
      </Link>

      <div className="card">
        <div className="card-header-row">
          <h1>Daily Log — {log.log_date}</h1>
          <span className={`badge badge-${log.review_status}`}>{log.review_status}</span>
        </div>
        <p>
          <strong>Stage:</strong> {log.current_stage}
          {log.overall_project_completion_percent != null &&
            ` · ${log.overall_project_completion_percent}% complete`}
        </p>
        <p>
          <strong>Workers present:</strong> {log.total_workers_present}
          {log.total_workers_scheduled != null && ` / ${log.total_workers_scheduled} scheduled`}
        </p>
        {log.safety_notes && (
          <p>
            <strong>Safety notes:</strong> {log.safety_notes}
          </p>
        )}
        {log.review_notes && (
          <p>
            <strong>Review notes:</strong> {log.review_notes}
          </p>
        )}
      </div>

      {log.trades_on_site.length > 0 && (
        <div className="card">
          <h2>Trades on site</h2>
          <ul>
            {log.trades_on_site.map((t) => (
              <li key={t.id}>
                {t.trade} — {t.workers_count} worker(s)
                {t.foreman_name ? ` (foreman: ${t.foreman_name})` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}

      {log.work_items.length > 0 && (
        <div className="card">
          <h2>Work completed</h2>
          <ul>
            {log.work_items.map((w) => (
              <li key={w.id}>
                {w.task_description}
                {w.quantity_completed != null &&
                  ` — ${w.quantity_completed} ${w.unit_of_measure ?? ''}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {log.delays.length > 0 && (
        <div className="card">
          <h2>Delays</h2>
          <ul>
            {log.delays.map((d) => (
              <li key={d.id}>
                {d.description}
                {d.hours_lost != null && ` — ${d.hours_lost}h lost`}
                {d.delay_resolved ? ' (resolved)' : ' (unresolved)'}
              </li>
            ))}
          </ul>
        </div>
      )}

      {log.safety_incidents.length > 0 && (
        <div className="card">
          <h2>Safety incidents</h2>
          <ul>
            {log.safety_incidents.map((s) => (
              <li key={s.id}>
                {s.incident_type}: {s.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      {canReview && (
        <div className="card">
          <h2>Review decision</h2>
          {error && <div className="alert alert-error">{error}</div>}
          {!showRejectForm ? (
            <div className="review-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={isSubmitting}
                onClick={() => void handleApprove()}
              >
                Approve
              </button>
              <button
                type="button"
                className="btn-danger"
                disabled={isSubmitting}
                onClick={() => setShowRejectForm(true)}
              >
                Reject
              </button>
            </div>
          ) : (
            <div className="review-actions">
              <label htmlFor="reject_notes">Reason for rejection (required)</label>
              <textarea
                id="reject_notes"
                value={rejectNotes}
                onChange={(e) => setRejectNotes(e.target.value)}
                rows={3}
                required
              />
              <div className="review-actions">
                <button
                  type="button"
                  className="btn-danger"
                  disabled={isSubmitting || !rejectNotes.trim()}
                  onClick={() => void handleReject()}
                >
                  Confirm rejection
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowRejectForm(false)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
