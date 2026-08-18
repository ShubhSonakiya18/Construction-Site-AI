import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { askProjectQuestion, listProjectDailyLogs } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import type { DailyLogSummary } from '../api/types'

const PROJECT_ID_STORAGE_KEY = 'csa_active_project_id'

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  under_review: 'Under review',
  approved: 'Approved',
  rejected: 'Rejected',
}

export function DashboardPage() {
  const [projectId, setProjectId] = useState(
    () => localStorage.getItem(PROJECT_ID_STORAGE_KEY) ?? '',
  )
  const [projectIdInput, setProjectIdInput] = useState(projectId)
  const [logs, setLogs] = useState<DailyLogSummary[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<string | null>(null)
  const [answerMeta, setAnswerMeta] = useState<{ logsUsed: number; model: string | null } | null>(
    null,
  )
  const [isAsking, setIsAsking] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)

  useEffect(() => {
    if (!projectId) return
    setIsLoading(true)
    setError(null)
    listProjectDailyLogs(projectId, statusFilter || undefined)
      .then(setLogs)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false))
  }, [projectId, statusFilter])

  function handleSetProject(e: FormEvent) {
    e.preventDefault()
    const trimmed = projectIdInput.trim()
    localStorage.setItem(PROJECT_ID_STORAGE_KEY, trimmed)
    setProjectId(trimmed)
  }

  async function handleAsk(e: FormEvent) {
    e.preventDefault()
    if (!projectId || !question.trim()) return
    setIsAsking(true)
    setAskError(null)
    setAnswer(null)
    try {
      const result = await askProjectQuestion(projectId, question.trim())
      setAnswer(result.answer)
      setAnswerMeta({ logsUsed: result.logs_used, model: result.model })
    } catch (err) {
      setAskError(extractErrorMessage(err))
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <div className="dashboard">
      <section className="card">
        <h2>Active project</h2>
        {/* No GET /projects listing endpoint exists yet (see
            docs/NEXT_SPRINT.md — full project CRUD deferred past Sprint 9)
            — a project id is entered directly rather than picked from a
            list, and remembered in localStorage for next visit. */}
        <form className="inline-form" onSubmit={handleSetProject}>
          <input
            type="text"
            placeholder="Project ID"
            value={projectIdInput}
            onChange={(e) => setProjectIdInput(e.target.value)}
          />
          <button type="submit" className="btn-secondary">
            Load
          </button>
        </form>
        {!projectId && (
          <p className="hint">Enter a project ID above to see its daily logs.</p>
        )}
      </section>

      {projectId && (
        <>
          <section className="card">
            <div className="card-header-row">
              <h2>Daily logs</h2>
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All statuses</option>
                <option value="draft">Draft</option>
                <option value="under_review">Under review</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>

            {error && (
              <div className="alert alert-error" role="alert">
                {error}
              </div>
            )}
            {isLoading && <p className="hint">Loading…</p>}
            {!isLoading && logs.length === 0 && !error && (
              <p className="hint">No daily logs found for this project.</p>
            )}

            <ul className="log-list">
              {logs.map((log) => (
                <li key={log.id} className="log-list-item">
                  <Link to={`/logs/${log.id}`} className="log-list-link">
                    <span className="log-date">{log.log_date}</span>
                    <span className="log-stage">{log.current_stage}</span>
                    <span className={`badge badge-${log.review_status}`}>
                      {STATUS_LABELS[log.review_status] ?? log.review_status}
                    </span>
                    <span className="log-workers">{log.total_workers_present} workers</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>

          <section className="card">
            <h2>Ask about this project</h2>
            <p className="hint">
              Answers are grounded in this project's recent approved daily logs only.
            </p>
            <form className="inline-form" onSubmit={(e) => void handleAsk(e)}>
              <input
                type="text"
                placeholder="e.g. Were there any delays this week?"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <button type="submit" className="btn-secondary" disabled={isAsking}>
                {isAsking ? 'Asking…' : 'Ask'}
              </button>
            </form>
            {askError && (
              <div className="alert alert-error" role="alert">
                {askError}
              </div>
            )}
            {answer && (
              <div className="answer-box">
                <p>{answer}</p>
                {answerMeta && (
                  <p className="hint">
                    Grounded in {answerMeta.logsUsed} log(s)
                    {answerMeta.model ? ` · ${answerMeta.model}` : ''}
                  </p>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
