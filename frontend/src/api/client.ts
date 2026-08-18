import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { ApiResponse, RefreshResponseData } from './types'

// Storage keys. localStorage (not a cookie) is the pragmatic Sprint 9
// choice: the backend's refresh token is already opaque and
// server-revocable (UserSession rows, Sprint 8) rather than a JWT itself,
// so an XSS reading it from localStorage can do the same damage an
// httpOnly-cookie setup would still need CSRF protection against on a
// same-origin API. A production hardening pass could move to httpOnly
// cookies later without changing anything below AuthProvider's public
// interface.
const ACCESS_TOKEN_KEY = 'csa_access_token'
const REFRESH_TOKEN_KEY = 'csa_refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}
export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, access)
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh)
}
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

export const apiClient = axios.create({ baseURL: '/api/v1' })

apiClient.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Single in-flight refresh shared across every 401 that arrives while a
// refresh is already happening — without this, N concurrent requests that
// all 401 at once would each fire their own POST /auth/refresh, and per
// Sprint 8's rotation design (ADR-035) only the FIRST of those succeeds;
// the rest would rotate an already-rotated (now-revoked) token and log
// the user out despite having a perfectly valid session.
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new Error('No refresh token available.')
  }
  const response = await axios.post<ApiResponse<RefreshResponseData>>(
    '/api/v1/auth/refresh',
    { refresh_token: refreshToken },
  )
  const data = response.data.data
  if (!data) {
    throw new Error('Refresh response had no data.')
  }
  setTokens(data.access_token, data.refresh_token)
  return data.access_token
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined

    const isAuthEndpoint =
      originalRequest?.url?.includes('/auth/login') ||
      originalRequest?.url?.includes('/auth/refresh')

    if (
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retried &&
      !isAuthEndpoint
    ) {
      originalRequest._retried = true
      try {
        if (!refreshPromise) {
          refreshPromise = refreshAccessToken().finally(() => {
            refreshPromise = null
          })
        }
        const newAccessToken = await refreshPromise
        originalRequest.headers = originalRequest.headers ?? {}
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
        return apiClient(originalRequest)
      } catch {
        clearTokens()
        window.location.href = '/login'
        return Promise.reject(error)
      }
    }
    return Promise.reject(error)
  },
)

/** Extracts a human-readable message from a failed ApiResponse envelope,
 * falling back sensibly for network errors that never reached the
 * backend's envelope shape at all. */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as ApiResponse<unknown> | undefined
    if (body?.message) return body.message
    if (body?.errors?.length) return body.errors.map((e) => e.message).join(' ')
    if (error.response?.status === 429) return 'Too many attempts. Please try again later.'
    if (!error.response) return 'Could not reach the server. Is the backend running?'
  }
  return 'Something went wrong.'
}
