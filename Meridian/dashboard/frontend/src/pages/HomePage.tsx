import { useState, useEffect } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { 
  Box, 
  Typography, 
  Card, 
  CardContent, 
  Grid, 
  CircularProgress,
  Alert,
  Paper,
  Chip,
  Divider,
  Link as MuiLink
} from '@mui/material'
import {
  Groups as TeamsIcon,
  GroupWork as ScrumIcon,
  Assignment as RoleIcon,
  Schedule as ScheduleIcon,
  People as PeopleIcon
} from '@mui/icons-material'
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip
} from 'recharts'

interface RoleDistribution {
  name: string
  count: number
}

interface DataCollectionInfo {
  source: string
  lastUpdate: string
  status: string
  recordCount: number
}

export default function HomePage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState({
    teams: 0,
    scrums: 0,
    roles: 0,
    employees: 0
  })
  const [primaryRoleDistribution, setPrimaryRoleDistribution] = useState<RoleDistribution[]>([])
  const [secondaryRoleDistribution, setSecondaryRoleDistribution] = useState<RoleDistribution[]>([])
  const [dataCollectionInfo, setDataCollectionInfo] = useState<DataCollectionInfo[]>([])

  useEffect(() => {
    fetchDashboardData()
  }, [])

  const fetchDashboardData = async () => {
    try {
      // Fetch home statistics (includes all counts and role distributions)
      const statsRes = await fetch('/api/home/statistics')
      const statsData = await statsRes.json()
      
      if (!statsData.success) {
        throw new Error(statsData.error || 'Failed to fetch statistics')
      }
      
      // Set statistics
      setStats(statsData.statistics)
      
      // Set role distributions (top 10)
      setPrimaryRoleDistribution(
        statsData.primary_role_distribution.slice(0, 10)
      )
      setSecondaryRoleDistribution(
        statsData.secondary_role_distribution.slice(0, 10)
      )

      // Mock data collection info (can be replaced with actual API)
      setDataCollectionInfo([
        {
          source: 'JIRA Issues',
          lastUpdate: new Date().toLocaleDateString(),
          status: 'Active',
          recordCount: 1250
        },
        {
          source: 'GitHub Commits',
          lastUpdate: new Date().toLocaleDateString(),
          status: 'Active',
          recordCount: 3450
        },
        {
          source: 'Employee Records',
          lastUpdate: new Date().toLocaleDateString(),
          status: 'Active',
          recordCount: statsData.statistics.employees
        }
      ])

      setLoading(false)
    } catch (err) {
      setError('Failed to load dashboard data')
      setLoading(false)
    }
  }

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D', '#FFC658', '#FF6B9D', '#C0C0C0', '#A4DE6C']

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress />
      </Box>
    )
  }

  if (error) {
    return (
      <Box>
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom fontWeight="bold">
        TeamSight Metrics Dashboard
      </Typography>
      <Typography variant="body1" color="text.secondary" paragraph>
        Comprehensive KPI tracking and team performance analytics
      </Typography>

      {/* Statistics Cards */}
      <Grid container spacing={3} sx={{ mt: 2 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="h3" fontWeight="bold" color="primary">
                    {stats.teams}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Teams
                  </Typography>
                </Box>
                <TeamsIcon sx={{ fontSize: 48, color: 'primary.main', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="h3" fontWeight="bold" color="success.main">
                    {stats.scrums}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Scrums
                  </Typography>
                </Box>
                <ScrumIcon sx={{ fontSize: 48, color: 'success.main', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="h3" fontWeight="bold" color="warning.main">
                    {stats.employees}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Individuals
                  </Typography>
                </Box>
                <PeopleIcon sx={{ fontSize: 48, color: 'warning.main', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="h3" fontWeight="bold" color="error.main">
                    {stats.roles}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Roles
                  </Typography>
                </Box>
                <RoleIcon sx={{ fontSize: 48, color: 'error.main', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Role Distribution Charts */}
      <Grid container spacing={3} sx={{ mt: 2 }}>
        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom fontWeight="bold">
                Primary Role Distribution (Top 10)
              </Typography>
              <Divider sx={{ mb: 2 }} />
              {primaryRoleDistribution.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={primaryRoleDistribution}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name}: ${((percent ?? 0) * 100).toFixed(0)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="count"
                    >
                      {primaryRoleDistribution.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
                  No data available
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom fontWeight="bold">
                Secondary Role Distribution (Top 10)
              </Typography>
              <Divider sx={{ mb: 2 }} />
              {secondaryRoleDistribution.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={secondaryRoleDistribution}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name}: ${((percent ?? 0) * 100).toFixed(0)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="count"
                    >
                      {secondaryRoleDistribution.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
                  No data available
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Data Collection Status */}
      <Grid container spacing={3} sx={{ mt: 2 }}>
        <Grid item xs={12}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" mb={2}>
                <ScheduleIcon sx={{ mr: 1, color: 'primary.main' }} />
                <Typography variant="h6" fontWeight="bold">
                  Data Collection Status
                </Typography>
              </Box>
              <Divider sx={{ mb: 2 }} />
              <Grid container spacing={2}>
                {dataCollectionInfo.map((info, index) => (
                  <Grid item xs={12} sm={6} md={4} key={index}>
                    <Paper elevation={1} sx={{ p: 2 }}>
                      <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
                        {info.source}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Last Update: {info.lastUpdate}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Records: {info.recordCount.toLocaleString()}
                      </Typography>
                      <Box mt={1}>
                        <Chip 
                          label={info.status} 
                          color="success" 
                          size="small" 
                        />
                      </Box>
                    </Paper>
                  </Grid>
                ))}
              </Grid>

            </CardContent>
          </Card>
        </Grid>
      </Grid>



      <Box sx={{ mt: 5, pt: 2, display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
        <MuiLink
          component={RouterLink}
          to="/scoring-logic"
          underline="hover"
          color="text.secondary"
          sx={{ fontSize: '0.75rem', opacity: 0.72 }}
        >
          Scoring Logic
        </MuiLink>
        <MuiLink
          component={RouterLink}
          to="/about"
          underline="hover"
          color="text.secondary"
          sx={{ fontSize: '0.75rem', opacity: 0.72 }}
        >
          About TeamSight
        </MuiLink>
      </Box>
    </Box>
  )
}
