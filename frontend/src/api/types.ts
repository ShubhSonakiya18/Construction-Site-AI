// Types mirroring app/schemas/*.py exactly — field names and shapes are
// kept in lockstep with the backend Pydantic models, not independently
// designed, so a backend response can be trusted to match these types
// without a runtime validation layer (this project has no OpenAPI-codegen
// step yet; these are hand-kept in sync — see the reference note below
// when the Sprint 8/9 schemas change).

export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T | null
  metadata: Record<string, unknown> | null
  errors: ErrorDetail[] | null
  timestamp: string
  request_id: string
}

export interface ErrorDetail {
  code: string
  message: string
  field: string | null
}

// ── Auth (app/schemas/auth.py) ────────────────────────────────────────────

export interface LoginResponseData {
  access_token: string
  token_type: string
  expires_in_minutes: number
  user_id: string
  company_id: string
  role: string
  email: string
  refresh_token: string
  refresh_token_expires_in_days: number
  session_id: string
}

export interface RefreshResponseData {
  access_token: string
  token_type: string
  expires_in_minutes: number
  refresh_token: string
  refresh_token_expires_in_days: number
  session_id: string
}

export interface CurrentUserResponseData {
  user_id: string
  company_id: string
  email: string
  first_name: string
  last_name: string
  role: string
  is_active: boolean
}

// ── Projects / Daily Logs (app/schemas/project.py, daily_log.py) ─────────

export interface ProjectRead {
  id: string
  company_id: string
  name: string
  project_type: string | null
  status: string
  client_name: string | null
  project_start_date: string | null
  planned_completion_date: string | null
  contract_value_usd: number | null
  created_at: string
}

export interface DailyLogSummary {
  id: string
  project_id: string
  site_id: string | null
  log_date: string
  current_stage: string
  review_status: 'draft' | 'under_review' | 'approved' | 'rejected'
  total_workers_present: number
  overall_project_completion_percent: number | null
  created_at: string
}

export interface TradeOnSiteRead {
  id: string
  trade: string
  workers_count: number
  foreman_name: string | null
  subcontractor_company: string | null
  hours_worked: number | null
  notes: string | null
}

export interface WorkItemRead {
  id: string
  task_description: string
  trade: string
  location_on_site: string | null
  quantity_completed: number | null
  unit_of_measure: string | null
  task_completion_percent: number | null
  notes: string | null
}

export interface DelayRead {
  id: string
  delay_type: string
  description: string
  hours_lost: number | null
  workers_affected: number | null
  schedule_impact: string | null
  days_lost_to_schedule: number | null
  delay_resolved: boolean
  responsible_party: string | null
}

export interface MaterialUsedRead {
  id: string
  material_name: string
  category: string | null
  quantity_used: number
  unit: string
  waste_quantity: number | null
  unit_cost_usd: number | null
  supplier: string | null
}

export interface SafetyIncidentRead {
  id: string
  incident_type: string
  description: string
  worker_involved: string | null
  osha_recordable: boolean | null
  medical_treatment_required: boolean | null
  corrective_actions: string | null
}

export interface DailyLogRead extends DailyLogSummary {
  foreman_id: string | null
  log_source: string
  review_notes: string | null
  reviewed_by_id: string | null
  reviewed_at: string | null
  raw_transcript: string | null
  transcript_confidence: number | null
  stage_completion_percent: number | null
  weather: Record<string, unknown> | null
  total_workers_scheduled: number | null
  total_man_hours_worked: number | null
  safety_meeting_conducted: boolean
  safety_notes: string | null
  tomorrow_plan: Record<string, unknown> | null
  client_communication: Record<string, unknown> | null
  trades_on_site: TradeOnSiteRead[]
  work_items: WorkItemRead[]
  materials_used: MaterialUsedRead[]
  delays: DelayRead[]
  safety_incidents: SafetyIncidentRead[]
}

// ── Audio (app/schemas/audio.py) ──────────────────────────────────────────

export interface AudioUploadResponseData {
  id: string
  original_filename: string
  processing_status: string
  project_id: string | null
  created_at: string
}

export interface AudioStatusResponseData {
  id: string
  original_filename: string
  processing_status:
    | 'pending'
    | 'transcribing'
    | 'extracting'
    | 'generating'
    | 'complete'
    | 'failed'
  is_valid: boolean | null
  validation_errors: string[] | null
  duration_seconds: number | null
  daily_log_id: string | null
  error_message: string | null
}

// ── Project Q&A (app/schemas/project.py, post-Sprint-8) ──────────────────

export interface AskProjectQuestionResponseData {
  answer: string
  logs_used: number
  model: string | null
}

// ── Generation Outputs (app/schemas/generation.py) ────────────────────────

export type ServiceType =
  | 'daily_report'
  | 'customer_update'
  | 'safety_talk'
  | 'material_reminder'
  | 'project_qa'

export interface GenerationOutputRead {
  id: string
  daily_log_id: string | null
  service_type: ServiceType
  content: string
  is_valid: boolean
  is_sent: boolean
  model: string | null
  tokens_used: number | null
  created_at: string
}

export interface TriggerGenerationResponseData {
  daily_log_id: string
  outputs_generated: number
  service_types: string[]
}

// ── Analytics (app/schemas/project.py, Sprint 10 Deliverable 6) ──────────

export interface CompletionTrendPoint {
  log_date: string
  overall_project_completion_percent: number | null
}

export interface DelayFrequencyEntry {
  delay_type: string
  occurrence_count: number
  total_hours_lost: number
}

export interface ProjectAnalyticsResponseData {
  completion_trend: CompletionTrendPoint[]
  delay_frequency: DelayFrequencyEntry[]
  logs_analyzed: number
}
