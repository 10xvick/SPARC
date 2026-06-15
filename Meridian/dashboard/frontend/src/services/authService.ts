import axios from 'axios'

export interface AuthUser {
  id: number
  sapid: string
  name: string
  email: string | null
  role: string
  is_active: boolean
  team_ids: string[]
  managed_user_ids: number[]
  source: string
  last_login: string | null
  created_at: string
  updated_at: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: AuthUser
  permissions: string[]
}

export interface AuthSession {
  accessToken: string
  refreshToken: string
  user: AuthUser
  permissions: string[]
}

const STORAGE_KEY = 'teamsight_auth_session'

// Track ongoing refresh to avoid parallel refresh storms
let _refreshPromise: Promise<AuthSession> | null = null

export const authService = {
  async login(sapid: string, password: string): Promise<AuthSession> {
    const response = await axios.post<LoginResponse>('/api/auth/login', { sapid, password })
    const payload = response.data

    const session: AuthSession = {
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      user: payload.user,
      permissions: payload.permissions ?? []
    }

    this.persistSession(session)
    this.applyAuthHeader(session.accessToken)
    return session
  },

  async refresh(refreshToken: string): Promise<AuthSession> {
    const response = await axios.post<LoginResponse>('/api/auth/refresh', {
      refresh_token: refreshToken
    })
    const payload = response.data

    const session: AuthSession = {
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      user: payload.user,
      permissions: payload.permissions ?? []
    }

    this.persistSession(session)
    this.applyAuthHeader(session.accessToken)
    return session
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await axios.post('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword
    })
  },

  getStoredSession(): AuthSession | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return null
      const parsed = JSON.parse(raw) as AuthSession
      if (!parsed?.accessToken || !parsed?.refreshToken || !parsed?.user) {
        return null
      }
      return parsed
    } catch {
      return null
    }
  },

  persistSession(session: AuthSession): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  },

  clearSession(): void {
    localStorage.removeItem(STORAGE_KEY)
    delete axios.defaults.headers.common.Authorization
  },

  applyAuthHeader(accessToken: string): void {
    axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`
  },

  /**
   * Set up a global axios response interceptor that:
   * 1. Detects 401 errors from the API
   * 2. Attempts a silent token refresh using the stored refresh token
   * 3. Retries the original request with the new token
   * 4. Redirects to /login if refresh fails (expired refresh token)
   *
   * Called once at app startup from AuthProvider.
   */
  setupRefreshInterceptor(): void {
    axios.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config

        // Only handle 401 errors; skip auth endpoints and already-retried requests
        if (
          error.response?.status !== 401 ||
          originalRequest._retried ||
          originalRequest.url?.includes('/api/auth/')
        ) {
          return Promise.reject(error)
        }

        originalRequest._retried = true

        try {
          const stored = authService.getStoredSession()
          if (!stored?.refreshToken) {
            throw new Error('No refresh token')
          }

          // Deduplicate concurrent refresh calls
          if (!_refreshPromise) {
            _refreshPromise = authService.refresh(stored.refreshToken).finally(() => {
              _refreshPromise = null
            })
          }

          const newSession = await _refreshPromise

          // Patch the original request with the new token and retry
          originalRequest.headers = originalRequest.headers ?? {}
          originalRequest.headers['Authorization'] = `Bearer ${newSession.accessToken}`
          return axios(originalRequest)
        } catch {
          // Refresh failed – clear session and redirect to login
          authService.clearSession()
          window.location.href = '/login'
          return Promise.reject(error)
        }
      }
    )
  }
}
