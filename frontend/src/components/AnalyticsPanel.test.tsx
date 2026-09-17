import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AuthProvider } from '../auth/AuthContext'
import { AnalyticsPanel } from './AnalyticsPanel'
import * as endpoints from '../api/endpoints'
import type { ProjectAnalyticsResponseData } from '../api/types'

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof endpoints>()
  return { ...actual, getProjectAnalytics: vi.fn() }
})

beforeEach(() => {
  vi.mocked(endpoints.getProjectAnalytics).mockReset()
  localStorage.clear()
})

// AnalyticsPanel reads the current user's role (Sprint 13, Deliverable 5,
// ADR-056 — hides Safety incidents / Delay frequency by trade from
// client) via useAuth(), so every render needs an AuthProvider ancestor.
// Defaults to 'owner' (every section visible) so the pre-existing tests
// below, written before role-gating existed, keep asserting what they
// always asserted; the dedicated RBAC tests at the bottom override the
// role per-test, matching DocumentsPanel.test.tsx's established pattern.
function renderAnalyticsPanel(projectId = 'proj-1', role = 'owner') {
  localStorage.setItem('csa_access_token', 'fake-token')
  localStorage.setItem('csa_refresh_token', 'fake-refresh')
  localStorage.setItem(
    'csa_user',
    JSON.stringify({ userId: 'u1', companyId: 'c1', email: 'a@b.com', role }),
  )
  return render(
    <AuthProvider>
      <AnalyticsPanel projectId={projectId} />
    </AuthProvider>,
  )
}

function makeResponse(
  overrides: Partial<ProjectAnalyticsResponseData> = {},
): ProjectAnalyticsResponseData {
  return {
    completion_trend: [],
    delay_frequency: [],
    delay_frequency_by_trade: [],
    safety_incident_trend: [],
    safety_incident_breakdown: [],
    safety_proactive_warnings: null,
    productivity_by_stage_trade: [],
    daily_cost_trend: [],
    budget_variance: null,
    earned_value: null,
    change_order_summary: [],
    cost_estimate: null,
    alert_history: [],
    logs_analyzed: 0,
    projected_completion_date: null,
    delay_adjusted_completion_date: null,
    ...overrides,
  }
}

describe('AnalyticsPanel', () => {
  it('shows an empty-state message when no approved logs exist yet', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse())
    renderAnalyticsPanel()
    expect(await screen.findByText(/analytics will appear once/i)).toBeInTheDocument()
  })

  it('renders the "based on N approved log(s)" summary once data loads', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
      completion_trend: [
        { log_date: '2026-05-14', overall_project_completion_percent: 28 },
        { log_date: '2026-05-15', overall_project_completion_percent: 32 },
      ],
      logs_analyzed: 2,
    }))
    renderAnalyticsPanel()
    expect(await screen.findByText(/based on 2 approved log/i)).toBeInTheDocument()
    expect(screen.getByText('Completion trend')).toBeInTheDocument()
  })

  it('renders the delay-frequency section only when there is delay data', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
      completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
      logs_analyzed: 1,
    }))
    renderAnalyticsPanel()
    await screen.findByText(/based on 1 approved log/i)
    expect(screen.queryByText('Delay frequency')).not.toBeInTheDocument()
  })

  it('renders the delay-frequency chart when delays are present', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
      completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
      delay_frequency: [
        { delay_type: 'material_shortage', occurrence_count: 3, total_hours_lost: 6.5 },
        { delay_type: 'weather', occurrence_count: 1, total_hours_lost: 0 },
      ],
      logs_analyzed: 1,
    }))
    renderAnalyticsPanel()
    expect(await screen.findByText('Delay frequency')).toBeInTheDocument()
  })

  it('shows an error message if the analytics request fails', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockRejectedValue({
      isAxiosError: true,
      response: { status: 404, data: { message: 'Project not found.' } },
    })
    renderAnalyticsPanel()
    expect(await screen.findByRole('alert')).toHaveTextContent(/project not found/i)
  })

  it('re-fetches when projectId changes', async () => {
    vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse())
    const { rerender } = renderAnalyticsPanel()
    await screen.findByText(/analytics will appear once/i)

    rerender(
      <AuthProvider>
        <AnalyticsPanel projectId="proj-2" />
      </AuthProvider>,
    )
    expect(endpoints.getProjectAnalytics).toHaveBeenCalledWith('proj-1')
    expect(endpoints.getProjectAnalytics).toHaveBeenCalledWith('proj-2')
  })

  describe('projected completion (Sprint 13, Deliverable 1)', () => {
    it('shows no projection line when the project has no schedule yet', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      await screen.findByText('Completion trend')
      expect(screen.queryByText(/planned completion/i)).not.toBeInTheDocument()
    })

    it('shows no delay-frequency-by-trade section when the array is empty', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Delay frequency by trade')).not.toBeInTheDocument()
    })

    it('states that no incidents were recorded rather than hiding the safety section', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText('Safety incidents')).toBeInTheDocument()
      expect(screen.getByText(/no safety incidents recorded/i)).toBeInTheDocument()
    })

    it('summarizes incident counts and flags OSHA-recordable ones', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        safety_incident_trend: [
          { log_date: '2026-05-14', incident_count: 2, osha_recordable_count: 1 },
        ],
        safety_incident_breakdown: [
          { incident_type: 'near_miss', incident_count: 1, osha_recordable_count: 0 },
          { incident_type: 'first_aid', incident_count: 1, osha_recordable_count: 1 },
        ],
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText(/2 incident\(s\) recorded/i)).toBeInTheDocument()
      expect(screen.getByText(/1 OSHA-recordable/i)).toBeInTheDocument()
      expect(screen.queryByText(/no safety incidents recorded/i)).not.toBeInTheDocument()
    })

    it('omits the OSHA-recordable callout when none are recordable', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        safety_incident_trend: [
          { log_date: '2026-05-14', incident_count: 1, osha_recordable_count: 0 },
        ],
        safety_incident_breakdown: [
          { incident_type: 'near_miss', incident_count: 1, osha_recordable_count: 0 },
        ],
      }))
      renderAnalyticsPanel()
      await screen.findByText(/1 incident\(s\) recorded/i)
      expect(screen.queryByText(/OSHA-recordable/i)).not.toBeInTheDocument()
    })

    it('shows no productivity section when the array is empty', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      await screen.findByText('Completion trend')
      expect(
        screen.queryByText('Average reported completion by stage / trade'),
      ).not.toBeInTheDocument()
    })

    it('renders the productivity-by-stage-trade chart when data is present', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        productivity_by_stage_trade: [
          { current_stage: 'framing', trade: 'framing_carpenter', avg_task_completion_percent: 82, work_item_count: 5 },
          { current_stage: 'foundation', trade: 'general_labor', avg_task_completion_percent: 60, work_item_count: 2 },
        ],
      }))
      renderAnalyticsPanel()
      expect(
        await screen.findByText('Average reported completion by stage / trade'),
      ).toBeInTheDocument()
    })

    it('renders the delay-frequency-by-trade chart when data is present', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        delay_frequency_by_trade: [
          { trade: 'electrical', delay_count: 2, total_hours_lost: 5 },
          { trade: 'framing', delay_count: 1, total_hours_lost: 2 },
        ],
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText('Delay frequency by trade')).toBeInTheDocument()
    })

    it('shows the planned completion date when a schedule exists', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        projected_completion_date: '2026-06-26',
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText(/planned completion: 2026-06-26/i)).toBeInTheDocument()
    })

    it('shows a separate delay-adjusted date only when it differs from the planned date', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        projected_completion_date: '2026-06-26',
        delay_adjusted_completion_date: '2026-07-02',
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText(/delay-adjusted: 2026-07-02/i)).toBeInTheDocument()
    })

    it('does not repeat the date when delay_adjusted_completion_date equals projected_completion_date', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        projected_completion_date: '2026-06-26',
        delay_adjusted_completion_date: '2026-06-26',
      }))
      renderAnalyticsPanel()
      await screen.findByText(/planned completion: 2026-06-26/i)
      expect(screen.queryByText(/delay-adjusted/i)).not.toBeInTheDocument()
    })
  })

  describe('safety status (Sprint 15, Deliverable 4)', () => {
    it('shows no safety-status section when the field is null', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Safety status')).not.toBeInTheDocument()
    })

    it('shows days since last incident and lists unresolved hazards', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        safety_proactive_warnings: {
          unresolved_hazards: [
            { hazard_type: 'trip_hazard', severity: 'medium', description: 'Loose cabling', days_open: 5 },
          ],
          days_since_last_incident: 12,
          incidence_rate_per_200k_hours: null,
          incidence_rate_unavailable_reason: 'only 300 hours logged -- too few to compute a reliable incidence rate',
        },
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText('Safety status')).toBeInTheDocument()
      expect(screen.getByText(/12 day\(s\) since the last recorded incident/)).toBeInTheDocument()
      expect(screen.getByText(/Loose cabling/)).toBeInTheDocument()
      expect(screen.getByText(/5 day\(s\) open/)).toBeInTheDocument()
      expect(screen.getByText(/Incidence rate unavailable/)).toBeInTheDocument()
    })

    it('shows "no unresolved hazards" when the list is empty', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        safety_proactive_warnings: {
          unresolved_hazards: [],
          days_since_last_incident: null,
          incidence_rate_per_200k_hours: null,
          incidence_rate_unavailable_reason: null,
        },
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText('Safety status')).toBeInTheDocument()
      expect(screen.getByText('No unresolved hazards.')).toBeInTheDocument()
      expect(screen.getByText('No safety incidents on record.')).toBeInTheDocument()
    })

    it('shows the incidence rate when available', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        safety_proactive_warnings: {
          unresolved_hazards: [],
          days_since_last_incident: 40,
          incidence_rate_per_200k_hours: 2.5,
          incidence_rate_unavailable_reason: null,
        },
      }))
      renderAnalyticsPanel()
      await screen.findByText('Safety status')
      expect(screen.getByText(/OSHA incidence rate: 2.5/)).toBeInTheDocument()
    })

    it('hides the safety-status section from a client-role user', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        safety_proactive_warnings: {
          unresolved_hazards: [],
          days_since_last_incident: 5,
          incidence_rate_per_200k_hours: null,
          incidence_rate_unavailable_reason: null,
        },
      }))
      renderAnalyticsPanel('proj-1', 'client')
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Safety status')).not.toBeInTheDocument()
    })
  })

  describe('cost and budget (Sprint 14)', () => {
    const withBudget = (overrides = {}) =>
      makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        daily_cost_trend: [
          {
            log_date: '2026-05-14',
            daily_labor_cost_usd: 2887.5,
            daily_material_cost_usd: 1240,
            daily_equipment_cost_usd: 150,
            daily_subcontractor_cost_usd: null,
            daily_total_cost_usd: 4277.5,
            cumulative_spend_to_date_usd: 4277.5,
          },
        ],
        budget_variance: {
          contract_value_usd: 425000,
          total_spend_to_date_usd: 4277.5,
          budget_remaining_usd: 420722.5,
          percent_of_budget_spent: 1.01,
          status: 'on_track' as const,
          material_cost_from_line_items_usd: 3828,
        },
        ...overrides,
      })

    it('shows no cost section when the project has no budget data', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Cost and budget')).not.toBeInTheDocument()
    })

    it('renders spend against the contract value', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(withBudget())
      renderAnalyticsPanel()
      expect(await screen.findByText('Cost and budget')).toBeInTheDocument()
      expect(screen.getByText(/on track/i)).toBeInTheDocument()
      expect(screen.getByText(/\$4,278 of \$425,000 spent/)).toBeInTheDocument()
      expect(screen.getByText(/\$420,723 remaining/)).toBeInTheDocument()
    })

    it('surfaces the independent material line-item total', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(withBudget())
      renderAnalyticsPanel()
      await screen.findByText('Cost and budget')
      expect(screen.getByText(/\$3,828/)).toBeInTheDocument()
    })

    it('flags an over-budget project', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(
        withBudget({
          budget_variance: {
            contract_value_usd: 100000,
            total_spend_to_date_usd: 112500,
            budget_remaining_usd: -12500,
            percent_of_budget_spent: 112.5,
            status: 'over_budget' as const,
            material_cost_from_line_items_usd: 0,
          },
        }),
      )
      renderAnalyticsPanel()
      expect(await screen.findByText(/over budget/i)).toBeInTheDocument()
    })

    it('renders a change-order breakdown when change orders exist', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(
        withBudget({
          change_order_summary: [
            { status: 'approved', change_order_count: 2, total_cost_impact_usd: 6000 },
            { status: 'under_negotiation', change_order_count: 1, total_cost_impact_usd: 1800 },
          ],
        }),
      )
      renderAnalyticsPanel()
      expect(await screen.findByText('Change orders')).toBeInTheDocument()
      expect(screen.getByText('approved')).toBeInTheDocument()
      expect(screen.getByText('under negotiation')).toBeInTheDocument()
    })

    it('shows no earned-value block when both EV and PV are null', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(
        withBudget({
          earned_value: {
            planned_value_usd: null,
            earned_value_usd: null,
            actual_cost_usd: 4277.5,
            cost_performance_index: null,
            schedule_performance_index: null,
          },
        }),
      )
      renderAnalyticsPanel()
      await screen.findByText('Cost and budget')
      expect(screen.queryByText('Earned value')).not.toBeInTheDocument()
    })

    it('renders CPI/SPI with EV/AC/PV once earned value is available', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(
        withBudget({
          earned_value: {
            planned_value_usd: 50000,
            earned_value_usd: 40000,
            actual_cost_usd: 32000,
            cost_performance_index: 1.25,
            schedule_performance_index: 0.8,
          },
        }),
      )
      renderAnalyticsPanel()
      expect(
        await screen.findByRole('heading', { name: 'Earned value' }),
      ).toBeInTheDocument()
      expect(screen.getByText('1.25')).toBeInTheDocument()
      expect(screen.getByText('0.80')).toBeInTheDocument()
    })

    it('hides the whole cost section from a client-role user', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(withBudget())
      renderAnalyticsPanel('proj-1', 'client')
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Cost and budget')).not.toBeInTheDocument()
      expect(screen.queryByText(/425,000/)).not.toBeInTheDocument()
    })
  })

  describe('reference cost estimate (Sprint 17, ADR-065)', () => {
    it('shows no section when the project has no cost_estimate data', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Reference cost estimate')).not.toBeInTheDocument()
    })

    it('shows the unavailable reason when the project has no size set', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        cost_estimate: {
          project_size_sqft: null,
          stages: [],
          low_usd: 0,
          high_usd: 0,
          unavailable_reason: 'This project has no schedule yet -- a reference-cost estimate needs a stage list to know which materials apply.',
          contract_comparison_note: null,
        },
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText('Reference cost estimate')).toBeInTheDocument()
      expect(screen.getByText(/no schedule yet/)).toBeInTheDocument()
    })

    it('renders the total range, stage breakdown, and contract comparison note', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        cost_estimate: {
          project_size_sqft: 2850,
          stages: [
            {
              stage_id: 'foundation',
              materials: [
                {
                  material_id: 'mat_ready_mix_concrete',
                  material_name: 'Ready-Mix Concrete',
                  unit: 'cubic_yards',
                  estimated_quantity: 114,
                  low_usd: 13680,
                  high_usd: 20520,
                },
              ],
              low_usd: 14592,
              high_usd: 22116,
            },
          ],
          low_usd: 51898.5,
          high_usd: 107795.55,
          unavailable_reason: null,
          contract_comparison_note:
            'The contract value ($425,000) is above the reference materials estimate range ($51,898-$107,796).',
        },
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText('Reference cost estimate')).toBeInTheDocument()
      expect(screen.getAllByText(/\$51,899/).length).toBeGreaterThan(0)
      expect(screen.getAllByText(/\$107,796/).length).toBeGreaterThan(0)
      expect(screen.getByText('foundation')).toBeInTheDocument()
      expect(screen.getByText(/is above the reference materials estimate range/)).toBeInTheDocument()
    })

    it('hides the section from a client-role user', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        cost_estimate: {
          project_size_sqft: 2850,
          stages: [],
          low_usd: 51898.5,
          high_usd: 107795.55,
          unavailable_reason: null,
          contract_comparison_note: null,
        },
      }))
      renderAnalyticsPanel('proj-1', 'client')
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Reference cost estimate')).not.toBeInTheDocument()
    })
  })

  describe('alert history (Sprint 19, ADR-066)', () => {
    it('shows no section when alert_history is empty', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
      }))
      renderAnalyticsPanel()
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Alert history')).not.toBeInTheDocument()
    })

    it('renders the last alert sent for each alert type', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        alert_history: [
          {
            alert_type: 'budget_variance',
            last_status_value: 'over_budget',
            last_sent_at: '2026-09-17T12:00:00Z',
          },
          {
            alert_type: 'safety_warning',
            last_status_value: 'has_hazards',
            last_sent_at: '2026-09-16T08:00:00Z',
          },
        ],
      }))
      renderAnalyticsPanel()
      expect(await screen.findByText('Alert history')).toBeInTheDocument()
      expect(screen.getByText('budget variance')).toBeInTheDocument()
      expect(screen.getByText('over budget')).toBeInTheDocument()
      expect(screen.getByText('safety warning')).toBeInTheDocument()
      expect(screen.getByText('has hazards')).toBeInTheDocument()
    })

    it('hides the section from a client-role user', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(makeResponse({
        completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
        logs_analyzed: 1,
        alert_history: [
          {
            alert_type: 'budget_variance',
            last_status_value: 'over_budget',
            last_sent_at: '2026-09-17T12:00:00Z',
          },
        ],
      }))
      renderAnalyticsPanel('proj-1', 'client')
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Alert history')).not.toBeInTheDocument()
    })
  })

  describe('client-role curation (Sprint 13, Deliverable 5, ADR-056)', () => {
    const fullResponse = makeResponse({
      completion_trend: [{ log_date: '2026-05-14', overall_project_completion_percent: 28 }],
      logs_analyzed: 1,
      delay_frequency_by_trade: [
        { trade: 'electrical', delay_count: 2, total_hours_lost: 5 },
      ],
      safety_incident_trend: [
        { log_date: '2026-05-14', incident_count: 1, osha_recordable_count: 1 },
      ],
      safety_incident_breakdown: [
        { incident_type: 'near_miss', incident_count: 1, osha_recordable_count: 1 },
      ],
      productivity_by_stage_trade: [
        { current_stage: 'framing', trade: 'framing_carpenter', avg_task_completion_percent: 82, work_item_count: 5 },
      ],
    })

    it('hides Delay frequency by trade and Safety incidents from a client-role user', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(fullResponse)
      renderAnalyticsPanel('proj-1', 'client')
      await screen.findByText('Completion trend')
      expect(screen.queryByText('Delay frequency by trade')).not.toBeInTheDocument()
      expect(screen.queryByText('Safety incidents')).not.toBeInTheDocument()
    })

    it('still shows a client-role user completion trend, planned dates, and productivity', async () => {
      vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(fullResponse)
      renderAnalyticsPanel('proj-1', 'client')
      expect(await screen.findByText('Completion trend')).toBeInTheDocument()
      expect(
        screen.getByText('Average reported completion by stage / trade'),
      ).toBeInTheDocument()
    })

    it.each(['owner', 'admin', 'project_manager', 'safety_officer', 'foreman', 'system_admin'])(
      'shows Delay frequency by trade and Safety incidents to a %s-role user',
      async (role) => {
        vi.mocked(endpoints.getProjectAnalytics).mockResolvedValue(fullResponse)
        renderAnalyticsPanel('proj-1', role)
        expect(await screen.findByText('Delay frequency by trade')).toBeInTheDocument()
        expect(screen.getByText('Safety incidents')).toBeInTheDocument()
      },
    )
  })
})
