import { apiClient, clearTokens, getRefreshToken } from './client'
import type {
  ApiResponse,
  AskProjectQuestionResponseData,
  AudioStatusResponseData,
  AudioUploadResponseData,
  CurrentUserResponseData,
  DailyLogRead,
  DailyLogSummary,
  LoginResponseData,
  ProjectRead,
} from './types'

export async function login(
  email: string,
  password: string,
): Promise<LoginResponseData> {
  const response = await apiClient.post<ApiResponse<LoginResponseData>>('/auth/login', {
    email,
    password,
  })
  if (!response.data.data) throw new Error('Login response had no data.')
  return response.data.data
}

export async function logout(): Promise<void> {
  const refreshToken = getRefreshToken()
  try {
    if (refreshToken) {
      await apiClient.post('/auth/logout', { refresh_token: refreshToken })
    }
  } finally {
    // Always clear local tokens even if the revoke call itself fails
    // (e.g. network drop) — a logged-out UI is the correct client state
    // regardless of whether the server-side session row was revoked.
    clearTokens()
  }
}

export async function getCurrentUser(): Promise<CurrentUserResponseData> {
  const response = await apiClient.get<ApiResponse<CurrentUserResponseData>>('/auth/me')
  if (!response.data.data) throw new Error('No current-user data.')
  return response.data.data
}

export async function forgotPassword(email: string): Promise<void> {
  await apiClient.post('/auth/forgot-password', { email })
}

export async function resetPassword(
  resetToken: string,
  newPassword: string,
): Promise<void> {
  await apiClient.post('/auth/reset-password', {
    reset_token: resetToken,
    new_password: newPassword,
  })
}

// ── Projects ───────────────────────────────────────────────────────────────

export async function listProjectDailyLogs(
  projectId: string,
  status?: string,
): Promise<DailyLogSummary[]> {
  const response = await apiClient.get<ApiResponse<DailyLogSummary[]>>(
    `/projects/${projectId}/daily-logs`,
    { params: status ? { status } : undefined },
  )
  return response.data.data ?? []
}

export async function askProjectQuestion(
  projectId: string,
  question: string,
): Promise<AskProjectQuestionResponseData> {
  const response = await apiClient.post<ApiResponse<AskProjectQuestionResponseData>>(
    `/projects/${projectId}/ask`,
    { question },
  )
  if (!response.data.data) throw new Error('No answer returned.')
  return response.data.data
}

// There is no GET /projects (list all projects) endpoint yet in the
// backend (see docs/NEXT_SPRINT.md — full project CRUD is explicitly
// deferred). The dashboard therefore works from a known project id rather
// than a project picker — see Dashboard.tsx's own note on this gap.
export async function getProject(_projectId: string): Promise<ProjectRead | null> {
  // Placeholder for when GET /projects/{id} exists — kept as a named,
  // typed function so DashboardPage's call site doesn't need to change
  // shape when the backend adds it, only this function's body.
  return null
}

// ── Daily Logs ─────────────────────────────────────────────────────────────

export async function getDailyLog(logId: string): Promise<DailyLogRead> {
  const response = await apiClient.get<ApiResponse<DailyLogRead>>(`/daily-logs/${logId}`)
  if (!response.data.data) throw new Error('Daily log not found.')
  return response.data.data
}

export async function approveDailyLog(logId: string, notes?: string): Promise<DailyLogRead> {
  const response = await apiClient.post<ApiResponse<DailyLogRead>>(
    `/daily-logs/${logId}/approve`,
    { notes },
  )
  if (!response.data.data) throw new Error('No data returned from approve.')
  return response.data.data
}

export async function rejectDailyLog(logId: string, notes: string): Promise<DailyLogRead> {
  const response = await apiClient.post<ApiResponse<DailyLogRead>>(
    `/daily-logs/${logId}/reject`,
    { notes },
  )
  if (!response.data.data) throw new Error('No data returned from reject.')
  return response.data.data
}

// ── Audio ──────────────────────────────────────────────────────────────────

export async function uploadAudio(
  file: File,
  projectId?: string,
): Promise<AudioUploadResponseData> {
  const form = new FormData()
  form.append('file', file)
  if (projectId) form.append('project_id', projectId)
  const response = await apiClient.post<ApiResponse<AudioUploadResponseData>>(
    '/audio/upload',
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  if (!response.data.data) throw new Error('Upload response had no data.')
  return response.data.data
}

export async function getAudioStatus(audioId: string): Promise<AudioStatusResponseData> {
  const response = await apiClient.get<ApiResponse<AudioStatusResponseData>>(
    `/audio/${audioId}/status`,
  )
  if (!response.data.data) throw new Error('No status data.')
  return response.data.data
}
