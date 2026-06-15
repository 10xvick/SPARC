import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { authService, AuthSession, AuthUser } from '../services/authService'

interface AuthContextType {
  user: AuthUser | null
  permissions: string[]
  accessToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (sapid: string, password: string) => Promise<void>
  logout: () => void
  hasPermission: (permission: string) => boolean
  hasAnyPermission: (permissions: string[]) => boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Register the 401 auto-refresh interceptor once at app startup
    authService.setupRefreshInterceptor()

    const stored = authService.getStoredSession()
    if (stored) {
      authService.applyAuthHeader(stored.accessToken)
      setSession(stored)
    }
    setIsLoading(false)
  }, [])

  const login = async (sapid: string, password: string) => {
    const nextSession = await authService.login(sapid, password)
    setSession(nextSession)
  }

  const logout = () => {
    authService.clearSession()
    setSession(null)
  }

  const hasPermission = (permission: string): boolean => {
    if (!session) return false
    return session.permissions.includes(permission)
  }

  const hasAnyPermission = (permissions: string[]): boolean => {
    if (!session) return false
    return permissions.some((permission) => session.permissions.includes(permission))
  }

  const value = useMemo<AuthContextType>(() => ({
    user: session?.user ?? null,
    permissions: session?.permissions ?? [],
    accessToken: session?.accessToken ?? null,
    isAuthenticated: !!session,
    isLoading,
    login,
    logout,
    hasPermission,
    hasAnyPermission
  }), [session, isLoading])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
