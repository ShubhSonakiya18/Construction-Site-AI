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
import { useAuth } from '../auth/AuthContext'
import { STAFF_ONLY_ANALYTICS_ROLES } from '../auth/roles'
import type { ProjectAnalyticsResponseData } from '../api/types'

// Sprint 10, Deliverable 6: completion trend + delay frequency, per
// docs/NEXT_SPRINT.md — "a simple chart... showing these two trends for
// the active project." Both series come from GET /projects/{id}/analytics,
// which only counts approved logs (the same trust boundary the grounded
// Q&A feature applies).
const CHART_COLOR = '#3b82f6'
const DELAY_BAR_COLOR = '#f59e0b'
// Safety gets its own scale, distinct from the amber delay bars: an
// incident is a different kind of event than a schedule delay, and
// OSHA-recordable is a severity signal within it, not just a second
// series.
const INCIDENT_COLOR = '#94a3b8'
const OSHA_COLOR = '#ef4444'
// Cost gets its own hue again — money is a different axis from both
// schedule delays (amber) and safety (red/grey), and the cumulative
// line needs to read as distinct from the per-day bars.
const COST_DAILY_COLOR = '#22c55e'
const COST_CUMULATIVE_COLOR = '#3b82f6'

const BUDGET_STATUS_LABELS: Record<string, string> = {
  on_track: 'On track',
  approaching_budget: 'Approaching budget',
  over_budget: 'Over budget',
  no_budget_set: 'No contract value set',
}

function formatUsd(value: number | null): string {
  if (value === null) return '—'
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

export function AnalyticsPanel({ projectId }: { projectId: string }) {
  const { user } = useAuth()
  const isStaffView = STAFF_ONLY_ANALYTICS_ROLES.has(user?.role ?? '')
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
  // Sprint 13's four new array fields default to [] server-side
  // (Field(default_factory=list) in ProjectAnalyticsResponseData), but
  // ?? [] guards the render against any response that omits them
  // anyway -- a missing field here would otherwise throw on .map() and
  // take down the whole dashboard (not just this card), since nothing
  // above this line renders anything that could catch it.
  const delayByTradeData = (data.delay_frequency_by_trade ?? []).map((d) => ({
    trade: d.trade,
    hours: d.total_hours_lost,
    count: d.delay_count,
  }))
  const safetyTrendData = (data.safety_incident_trend ?? []).map((s) => ({
    date: s.log_date,
    incidents: s.incident_count,
    osha: s.osha_recordable_count,
  }))
  const safetyBreakdownData = (data.safety_incident_breakdown ?? []).map((s) => ({
    type: s.incident_type,
    incidents: s.incident_count,
    osha: s.osha_recordable_count,
  }))
  const totalIncidents = safetyBreakdownData.reduce(
    (sum, s) => sum + s.incidents,
    0,
  )
  const totalOshaRecordable = safetyBreakdownData.reduce(
    (sum, s) => sum + s.osha,
    0,
  )
  const costTrendData = (data.daily_cost_trend ?? []).map((c) => ({
    date: c.log_date,
    daily: c.daily_total_cost_usd,
    cumulative: c.cumulative_spend_to_date_usd,
  }))
  const changeOrderData = data.change_order_summary ?? []
  const budget = data.budget_variance
  const evm = data.earned_value
  const costEstimate = data.cost_estimate
  const safety = data.safety_proactive_warnings
  const productivityData = (data.productivity_by_stage_trade ?? []).map((p) => ({
    label: `${p.current_stage} / ${p.trade}`,
    completion: p.avg_task_completion_percent,
    count: p.work_item_count,
  }))

  return (
    <section className="card">
      <h2>Analytics</h2>
      <p className="hint">Based on {data.logs_analyzed} approved log(s).</p>

      <div className="analytics-chart">
        <h3>Completion trend</h3>
        {(data.projected_completion_date || data.delay_adjusted_completion_date) && (
          <p className="hint analytics-projection">
            {data.projected_completion_date && (
              <span>Planned completion: {data.projected_completion_date}</span>
            )}
            {data.delay_adjusted_completion_date &&
              data.delay_adjusted_completion_date !== data.projected_completion_date && (
                <span className="analytics-projection-delayed">
                  {' '}
                  · delay-adjusted: {data.delay_adjusted_completion_date}
                </span>
              )}
          </p>
        )}
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

      {isStaffView && delayByTradeData.length > 0 && (
        <div className="analytics-chart">
          <h3>Delay frequency by trade</h3>
          <p className="hint">
            Trades on site the day a delay happened — not a claim that the delay blocked that
            trade's own work.
          </p>
          <ResponsiveContainer width="100%" height={Math.max(180, delayByTradeData.length * 40)}>
            <BarChart
              data={delayByTradeData}
              layout="vertical"
              margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} />
              <YAxis
                type="category"
                dataKey="trade"
                width={140}
                tick={{ fill: '#94a3b8', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: '#273549', border: '1px solid #334155' }}
                labelStyle={{ color: '#f1f5f9' }}
              />
              <Bar dataKey="count" fill={DELAY_BAR_COLOR} name="Delays" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {isStaffView && (
      <div className="analytics-chart">
        <h3>Safety incidents</h3>
        {totalIncidents === 0 ? (
          // Unlike an empty delay chart, zero incidents is itself a
          // meaningful result worth stating -- an absent section would
          // read as "not tracked" rather than "none recorded".
          <p className="hint">
            No safety incidents recorded on this project's approved logs.
          </p>
        ) : (
          <>
            <p className="hint analytics-safety-summary">
              {totalIncidents} incident(s) recorded
              {totalOshaRecordable > 0 && (
                <span className="analytics-safety-osha">
                  {' '}
                  · {totalOshaRecordable} OSHA-recordable
                </span>
              )}
            </p>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart
                data={safetyTrendData}
                margin={{ top: 8, right: 16, left: -16, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis allowDecimals={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#273549', border: '1px solid #334155' }}
                  labelStyle={{ color: '#f1f5f9' }}
                />
                <Line
                  type="monotone"
                  dataKey="incidents"
                  stroke={INCIDENT_COLOR}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Incidents"
                />
                <Line
                  type="monotone"
                  dataKey="osha"
                  stroke={OSHA_COLOR}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="OSHA-recordable"
                />
              </LineChart>
            </ResponsiveContainer>

            <ResponsiveContainer
              width="100%"
              height={Math.max(180, safetyBreakdownData.length * 40)}
            >
              <BarChart
                data={safetyBreakdownData}
                layout="vertical"
                margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis type="number" allowDecimals={false} tick={{ fill: '#94a3b8', fontSize: 12 }} />
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
                <Bar dataKey="incidents" fill={INCIDENT_COLOR} name="Incidents" />
                <Bar dataKey="osha" fill={OSHA_COLOR} name="OSHA-recordable" />
              </BarChart>
            </ResponsiveContainer>
          </>
        )}
      </div>
      )}

      {/* Sprint 15, Deliverable 4 (ADR-063): computed read-time
          warnings, not a pushed notification -- recomputed on every
          load, same pattern as Sprint 11's schedule variance. */}
      {isStaffView && safety && (
        <div className="analytics-chart">
          <h3>Safety status</h3>
          <p className="hint">
            {safety.days_since_last_incident === null
              ? 'No safety incidents on record.'
              : safety.days_since_last_incident === 0
                ? 'An incident was recorded today.'
                : `${safety.days_since_last_incident} day(s) since the last recorded incident.`}
            {safety.incidence_rate_per_200k_hours !== null ? (
              <> {' '}· OSHA incidence rate: {safety.incidence_rate_per_200k_hours} per 100 workers/year.</>
            ) : (
              safety.incidence_rate_unavailable_reason && (
                <> {' '}· Incidence rate unavailable ({safety.incidence_rate_unavailable_reason}).</>
              )
            )}
          </p>

          {safety.unresolved_hazards.length === 0 ? (
            <p className="hint">No unresolved hazards.</p>
          ) : (
            <ul className="analytics-hazard-list">
              {safety.unresolved_hazards.map((h, i) => (
                <li key={i} className={`analytics-hazard-${h.severity}`}>
                  <span className="analytics-hazard-severity">{h.severity}</span>
                  {' '}— {h.hazard_type.replace(/_/g, ' ')}: {h.description}
                  {' '}<span className="hint">({h.days_open} day(s) open)</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {productivityData.length > 0 && (
        <div className="analytics-chart">
          <h3>Average reported completion by stage / trade</h3>
          <p className="hint">
            Average task_completion_percent logged per stage/trade pair — not a comparison
            against a planned rate, and a low average may just mean work was still in progress
            when logged. Hover a bar for its sample size.
          </p>
          <ResponsiveContainer width="100%" height={Math.max(180, productivityData.length * 40)}>
            <BarChart
              data={productivityData}
              layout="vertical"
              margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                type="number"
                domain={[0, 100]}
                tick={{ fill: '#94a3b8', fontSize: 12 }}
              />
              <YAxis
                type="category"
                dataKey="label"
                width={160}
                tick={{ fill: '#94a3b8', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{ background: '#273549', border: '1px solid #334155' }}
                labelStyle={{ color: '#f1f5f9' }}
                formatter={(value, name, props) => {
                  if (name === 'Avg completion %') {
                    const count = (props.payload as { count: number }).count
                    return [`${value}% (${count} work item(s))`, name]
                  }
                  return [value ?? '', name]
                }}
              />
              <Bar dataKey="completion" fill={CHART_COLOR} name="Avg completion %" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Cost (Sprint 14). Staff-only for the same reason ADR-056 gates
          safety and delay-by-trade: a GC's internal cost breakdown and
          remaining margin are not a client's business, even though the
          client can see the schedule progress those costs produced. */}
      {isStaffView && budget && (
        <div className="analytics-chart">
          <h3>Cost and budget</h3>
          <p className={`hint analytics-budget-${budget.status}`}>
            {BUDGET_STATUS_LABELS[budget.status] ?? budget.status}
            {budget.contract_value_usd !== null && (
              <>
                {' · '}
                {formatUsd(budget.total_spend_to_date_usd)} of{' '}
                {formatUsd(budget.contract_value_usd)} spent
                {budget.percent_of_budget_spent !== null &&
                  ` (${budget.percent_of_budget_spent}%)`}
                {' · '}
                {formatUsd(budget.budget_remaining_usd)} remaining
              </>
            )}
          </p>
          <p className="hint">
            Material line items on record total{' '}
            {formatUsd(budget.material_cost_from_line_items_usd)} — recorded quantities ×
            unit costs, independent of the daily figures reported by voice.
          </p>

          {costTrendData.length > 0 && (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart
                data={costTrendData}
                margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} />
                <Tooltip
                  contentStyle={{ background: '#273549', border: '1px solid #334155' }}
                  labelStyle={{ color: '#f1f5f9' }}
                  formatter={(value) => formatUsd(Number(value))}
                />
                <Line
                  type="monotone"
                  dataKey="daily"
                  stroke={COST_DAILY_COLOR}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Daily cost"
                />
                <Line
                  type="monotone"
                  dataKey="cumulative"
                  stroke={COST_CUMULATIVE_COLOR}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Cumulative spend"
                />
              </LineChart>
            </ResponsiveContainer>
          )}

          {changeOrderData.length > 0 && (
            <div className="analytics-change-orders">
              <h4>Change orders</h4>
              <ul className="analytics-change-order-list">
                {changeOrderData.map((c) => (
                  <li key={c.status}>
                    <span className="analytics-change-order-status">
                      {c.status.replace(/_/g, ' ')}
                    </span>
                    : {c.change_order_count} ({formatUsd(c.total_cost_impact_usd)})
                  </li>
                ))}
              </ul>
            </div>
          )}

          {evm && (evm.earned_value_usd !== null || evm.planned_value_usd !== null) && (
            <div className="analytics-evm">
              <h4>Earned value</h4>
              <dl className="analytics-evm-grid">
                <div>
                  <dt>Planned value</dt>
                  <dd>{formatUsd(evm.planned_value_usd)}</dd>
                </div>
                <div>
                  <dt>Earned value</dt>
                  <dd>{formatUsd(evm.earned_value_usd)}</dd>
                </div>
                <div>
                  <dt>Actual cost</dt>
                  <dd>{formatUsd(evm.actual_cost_usd)}</dd>
                </div>
                <div>
                  <dt>Cost performance (CPI)</dt>
                  <dd>
                    {evm.cost_performance_index !== null ? (
                      <span
                        className={
                          evm.cost_performance_index >= 1
                            ? 'analytics-evm-good'
                            : 'analytics-evm-bad'
                        }
                      >
                        {evm.cost_performance_index.toFixed(2)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </dd>
                </div>
                <div>
                  <dt>Schedule performance (SPI)</dt>
                  <dd>
                    {evm.schedule_performance_index !== null ? (
                      <span
                        className={
                          evm.schedule_performance_index >= 1
                            ? 'analytics-evm-good'
                            : 'analytics-evm-bad'
                        }
                      >
                        {evm.schedule_performance_index.toFixed(2)}
                      </span>
                    ) : (
                      '—'
                    )}
                  </dd>
                </div>
              </dl>
              <p className="hint">
                CPI/SPI above 1.0 means ahead of cost/schedule expectations, below 1.0 means
                behind. Planned value assumes cost accrues evenly across the schedule — a
                simplification, not a per-stage budget.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Reference-cost estimate (Sprint 17, ADR-065). Staff-only for the
          same reason as "Cost and budget" — internal cost planning, not
          client-facing. Deliberately never labeled a bid or a quote: it's
          a materials-only range computed from typical-quantity reference
          data, not from this project's own actual spend or any
          historical project. */}
      {isStaffView && costEstimate && (
        <div className="analytics-chart">
          <h3>Reference cost estimate</h3>
          {costEstimate.unavailable_reason ? (
            <p className="hint">{costEstimate.unavailable_reason}</p>
          ) : (
            <>
              <p className="hint">
                Materials-only reference range for a {costEstimate.project_size_sqft?.toLocaleString()}{' '}
                sqft project: {formatUsd(costEstimate.low_usd)} – {formatUsd(costEstimate.high_usd)}.
                Computed from typical material quantities per square foot, not from this
                project's own spend or any historical project — labor, subcontractors, and
                permits are not included.
              </p>
              {costEstimate.contract_comparison_note && (
                <p className="hint">{costEstimate.contract_comparison_note}</p>
              )}
              {costEstimate.stages.length > 0 && (
                <table className="analytics-cost-estimate-table">
                  <thead>
                    <tr>
                      <th>Stage</th>
                      <th>Reference range</th>
                    </tr>
                  </thead>
                  <tbody>
                    {costEstimate.stages.map((stage) => (
                      <tr key={stage.stage_id}>
                        <td>{stage.stage_id.replace(/_/g, ' ')}</td>
                        <td>
                          {formatUsd(stage.low_usd)} – {formatUsd(stage.high_usd)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </div>
      )}
    </section>
  )
}
