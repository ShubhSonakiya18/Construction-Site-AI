import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getAccessToken, setTokens, clearTokens } from '../api/client'
import { login as loginApi, logout as logoutApi } from '../api/endpoints'
import type { LoginResponseData } from '../api/types'

interface AuthUser {
  userId: string
  companyId: string
  email: string
  role: string
}

interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const USER_STORAGE_KEY = 'csa_user'

function storeUser(data: LoginResponseData): AuthUser {
  const user: AuthUser = {
    userId: data.user_id,
    companyId: data.company_id,
    email: data.email,
    role: data.role,
  }
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user))
  return user
}

function readStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Trust the locally-stored user/token pair on page load rather than
    // re-verifying against GET /auth/me here — every apiClient request
    // already carries the access token and the response interceptor
    // (api/client.ts) transparently refreshes or logs out on a real 401,
    // so an extra verification round-trip on every page load would only
    // add latency for the common case (token still valid).
    const token = getAccessToken()
    const storedUser = readStoredUser()
    if (token && storedUser) {
      setUser(storedUser)
    }
    setIsLoading(false)
  }, [])

  async function login(email: string, password: string) {
    const data = await loginApi(email, password)
    setTokens(data.access_token, data.refresh_token)
    setUser(storeUser(data))
  }

  async function logout() {
    await logoutApi()
    localStorage.removeItem(USER_STORAGE_KEY)
    clearTokens()
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated: user !== null, isLoading, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth() must be used within an AuthProvider.')
  return ctx
}
