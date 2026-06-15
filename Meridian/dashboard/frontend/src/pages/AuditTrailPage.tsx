import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Grid,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TablePagination,
  TextField,
  Typography,
  Button
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import LoginIcon from '@mui/icons-material/Login'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings'
import QueryStatsIcon from '@mui/icons-material/QueryStats'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend
} from 'recharts'
import { auditTrailApi, AuditTrailResponse } from '../services/auditTrailApi'

type LoginStatusFilter = 'all' | 'success' | 'failed'
type EventTypeFilter =
  | 'login'
  | 'system_admin_access'
  | 'system_admin_change'
  | 'report_access'
  | 'dashboard_access'
  | 'configuration_access'
  | 'configuration_change'
  | 'all'
type CardMetric = {
  label: string
  value: number
  icon: 'login' | 'success' | 'error' | 'warning' | 'admin'
  caption?: string
}

const defaultData: AuditTrailResponse = {
  data: [],
  total_filtered: 0,
  summary: {
    total_events: 0,
    total_logins: 0,
    successful_logins: 0,
    failed_logins: 0,
    admin_access_events: 0,
    admin_change_events: 0,
    report_access_events: 0,
    dashboard_access_events: 0,
    configuration_access_events: 0,
    configuration_change_events: 0,
    unique_users: 0,
    unique_targets: 0,
    last_event_at: null,
    by_day: [],
    top_users: []
  },
  filters: {
    sapids: [],
    roles: [],
    event_types: [
      'login',
      'system_admin_access',
      'system_admin_change',
      'report_access',
      'dashboard_access',
      'configuration_access',
      'configuration_change'
    ]
  }
}

const isObject = (value: unknown): value is Record<string, unknown> => {
  return typeof value === 'object' && value !== null
}

const normalizeAuditPayload = (payload: unknown): AuditTrailResponse | null => {
  if (!isObject(payload)) return null

  const summaryRaw = isObject(payload.summary) ? payload.summary : {}
  const filtersRaw = isObject(payload.filters) ? payload.filters : {}

  return {
    data: Array.isArray(payload.data) ? payload.data as AuditTrailResponse['data'] : [],
    total_filtered: typeof payload.total_filtered === 'number' ? payload.total_filtered : 0,
    summary: {
      total_events: typeof summaryRaw.total_events === 'number' ? summaryRaw.total_events : 0,
      total_logins: typeof summaryRaw.total_logins === 'number' ? summaryRaw.total_logins : 0,
      successful_logins: typeof summaryRaw.successful_logins === 'number' ? summaryRaw.successful_logins : 0,
      failed_logins: typeof summaryRaw.failed_logins === 'number' ? summaryRaw.failed_logins : 0,
      admin_access_events: typeof summaryRaw.admin_access_events === 'number' ? summaryRaw.admin_access_events : 0,
      admin_change_events: typeof summaryRaw.admin_change_events === 'number' ? summaryRaw.admin_change_events : 0,
      report_access_events: typeof summaryRaw.report_access_events === 'number' ? summaryRaw.report_access_events : 0,
      dashboard_access_events: typeof summaryRaw.dashboard_access_events === 'number' ? summaryRaw.dashboard_access_events : 0,
      configuration_access_events: typeof summaryRaw.configuration_access_events === 'number' ? summaryRaw.configuration_access_events : 0,
      configuration_change_events: typeof summaryRaw.configuration_change_events === 'number' ? summaryRaw.configuration_change_events : 0,
      unique_users: typeof summaryRaw.unique_users === 'number' ? summaryRaw.unique_users : 0,
      unique_targets: typeof summaryRaw.unique_targets === 'number' ? summaryRaw.unique_targets : 0,
      last_event_at: typeof summaryRaw.last_event_at === 'string' ? summaryRaw.last_event_at : null,
      by_day: Array.isArray(summaryRaw.by_day) ? summaryRaw.by_day as AuditTrailResponse['summary']['by_day'] : [],
      top_users: Array.isArray(summaryRaw.top_users) ? summaryRaw.top_users as AuditTrailResponse['summary']['top_users'] : []
    },
    filters: {
      sapids: Array.isArray(filtersRaw.sapids) ? filtersRaw.sapids as string[] : [],
      roles: Array.isArray(filtersRaw.roles) ? filtersRaw.roles as string[] : [],
      event_types: Array.isArray(filtersRaw.event_types)
        ? filtersRaw.event_types as AuditTrailResponse['filters']['event_types']
        : [
          'login',
          'system_admin_access',
          'system_admin_change',
          'report_access',
          'dashboard_access',
          'configuration_access',
          'configuration_change'
        ]
    }
  }
}

const formatDateTime = (value: string | null): string => {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

export default function AuditTrailPage() {
  const [auditData, setAuditData] = useState<AuditTrailResponse>(defaultData)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [eventType, setEventType] = useState<EventTypeFilter>('all')
  const [sapid, setSapid] = useState('')
  const [role, setRole] = useState('')
  const [statusFilter, setStatusFilter] = useState<LoginStatusFilter>('all')
  const [search, setSearch] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)

  const filteredStats = useMemo(() => {
    return {
      total: auditData.summary.total_events,
      login: auditData.summary.total_logins,
      loginSuccess: auditData.summary.successful_logins,
      loginFailed: auditData.summary.failed_logins,
      adminAccess: auditData.summary.admin_access_events ?? 0,
      adminChange: auditData.summary.admin_change_events ?? 0,
      reportAccess: auditData.summary.report_access_events ?? 0,
      dashboardAccess: auditData.summary.dashboard_access_events ?? 0,
      configurationAccess: auditData.summary.configuration_access_events ?? 0,
      configurationChange: auditData.summary.configuration_change_events ?? 0,
      uniqueUsers: auditData.summary.unique_users,
      uniqueTargets: auditData.summary.unique_targets ?? 0
    }
  }, [auditData.summary])

  const loginSuccessRate = useMemo(() => {
    if (filteredStats.login === 0) return 0
    return Math.round((filteredStats.loginSuccess / filteredStats.login) * 100)
  }, [filteredStats.login, filteredStats.loginSuccess])

  const trendData = useMemo(() => {
    return auditData.summary.by_day.map((item) => ({
      ...item,
      login: (typeof item.successful === 'number' ? item.successful : 0)
        + (typeof item.failed === 'number' ? item.failed : 0)
    }))
  }, [auditData.summary.by_day])

  const cardMetrics = useMemo<CardMetric[]>(() => {
    if (eventType === 'login') {
      return [
        { label: 'Total Logins', value: filteredStats.login, icon: 'login' as const },
        { label: 'Successful Logins', value: filteredStats.loginSuccess, icon: 'success' as const },
        { label: 'Failed Logins', value: filteredStats.loginFailed, icon: 'error' as const },
        {
          label: 'Unique Users',
          value: filteredStats.uniqueUsers,
          caption: `Success Rate: ${loginSuccessRate}%`,
          icon: 'admin' as const
        }
      ]
    }

    if (eventType === 'system_admin_access') {
      return [
        { label: 'Admin Access Events', value: filteredStats.adminAccess, icon: 'admin' as const },
        { label: 'Unique Actors', value: filteredStats.uniqueUsers, icon: 'admin' as const },
        { label: 'Unique Routes', value: filteredStats.uniqueTargets, icon: 'success' as const },
        { label: 'Filtered Events', value: filteredStats.total, icon: 'login' as const }
      ]
    }

    if (eventType === 'system_admin_change') {
      return [
        { label: 'Admin Change Events', value: filteredStats.adminChange, icon: 'admin' as const },
        { label: 'Unique Actors', value: filteredStats.uniqueUsers, icon: 'admin' as const },
        { label: 'Impacted Routes', value: filteredStats.uniqueTargets, icon: 'warning' as const },
        { label: 'Filtered Events', value: filteredStats.total, icon: 'login' as const }
      ]
    }

    if (eventType === 'report_access') {
      return [
        { label: 'Report Access Events', value: filteredStats.reportAccess, icon: 'success' as const },
        { label: 'Unique Actors', value: filteredStats.uniqueUsers, icon: 'admin' as const },
        { label: 'Unique Reports', value: filteredStats.uniqueTargets, icon: 'login' as const },
        { label: 'Filtered Events', value: filteredStats.total, icon: 'warning' as const }
      ]
    }

    if (eventType === 'dashboard_access') {
      return [
        { label: 'Dashboard Access Events', value: filteredStats.dashboardAccess, icon: 'success' as const },
        { label: 'Unique Actors', value: filteredStats.uniqueUsers, icon: 'admin' as const },
        { label: 'Unique Dashboards', value: filteredStats.uniqueTargets, icon: 'login' as const },
        { label: 'Filtered Events', value: filteredStats.total, icon: 'warning' as const }
      ]
    }

    if (eventType === 'configuration_access') {
      return [
        { label: 'Configuration Access', value: filteredStats.configurationAccess, icon: 'admin' as const },
        { label: 'Unique Actors', value: filteredStats.uniqueUsers, icon: 'admin' as const },
        { label: 'Unique Routes', value: filteredStats.uniqueTargets, icon: 'success' as const },
        { label: 'Filtered Events', value: filteredStats.total, icon: 'login' as const }
      ]
    }

    if (eventType === 'configuration_change') {
      return [
        { label: 'Configuration Changes', value: filteredStats.configurationChange, icon: 'warning' as const },
        { label: 'Unique Actors', value: filteredStats.uniqueUsers, icon: 'admin' as const },
        { label: 'Impacted Routes', value: filteredStats.uniqueTargets, icon: 'warning' as const },
        { label: 'Filtered Events', value: filteredStats.total, icon: 'login' as const }
      ]
    }

    return [
      { label: 'Total Events', value: filteredStats.total, icon: 'login' as const },
      { label: 'Login Events', value: filteredStats.login, icon: 'success' as const },
      { label: 'Admin Access', value: filteredStats.adminAccess, icon: 'admin' as const },
      { label: 'Admin Changes', value: filteredStats.adminChange, icon: 'warning' as const }
    ]
  }, [eventType, filteredStats, loginSuccessRate])

  const loadAuditData = async (pageOverride?: number, rowsPerPageOverride?: number) => {
    setLoading(true)
    setError(null)

    try {
      const effectivePage = pageOverride ?? page
      const effectiveRowsPerPage = rowsPerPageOverride ?? rowsPerPage
      const payload = await auditTrailApi.listEvents({
        event_type: eventType,
        sapid: sapid || undefined,
        role: role || undefined,
        success: eventType === 'login' && statusFilter !== 'all' ? statusFilter === 'success' : undefined,
        search: search || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        offset: effectivePage * effectiveRowsPerPage,
        limit: effectiveRowsPerPage
      })
      const normalized = normalizeAuditPayload(payload)
      if (!normalized) {
        setError('Audit trail API returned an unexpected response. Restart backend to load the latest routes.')
        setAuditData(defaultData)
        return
      }
      setAuditData(normalized)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to load audit trail events')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (eventType !== 'login' && statusFilter !== 'all') {
      setStatusFilter('all')
      return
    }
    setPage(0)
    loadAuditData(0)
  }, [eventType, statusFilter])

  useEffect(() => {
    loadAuditData()
  }, [page, rowsPerPage])

  const handleApplyFilters = async () => {
    setPage(0)
    await loadAuditData(0)
  }

  const handleResetFilters = async () => {
    setEventType('all')
    setSapid('')
    setRole('')
    setStatusFilter('all')
    setSearch('')
    setStartDate('')
    setEndDate('')
    setPage(0)

    setLoading(true)
    setError(null)
    try {
      const payload = await auditTrailApi.listEvents({ event_type: 'all', offset: 0, limit: rowsPerPage })
      const normalized = normalizeAuditPayload(payload)
      if (!normalized) {
        setError('Audit trail API returned an unexpected response. Restart backend to load the latest routes.')
        setAuditData(defaultData)
        return
      }
      setAuditData(normalized)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to load audit trail events')
    } finally {
      setLoading(false)
    }
  }

  const handlePageChange = (_event: unknown, nextPage: number) => {
    setPage(nextPage)
  }

  const handleRowsPerPageChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextRowsPerPage = parseInt(event.target.value, 10)
    setRowsPerPage(nextRowsPerPage)
    setPage(0)
  }

  return (
    <Container maxWidth="xl">
      <Stack spacing={3}>
        <Box>
          <Typography variant="h4" gutterBottom>
            Audit Trail Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Monitor logins, dashboard usage, report access, and configuration activity across the platform.
          </Typography>
        </Box>

        {error && <Alert severity="error">{error}</Alert>}

        <Paper sx={{ p: 2 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                select
                fullWidth
                size="small"
                label="Event Type"
                value={eventType}
                onChange={(event) => setEventType(event.target.value as EventTypeFilter)}
              >
                <MenuItem value="login">Logins</MenuItem>
                <MenuItem value="system_admin_access">System Admin Access</MenuItem>
                <MenuItem value="system_admin_change">System Admin Changes</MenuItem>
                <MenuItem value="report_access">Report Access</MenuItem>
                <MenuItem value="dashboard_access">Dashboard Access</MenuItem>
                <MenuItem value="configuration_access">Configuration Access</MenuItem>
                <MenuItem value="configuration_change">Configuration Changes</MenuItem>
                <MenuItem value="all">All Event Types</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                select
                fullWidth
                size="small"
                label="SAPID"
                value={sapid}
                onChange={(event) => setSapid(event.target.value)}
              >
                <MenuItem value="">All Users</MenuItem>
                {auditData.filters.sapids.map((item) => (
                  <MenuItem key={item} value={item}>{item}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                select
                fullWidth
                size="small"
                label="Role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
              >
                <MenuItem value="">All Roles</MenuItem>
                {auditData.filters.roles.map((item) => (
                  <MenuItem key={item} value={item}>{item}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                select
                fullWidth
                size="small"
                label="Login Status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as LoginStatusFilter)}
                disabled={eventType !== 'login'}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="success">Successful</MenuItem>
                <MenuItem value="failed">Failed</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                label="Start Date"
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                label="End Date"
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                size="small"
                label="Search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="SAPID, name, path, change"
              />
            </Grid>
            <Grid item xs={12}>
              <Stack direction="row" spacing={1}>
                <Button
                  variant="contained"
                  onClick={handleApplyFilters}
                  startIcon={<QueryStatsIcon />}
                  disabled={loading}
                >
                  Apply Filters
                </Button>
                <Button
                  variant="outlined"
                  onClick={handleResetFilters}
                  startIcon={<RefreshIcon />}
                  disabled={loading}
                >
                  Reset
                </Button>
              </Stack>
            </Grid>
          </Grid>
        </Paper>

        <Grid container spacing={2}>
          {cardMetrics.map((metric) => (
            <Grid item xs={12} sm={6} md={3} key={metric.label}>
              <Card>
                <CardContent>
                  <Stack direction="row" spacing={1} alignItems="center">
                    {metric.icon === 'admin' && <AdminPanelSettingsIcon color="secondary" />}
                    {metric.icon === 'warning' && <WarningAmberIcon color="warning" />}
                    {metric.icon === 'error' && <WarningAmberIcon color="error" />}
                    {metric.icon === 'success' && <LoginIcon sx={{ color: 'success.main' }} />}
                    {metric.icon === 'login' && <LoginIcon color="primary" />}
                    <Typography variant="subtitle2" color="text.secondary">{metric.label}</Typography>
                  </Stack>
                  <Typography variant="h5">{metric.value}</Typography>
                  {metric.caption && (
                    <Typography variant="caption" color="text.secondary">
                      {metric.caption}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>Audit Trend (Daily)</Typography>
          <Box sx={{ width: '100%', height: 280 }}>
            {loading ? (
              <Stack direction="row" alignItems="center" justifyContent="center" sx={{ height: '100%' }}>
                <CircularProgress size={28} />
              </Stack>
            ) : (
              <ResponsiveContainer>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="login" stroke="#2e7d32" strokeWidth={2} name="Login" />
                  <Line type="monotone" dataKey="admin_access" stroke="#1565c0" strokeWidth={2} name="Admin Access" />
                  <Line type="monotone" dataKey="admin_change" stroke="#6d4c41" strokeWidth={2} name="Admin Change" />
                  <Line type="monotone" dataKey="report_access" stroke="#00897b" strokeWidth={2} name="Report Access" />
                  <Line type="monotone" dataKey="dashboard_access" stroke="#5e35b1" strokeWidth={2} name="Dashboard Access" />
                  <Line type="monotone" dataKey="configuration_access" stroke="#ef6c00" strokeWidth={2} name="Configuration Access" />
                  <Line type="monotone" dataKey="configuration_change" stroke="#c62828" strokeWidth={2} name="Configuration Changes" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Box>
        </Paper>

        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 2 }}>
              <Typography variant="h6" gutterBottom>Top Actors</Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>SAPID</TableCell>
                    <TableCell align="right">Events</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {auditData.summary.top_users.map((item) => (
                    <TableRow key={item.sapid}>
                      <TableCell>
                        <Typography variant="body2">{item.sapid}</Typography>
                        <Typography variant="caption" color="text.secondary">{item.name || '-'}</Typography>
                      </TableCell>
                      <TableCell align="right">{item.count}</TableCell>
                    </TableRow>
                  ))}
                  {auditData.summary.top_users.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={2}>
                        <Typography variant="body2" color="text.secondary">No data found</Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </Paper>
          </Grid>

          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 2 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="h6">Audit Events</Typography>
                <Typography variant="body2" color="text.secondary">
                  Showing {auditData.data.length} of {auditData.total_filtered}
                </Typography>
              </Stack>

              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Time</TableCell>
                    <TableCell>SAPID</TableCell>
                    <TableCell>User</TableCell>
                    <TableCell>Role</TableCell>
                    <TableCell>Event</TableCell>
                    <TableCell>Status / Detail</TableCell>
                    <TableCell>IP</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {auditData.data.map((item, idx) => (
                    <TableRow key={`${item.timestamp}-${item.sapid}-${idx}`}>
                      <TableCell>{formatDateTime(item.timestamp)}</TableCell>
                      <TableCell>{item.sapid || '-'}</TableCell>
                      <TableCell>{item.user_name || '-'}</TableCell>
                      <TableCell>{item.role || '-'}</TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={item.event_type}
                          color={
                            item.event_type === 'system_admin_change' || item.event_type === 'configuration_change'
                              ? 'warning'
                              : (
                                item.event_type === 'system_admin_access' ||
                                item.event_type === 'report_access' ||
                                item.event_type === 'dashboard_access' ||
                                item.event_type === 'configuration_access'
                              )
                                ? 'info'
                                : 'default'
                          }
                        />
                        <Typography variant="caption" sx={{ display: 'block' }}>{item.event_name || '-'}</Typography>
                      </TableCell>
                      <TableCell>
                        {item.event_type === 'login' ? (
                          <Chip
                            size="small"
                            color={item.success ? 'success' : 'error'}
                            label={item.success ? 'Successful' : (item.failure_reason || 'Failed')}
                          />
                        ) : (
                          <Typography variant="caption" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                            {item.details ? JSON.stringify(item.details) : '-'}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>{item.ip_address || '-'}</TableCell>
                    </TableRow>
                  ))}
                  {auditData.data.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={7}>
                        <Typography variant="body2" color="text.secondary">No audit events found for current filters</Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
              <TablePagination
                component="div"
                count={auditData.total_filtered}
                page={page}
                onPageChange={handlePageChange}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleRowsPerPageChange}
                rowsPerPageOptions={[10, 25, 50, 100]}
              />
            </Paper>
          </Grid>
        </Grid>

        <Typography variant="caption" color="text.secondary">
          Last event observed: {formatDateTime(auditData.summary.last_event_at)}
        </Typography>
      </Stack>
    </Container>
  )
}
