import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Box, CircularProgress, Typography } from '@mui/material'
import { useAuth } from '../context/AuthContext'

interface ProtectedRouteProps {
  children: React.ReactNode
  requiredPermissions?: string[]
  allowedRoles?: string[]
}

export default function ProtectedRoute({ children, requiredPermissions = [], allowedRoles = [] }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, hasAnyPermission, user } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '70vh' }}>
        <CircularProgress />
      </Box>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  }

  if (user?.role === 'API User') {
    return (
      <Box sx={{ mt: 8, textAlign: 'center', px: 2 }}>
        <Typography variant="h5" gutterBottom>
          API User has no UI access
        </Typography>
        <Typography color="text.secondary">
          Use API token or bearer auth for API endpoints.
        </Typography>
      </Box>
    )
  }

  const hasAllowedRole = Boolean(user?.role && allowedRoles.includes(user.role))

  if (requiredPermissions.length > 0 && !hasAnyPermission(requiredPermissions) && !hasAllowedRole) {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}
