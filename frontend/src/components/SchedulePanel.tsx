import { useEffect, useState } from 'react'
import { createProjectSchedule, getProjectSchedule } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'
import type { ProjectScheduleResponseData, ScheduleTaskRead } from '../api/types'

// Sprint 11, Deliverable 2: a hand-rolled SVG Gantt chart rather than a
// third-party library (frappe-gantt / gantt-task-react) — see ADR (Sprint
// 11, Deliverable 2 decision) for the full reasoning: a Gantt chart is
// fundamentally positioned horizontal bars against a shared date scale,
// which needs no dependency arrows or drag-to-reschedule for this
// sprint's read-only view, and hand-rolling keeps full control over
// styling to match the rest of this app (the way recharts already is for
// AnalyticsPanel, but a real Gantt is a different shape of chart than
// either of that panel's two).

const CRITICAL_COLOR = '#ef4444'
const NORMAL_COLOR = '#3b82f6'
const ACTUAL_COLOR = '#22c55e'
const ROW_HEIGHT = 28
const BAR_HEIGHT = 14
const LABEL_WIDTH = 180
const CHART_PADDING = 16

function parseDate(s: string): Date {
  return new Date(s + 'T00:00:00')
}

function daysBetween(a: Date, b: Date): number {
  return Math.round((b.getTime() - a.getTime()) / 86_400_000)
}

/** Renders the Gantt bars themselves — planned bars for every task, plus
 * a second, shorter actual-progress bar beneath any task that has
 * actual_start_date, so a viewer can see planned-vs-actual at a glance
 * without a legend explaining two different chart types. */
function GanttChart({ tasks }: { tasks: ScheduleTaskRead[] }) {
  if (tasks.length === 0) return null

  const allDates = tasks.flatMap((t) => [
    parseDate(t.planned_start_date),
    parseDate(t.planned_end_date),
    ...(t.actual_start_date ? [parseDate(t.actual_start_date)] : []),
    ...(t.actual_end_date ? [parseDate(t.actual_end_date)] : []),
  ])
  const minDate = new Date(Math.min(...allDates.map((d) => d.getTime())))
  const totalDays = Math.max(
    1,
    daysBetween(minDate, new Date(Math.max(...allDates.map((d) => d.getTime())))),
  )

  const chartWidth = 640
  const pxPerDay = chartWidth / totalDays
  const chartHeight = tasks.length * ROW_HEIGHT + CHART_PADDING * 2

  return (
    <div className="gantt-scroll">
      <svg
        role="img"
        aria-label="Project schedule Gantt chart"
        width={LABEL_WIDTH + chartWidth + CHART_PADDING * 2}
        height={chartHeight}
        style={{ display: 'block' }}
      >
        {tasks.map((task, i) => {
          const y = CHART_PADDING + i * ROW_HEIGHT
          const startOffset = daysBetween(minDate, parseDate(task.planned_start_date))
          const barWidth = Math.max(
            2,
            daysBetween(parseDate(task.planned_start_date), parseDate(task.planned_end_date)) *
              pxPerDay,
          )
          const barX = LABEL_WIDTH + CHART_PADDING + startOffset * pxPerDay
          const barColor = task.is_on_critical_path ? CRITICAL_COLOR : NORMAL_COLOR

          const actualBar =
            task.actual_start_date &&
            (() => {
              const actualStartOffset = daysBetween(minDate, parseDate(task.actual_start_date!))
              const actualEnd = task.actual_end_date
                ? parseDate(task.actual_end_date)
                : parseDate(task.actual_start_date!)
              const actualWidth = Math.max(
                2,
                daysBetween(parseDate(task.actual_start_date!), actualEnd) * pxPerDay || 4,
              )
              return (
                <rect
                  x={LABEL_WIDTH + CHART_PADDING + actualStartOffset * pxPerDay}
                  y={y + BAR_HEIGHT + 2}
                  width={actualWidth}
                  height={4}
                  rx={2}
                  fill={ACTUAL_COLOR}
                />
              )
            })()

          return (
            <g key={task.id}>
              <text
                x={0}
                y={y + BAR_HEIGHT / 2 + 4}
                fontSize={11}
                fill="var(--color-text)"
                style={{ fontFamily: 'inherit' }}
              >
                {task.stage_label.length > 24
                  ? task.stage_label.slice(0, 23) + '…'
                  : task.stage_label}
              </text>
              <rect
                x={barX}
                y={y}
                width={barWidth}
                height={BAR_HEIGHT}
                rx={3}
                fill={barColor}
                opacity={task.is_on_critical_path ? 1 : 0.75}
              />
              {actualBar}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export function SchedulePanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<ProjectScheduleResponseData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function load() {
    setIsLoading(true)
    setError(null)
    getProjectSchedule(projectId)
      .then(setData)
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setIsLoading(false))
  }

  useEffect(load, [projectId])

  async function handleCreate() {
    setIsCreating(true)
    setError(null)
    try {
      const schedule = await createProjectSchedule(projectId)
      setData(schedule)
    } catch (err) {
      setError(extractErrorMessage(err))
    } finally {
      setIsCreating(false)
    }
  }

  if (isLoading) {
    return (
      <section className="card">
        <h2>Schedule</h2>
        <p className="hint">Loading…</p>
      </section>
    )
  }

  if (!data) {
    return (
      <section className="card">
        <h2>Schedule</h2>
        <p className="hint">
          No schedule exists for this project yet. Creating one seeds a full task list from the
          standard residential-construction sequence, with planned dates and the critical path
          computed automatically.
        </p>
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}
        <button type="button" className="btn-primary" disabled={isCreating} onClick={() => void handleCreate()}>
          {isCreating ? 'Creating…' : 'Create schedule'}
        </button>
      </section>
    )
  }

  const behindTasks = data.variance.filter((v) => v.status === 'behind')
  const isDelayImpacted = data.delay_impact_days > 0

  return (
    <section className="card">
      <h2>Schedule</h2>
      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      <div className="schedule-summary">
        <div>
          <span className="hint">Projected completion</span>
          <p className="schedule-summary-value">{data.projected_completion_date}</p>
        </div>
        {isDelayImpacted && (
          <div>
            <span className="hint">Delay-adjusted completion</span>
            <p className="schedule-summary-value schedule-summary-delayed">
              {data.delay_adjusted_completion_date} (+{data.delay_impact_days}d)
            </p>
          </div>
        )}
        <div>
          <span className="hint">Critical path</span>
          <p className="schedule-summary-value">{data.critical_path_total_days} days</p>
        </div>
      </div>

      <div className="gantt-legend">
        <span>
          <i className="gantt-swatch" style={{ background: CRITICAL_COLOR }} /> Critical path
        </span>
        <span>
          <i className="gantt-swatch" style={{ background: NORMAL_COLOR, opacity: 0.75 }} /> Other
          tasks
        </span>
        <span>
          <i className="gantt-swatch gantt-swatch-thin" style={{ background: ACTUAL_COLOR }} />{' '}
          Actual progress
        </span>
      </div>

      <GanttChart tasks={data.tasks} />

      {behindTasks.length > 0 && (
        <div className="schedule-variance">
          <h3>Behind schedule</h3>
          <ul>
            {behindTasks.map((v) => (
              <li key={v.stage_id}>{v.message}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
