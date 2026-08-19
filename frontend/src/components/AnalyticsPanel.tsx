import { useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getProjectAnalytics } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import type { ProjectAnalyticsResponseData } from '../api/types'

// Sprint 10, Deliverable 6: completion trend + delay frequency, per
// docs/NEXT_SPRINT.md — "a simple chart... showing these two trends for
// the active project." Both series come from GET /projects/{id}/analytics,
// which only counts approved logs (the same trust boundary the grounded
// Q&A feature applies).
const CHART_COLOR = '#3b82f6'
const DELAY_BAR_COLOR = '#f59e0b'

export function AnalyticsPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<ProjectAnalyticsResponseData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setIsLoading(true)
    setError(null)
    getProjectAnalytics(projectId)
      .then(setData)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false))
  }, [projectId])

  if (isLoading) {
    return (
      <section className="card">
        <h2>Analytics</h2>
        <p className="hint">Loading…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="card">
        <h2>Analytics</h2>
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      </section>
    )
  }

  if (!data || data.logs_analyzed === 0) {
    return (
      <section className="card">
        <h2>Analytics</h2>
        <p className="hint">
          No approved daily logs yet for this project — analytics will appear once at least one
          log is approved.
        </p>
      </section>
    )
  }

  // recharts' XAxis/Tooltip render fine with the completion percent
  // possibly null (a log that never recorded one) — the line simply
  // gaps there rather than crashing, which is the correct behavior for
  // an optional field.
  const trendData = data.completion_trend.map((p) => ({
    date: p.log_date,
    completion: p.overall_project_completion_percent,
  }))
  const delayData = data.delay_frequency.map((d) => ({
    type: d.delay_type,
    hours: d.total_hours_lost,
    count: d.occurrence_count,
  }))

  return (
    <section className="card">
      <h2>Analytics</h2>
      <p className="hint">Based on {data.logs_analyzed} approved log(s).</p>

      <div className="analytics-chart">
        <h3>Completion trend</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={trendData} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 12 }} />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: '#94a3b8', fontSize: 12 }}
              label={{ value: '%', fill: '#94a3b8', position: 'insideLeft' }}
            />
            <Tooltip
              contentStyle={{ background: '#273549', border: '1px solid #334155' }}
              labelStyle={{ color: '#f1f5f9' }}
            />
            <Line
              type="monotone"
              dataKey="completion"
              stroke={CHART_COLOR}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
              name="Completion %"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {delayData.length > 0 && (
        <div className="analytics-chart">
          <h3>Delay frequency</h3>
          <ResponsiveContainer width="100%" height={Math.max(180, delayData.length * 40)}>
            <BarChart
              data={delayData}
              layout="vertical"
              margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="type"
                width={140}
                tick={{ fill: '#94a3b8', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: '#273549', border: '1px solid #334155' }}
                labelStyle={{ color: '#f1f5f9' }}
              />
              <Bar dataKey="count" fill={DELAY_BAR_COLOR} name="Occurrences" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
