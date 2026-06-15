import { useState, useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Container,
  Paper,
  Typography,
  Box,
  TextField,
  MenuItem,
  CircularProgress,
  Alert,
  Grid,
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Autocomplete,
  Avatar,
  Link,
  Tooltip,
  IconButton,
  Drawer,
  Divider,
  Stack
} from '@mui/material'
import PersonIcon from '@mui/icons-material/Person'
import BusinessIcon from '@mui/icons-material/Business'
import GroupsIcon from '@mui/icons-material/Groups'
import WorkIcon from '@mui/icons-material/Work'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import CleaningServicesIcon from '@mui/icons-material/CleaningServices'
import VerifiedIcon from '@mui/icons-material/Verified'
import CalendarTodayIcon from '@mui/icons-material/CalendarToday'
import InfoIcon from '@mui/icons-material/Info'
import CloseIcon from '@mui/icons-material/Close'
import BugReportIcon from '@mui/icons-material/BugReport'
import WarningIcon from '@mui/icons-material/Warning'
import { employeeDashboardApi, EmployeeOption, KPIPerformance, AssignedTask, DashboardTickerMessage } from '../services/employeeDashboardApi'
import { fetchAvailableDates } from '../services/teamDashboardApi'
import { JiraIssueTransitionsResponse, reportsApi } from '../services/reportsApi'
import { useAuth } from '../context/AuthContext'
import CategoryScoreGauge from '../components/CategoryScoreGauge'
import type { Employee } from '../types'

const ROG_COLORS = {
  green: '#66BB6A',
  orange: '#FFA726',
  red: '#EF5350',
  not_configured: 'grey.500'
}

const ROG_LABELS = {
  green: 'Green',
  orange: 'Orange',
  red: 'Red',
  not_configured: 'Not Configured'
}

const getGoalTypeIcon = (goalType: string) => {
  switch (goalType) {
    case 'Output':
      return <TrendingUpIcon sx={{ fontSize: 16, mr: 0.5 }} />
    case 'Input':
      return <TrendingDownIcon sx={{ fontSize: 16, mr: 0.5 }} />
    case 'Hygiene':
      return <CleaningServicesIcon sx={{ fontSize: 16, mr: 0.5 }} />
    case 'Quality':
      return <VerifiedIcon sx={{ fontSize: 16, mr: 0.5 }} />
    default:
      return null
  }
}

const getGoalTypeColor = (goalType: string): 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'default' => {
  switch (goalType) {
    case 'Output':
      return 'success'
    case 'Input':
      return 'info'
    case 'Hygiene':
      return 'warning'
    case 'Quality':
      return 'primary'
    default:
      return 'default'
  }
}

const CATEGORY_LABELS = {
  input: 'Input',
  output: 'Output',
  quality: 'Quality',
  hygiene: 'Hygiene'
}

function getProrateInfo(asOfDateInput: string, employeeStartDate?: string) {
  let ref: Date
  if (asOfDateInput && asOfDateInput.length === 10) {
    const [y, m, d] = asOfDateInput.split('-').map(Number)
    ref = new Date(y, m - 1, d)
  } else {
    ref = new Date()
  }
  const FISCAL_START = 4
  const refMonth = ref.getMonth() + 1
  const refYear = ref.getFullYear()
  const fyStartYear = refMonth >= FISCAL_START ? refYear : refYear - 1
  const fyStart = new Date(fyStartYear, FISCAL_START - 1, 1)
  const monthsSinceFY = ((refMonth - FISCAL_START) % 12 + 12) % 12
  const qNum = Math.floor(monthsSinceFY / 3)
  let qStartMonth = FISCAL_START + qNum * 3
  let qStartYear = fyStartYear
  if (qStartMonth > 12) { qStartMonth -= 12; qStartYear++ }
  const qStart = new Date(qStartYear, qStartMonth - 1, 1)

  let effectiveAnnualStart = fyStart
  let effectiveQStart = qStart
  let isPartialPeriod = false
  let joinDateFormatted = ''
  if (employeeStartDate && employeeStartDate.length === 10) {
    const [ey, em, ed] = employeeStartDate.split('-').map(Number)
    const empStart = new Date(ey, em - 1, ed)
    if (empStart > fyStart) effectiveAnnualStart = empStart
    if (empStart > qStart) effectiveQStart = empStart
    if (empStart > fyStart || empStart > qStart) {
      isPartialPeriod = true
      joinDateFormatted = empStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    }
  }

  const ms = 86400000
  const daysAnnual = Math.floor((ref.getTime() - effectiveAnnualStart.getTime()) / ms)
  const weeksAnnual = Math.min(Math.max(1, Math.ceil((daysAnnual + 1) / 7)), 52)
  const daysQ = Math.floor((ref.getTime() - effectiveQStart.getTime()) / ms)
  const weeksQ = Math.min(Math.max(1, Math.ceil((daysQ + 1) / 7)), 13)
  const annualPct = (weeksAnnual / 52 * 100).toFixed(1)
  const qPct = (weeksQ / 13 * 100).toFixed(1)
  const dateFormatted = ref.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  return { weeksAnnual, weeksQ, annualPct, qPct, dateFormatted, isPartialPeriod, joinDateFormatted }
}

function formatDateAsYyyyMmDd(value: string): string {
  const rawValue = String(value || '').trim()
  if (!rawValue) return 'NA'
  const isoPrefixMatch = rawValue.match(/^(\d{4}-\d{2}-\d{2})/)
  if (isoPrefixMatch) return isoPrefixMatch[1]
  const parsedDate = new Date(rawValue)
  if (Number.isNaN(parsedDate.getTime())) return rawValue
  return parsedDate.toISOString().slice(0, 10)
}

function formatDelayInDays(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value) || value < 0) return 'NA'
  return value.toFixed(1)
}

function getProfileValue(profile: any, keys: string[]): string {
  for (const key of keys) {
    const raw = profile?.[key]
    if (raw !== undefined && raw !== null) {
      const value = String(raw).trim()
      if (value && value.toLowerCase() !== 'nan') {
        return value
      }
    }
  }
  return ''
}

function mapDashboardProfileToEmployee(profile: any, selected: EmployeeOption | null): Employee {
  return {
    sapid: getProfileValue(profile, ['SAPID', 'sapid']) || String(selected?.sapid ?? '').trim(),
    name: getProfileValue(profile, ['Name', 'name']) || String(selected?.name ?? '').trim(),
    team: getProfileValue(profile, ['Team', 'team']) || String(selected?.team ?? '').trim(),
    scrum: getProfileValue(profile, ['Scrum', 'scrum']),
    primary_role: getProfileValue(profile, ['Primary Role', 'primary_role', 'primaryRole']),
    secondary_role: getProfileValue(profile, ['Secondary Role', 'secondary_role', 'secondaryRole']),
    manager: getProfileValue(profile, ['Manager', 'manager']),
    manager_name: getProfileValue(profile, ['Manager Name', 'manager_name', 'managerName']),
    email: getProfileValue(profile, ['Email', 'EMail', 'email']),
    jira_name: getProfileValue(profile, ['JIRA Name', 'Jira Name', 'jira_name', 'jiraName']),
    github_name: getProfileValue(profile, ['GitHub Name', 'GitHUB Name', 'github_name', 'githubName']),
    git_email: getProfileValue(profile, ['Git Email', 'GIT Email', 'git_email', 'gitEmail']),
    start_date: getProfileValue(profile, ['Start Date', 'start_date', 'startDate']),
    udeid: getProfileValue(profile, ['UDEID', 'udeid', 'UDE Id', 'UDE ID']),
    tacid: getProfileValue(profile, ['TACID', 'tacid', 'TAC Id', 'TAC ID'])
  }
}

function getTickerSeverityColors(severity: DashboardTickerMessage['severity']) {
  switch (severity) {
    case 'critical':
      return { bg: '#ffebee', fg: '#8b0000', border: '#ef9a9a' }
    case 'high':
      return { bg: '#fff3e0', fg: '#a04000', border: '#ffb74d' }
    case 'warning':
      return { bg: '#fff8e1', fg: '#8a6d1f', border: '#ffcc80' }
    case 'compliance':
      return { bg: '#ede7f6', fg: '#4527a0', border: '#b39ddb' }
    case 'low':
      return { bg: '#f1f8e9', fg: '#33691e', border: '#c5e1a5' }
    default:
      return { bg: '#e3f2fd', fg: '#0d47a1', border: '#90caf9' }
  }
}

export default function EmployeeDashboardPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { user } = useAuth()
  const [employees, setEmployees] = useState<EmployeeOption[]>([])
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeOption | null>(null)
  const [period, setPeriod] = useState('Annual')
  const [asOfDate, setAsOfDate] = useState<string>('')
  const [maxDate, setMaxDate] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const dateInputRef = useRef<HTMLInputElement>(null)
  const [loadingEmployees, setLoadingEmployees] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const [dashboardData, setDashboardData] = useState<any>(null)
  const [assignedTasks, setAssignedTasks] = useState<AssignedTask[]>([])
  const [loadingTasks, setLoadingTasks] = useState(false)

  // Issue transition history drawer state
  const [issueHistoryDialogOpen, setIssueHistoryDialogOpen] = useState(false)
  const [selectedTransitionIssueKey, setSelectedTransitionIssueKey] = useState('')
  const [issueTransitionsDetails, setIssueTransitionsDetails] = useState<JiraIssueTransitionsResponse | null>(null)
  const [loadingIssueTransitions, setLoadingIssueTransitions] = useState(false)
  const [issueTransitionsError, setIssueTransitionsError] = useState<string | null>(null)
  
  // Details drawer state
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false)
  const [employeeDetails, setEmployeeDetails] = useState<Employee | null>(null)

  const periods = ['Weekly', 'Quarterly', 'Annual']

  const toInputDate = (d: string): string =>
    d.length === 8 ? `${d.substring(0,4)}-${d.substring(4,6)}-${d.substring(6,8)}` : d

  const formatDisplayDate = (dateStr: string): string => {
    if (!dateStr || dateStr.length !== 10) return dateStr
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    const [year, month, day] = dateStr.split('-')
    return `${day}-${months[parseInt(month)-1]}-${year}`
  }

  // Load available dates on mount — used only to set a smart default
  useEffect(() => {
    fetchAvailableDates().then(dates => {
      if (dates.length > 0) {
        const latest = toInputDate(dates[0])
        setMaxDate(latest)
        // Default to the most recent date before today — today's data may be incomplete
        const todayStr = new Date().toISOString().slice(0, 10).replace(/-/g, '')
        const prevDate = dates.find(d => d < todayStr) ?? dates[0]
        setAsOfDate(toInputDate(prevDate))
      }
    }).catch(err => console.error('Failed to load available dates:', err))
  }, [])

  // Load employees on mount
  useEffect(() => {
    const loadEmployees = async () => {
      setLoadingEmployees(true)
      try {
        const response = await employeeDashboardApi.listEmployees()
        setEmployees(response.employees)
        
        const sapidParam = searchParams.get('sapid')
        const nameParam = searchParams.get('name')
        if (sapidParam && response.employees.length > 0) {
          const employee = response.employees.find(e => e.sapid === sapidParam)
          if (employee) {
            setSelectedEmployee(employee)
            return
          }
        }

        // Backward compatibility for old name-based links
        if (nameParam && response.employees.length > 0) {
          const matchingEmployees = response.employees.filter(e => e.name === nameParam)
          if (matchingEmployees.length === 1) {
            setSelectedEmployee(matchingEmployees[0])
          } else if (matchingEmployees.length > 1) {
            setError(`Multiple employees named ${nameParam} found. Please select by SAPID.`)
          }
        }
      } catch (err: any) {
        console.error('Failed to load employees:', err)
        setError('Failed to load employee list')
      } finally {
        setLoadingEmployees(false)
      }
    }
    loadEmployees()
  }, [searchParams])

  // Load dashboard data when employee or period or date changes
  useEffect(() => {
    if (!selectedEmployee) return
    const timer = setTimeout(() => { 
      loadDashboardData()
      loadAssignedTasks()
    }, 400)
    return () => clearTimeout(timer)
  }, [selectedEmployee, period, asOfDate])

  const loadDashboardData = async () => {
    if (!selectedEmployee) return
    
    setLoading(true)
    setError(null)
    try {
      const data = await employeeDashboardApi.getEmployeeDashboard(selectedEmployee.sapid, period, asOfDate ? asOfDate.replace(/-/g, '') : '')
      setDashboardData(data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load employee dashboard')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const loadAssignedTasks = async () => {
    if (!selectedEmployee) return
    
    setLoadingTasks(true)
    try {
      const response = await employeeDashboardApi.getAssignedTasks(selectedEmployee.sapid)
      setAssignedTasks(response.tasks || [])
    } catch (err: any) {
      console.error('Failed to load assigned tasks:', err)
      setAssignedTasks([])
    } finally {
      setLoadingTasks(false)
    }
  }

  const getTeamColor = (team: string) => {
    const colors: Record<string, string> = {
      'OOSM': '#2196f3',
      'APM-Core': '#4caf50',
      'FSO': '#ff9800',
      'DCEM': '#9c27b0',
      'R&D': '#f44336',
      'UDM/Support': '#00bcd4',
      'APM-RUM': '#795548'
    }
    return colors[team] || '#757575'
  }

  const canOpenIssueTransitionHistory = (() => {
    if (!user || !dashboardData?.employee?.Team) return false
    const currentTeam = String(dashboardData.employee.Team).trim()
    if (user.role === 'Admin') return true
    return user.role === 'Team Manager' && (user.team_ids || []).includes(currentTeam)
  })()

  const loadIssueTransitions = async (issueKey: string) => {
    const selectedIssue = String(issueKey || '').trim()
    if (!selectedIssue) return

    setSelectedTransitionIssueKey(selectedIssue)
    setLoadingIssueTransitions(true)
    setIssueTransitionsError(null)

    try {
      const data = await reportsApi.getJiraIssueTransitions(selectedIssue)
      setIssueTransitionsDetails(data)
    } catch (err: any) {
      setIssueTransitionsDetails(null)
      setIssueTransitionsError(err.response?.data?.detail || 'Failed to load issue transition history')
    } finally {
      setLoadingIssueTransitions(false)
    }
  }

  const handleOpenIssueTransitionHistory = (issueKey: string) => {
    if (!canOpenIssueTransitionHistory) return
    setIssueHistoryDialogOpen(true)
    loadIssueTransitions(issueKey)
  }

  const handleViewEmployeeDetails = () => {
    if (!dashboardData?.employee && !selectedEmployee) return

    setEmployeeDetails(mapDashboardProfileToEmployee(dashboardData?.employee, selectedEmployee))
    setDetailsDrawerOpen(true)
  }

  const prorateInfo = getProrateInfo(asOfDate, dashboardData?.employee_start_date)

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <PersonIcon sx={{ fontSize: 32, color: 'primary.main' }} />
            <Typography variant="h4">
              Employee Dashboard
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary">
            Comprehensive performance view for individual employees
          </Typography>
        </Box>

        {/* Employee Selection and Period Filter */}
        <Box sx={{ mb: 3 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Autocomplete
                options={employees}
                value={selectedEmployee}
                onChange={(_, newValue) => {
                  setSelectedEmployee(newValue)
                  if (newValue?.sapid) {
                    navigate(`/dashboard/employee?sapid=${encodeURIComponent(newValue.sapid)}`, { replace: true })
                  } else {
                    navigate('/dashboard/employee', { replace: true })
                  }
                }}
                isOptionEqualToValue={(option, value) => option.sapid === value.sapid}
                getOptionLabel={(option) => `${option.name} (${option.sapid}) - ${option.team}`}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Select Employee"
                    placeholder="Search by name, SAPID, or team"
                  />
                )}
                loading={loadingEmployees}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                select
                fullWidth
                label="Period"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                disabled={!selectedEmployee}
              >
                {periods.map((p) => (
                  <MenuItem key={p} value={p}>{p}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} md={3} sx={{ display: 'flex', alignItems: 'center' }}>
              <Box onClick={() => dateInputRef.current?.showPicker?.()} sx={{ position: 'relative', display: 'inline-flex', alignItems: 'center', gap: 0.5, cursor: 'pointer', py: 1, px: 0.5 }}>
                <CalendarTodayIcon fontSize="small" sx={{ color: asOfDate !== maxDate ? 'primary.main' : 'text.disabled' }} />
                <Typography variant="caption" sx={{ color: asOfDate !== maxDate ? 'primary.main' : 'text.secondary', userSelect: 'none', whiteSpace: 'nowrap' }}>
                  {asOfDate && asOfDate !== maxDate ? `As on ${formatDisplayDate(asOfDate)}` : 'Latest'}
                </Typography>
                <input
                  ref={dateInputRef}
                  type="date"
                  value={asOfDate}
                  max={maxDate}
                  onChange={(e) => setAsOfDate(e.target.value)}
                  disabled={!selectedEmployee}
                  style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%' }}
                />
              </Box>
            </Grid>
          </Grid>
        </Box>

        {/* Error Message */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Loading State */}
        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        )}

        {/* Dashboard Content */}
        {!loading && dashboardData && (
          <>
            {dashboardData.inactive && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                {dashboardData.message || 'Employee is marked inactive. Dashboard is unavailable.'}
              </Alert>
            )}

            {/* Employee Profile Card */}
            <Card sx={{ mb: 3, bgcolor: '#f5f5f5' }}>
              <CardContent>
                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                      <Avatar sx={{ width: 64, height: 64, bgcolor: 'primary.main' }}>
                        <PersonIcon sx={{ fontSize: 40 }} />
                      </Avatar>
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="h5" fontWeight={600}>
                          {dashboardData.employee.Name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          SAPID: {dashboardData.employee.SAPID}
                        </Typography>
                      </Box>
                      <Tooltip title="View employee details">
                        <IconButton
                          onClick={handleViewEmployeeDetails}
                          size="small"
                          sx={{ alignSelf: 'flex-start' }}
                        >
                          <InfoIcon sx={{ fontSize: 20 }} />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <BusinessIcon fontSize="small" color="action" />
                        <Typography variant="body2">
                          <strong>Team:</strong>{' '}
                          <Link 
                            component="button"
                            variant="body2"
                            onClick={() => navigate(`/dashboard/team?team=${encodeURIComponent(dashboardData.employee.Team)}`)}
                            sx={{ cursor: 'pointer', textDecoration: 'none' }}
                          >
                            {dashboardData.employee.Team}
                          </Link>
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <GroupsIcon fontSize="small" color="action" />
                        <Typography variant="body2">
                          <strong>Scrum:</strong>{' '}
                          <Link 
                            component="button"
                            variant="body2"
                            onClick={() => navigate(`/dashboard/scrum?scrum=${encodeURIComponent(dashboardData.employee.Scrum)}`)}
                            sx={{ cursor: 'pointer', textDecoration: 'none' }}
                          >
                            {dashboardData.employee.Scrum}
                          </Link>
                        </Typography>
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <WorkIcon fontSize="small" color="action" />
                        <Typography variant="body2">
                          <strong>Role:</strong> {dashboardData.employee['Primary Role']}
                          {dashboardData.employee['Secondary Role'] && ` / ${dashboardData.employee['Secondary Role']}`}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>

            {/* Message Ticker */}
            {!dashboardData.inactive && Array.isArray(dashboardData.ticker_messages) && dashboardData.ticker_messages.length > 0 && (
              <Box
                sx={{
                  mb: 3,
                  border: '1px solid',
                  borderColor: 'divider',
                  borderRadius: 1,
                  overflow: 'hidden',
                  bgcolor: 'background.paper',
                }}
              >
                <Box
                  sx={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    py: 1,
                    whiteSpace: 'nowrap',
                    minWidth: '100%',
                    animation: 'employeeTicker 40s linear infinite',
                    '@keyframes employeeTicker': {
                      '0%': { transform: 'translateX(100%)' },
                      '100%': { transform: 'translateX(-100%)' },
                    },
                  }}
                >
                  {dashboardData.ticker_messages.map((message: DashboardTickerMessage) => {
                    const colors = getTickerSeverityColors(message.severity)
                    return (
                      <Chip
                        key={message.id}
                        label={message.text}
                        sx={{
                          mx: 1,
                          bgcolor: colors.bg,
                          color: colors.fg,
                          border: '1px solid',
                          borderColor: colors.border,
                          fontWeight: 600,
                        }}
                      />
                    )
                  })}
                </Box>
              </Box>
            )}

            {/* Category Score Gauges - All in Single Row */}
            {!dashboardData.inactive && <Box sx={{ mb: 3 }}>
              <Typography variant="h6" gutterBottom>
                Performance Score - {period}
              </Typography>
              {dashboardData.score && (() => {
                // Get thresholds from score data
                const thresholds = dashboardData.score.score_display_thresholds || { green_min: 71, orange_min: 36, red_max: 35 };
                
                // Helper to determine status based on score
                const getScoreStatus = (score: number): 'green' | 'orange' | 'red' => {
                  if (score >= thresholds.green_min) return 'green';
                  if (score >= thresholds.orange_min) return 'orange';
                  return 'red';
                };
                
                return (
                  <Grid container spacing={2}>
                    {/* Overall Score */}
                    <Grid item xs={12} sm={6} md={2.4}>
                      <CategoryScoreGauge
                        category="Overall Score"
                        score={dashboardData.score.overall_score}
                        maxScore={dashboardData.score.max_score}
                        rogStatus={getScoreStatus(dashboardData.score.overall_score)}
                        isOverall={true}
                      />
                    </Grid>

                    {/* Category Scores */}
                    {Object.entries(dashboardData.category_status).map(([category]) => {
                      // Capitalize first letter to match backend keys (Input, Output, Quality, Hygiene)
                      const capitalizedCategory = category.charAt(0).toUpperCase() + category.slice(1);
                      const categoryData = dashboardData.score.categories[capitalizedCategory as keyof typeof dashboardData.score.categories];
                      const categoryScore = categoryData?.score || 0;
                      const categoryWeightage = categoryData?.weightage || 0;
                      // Calculate percentage for category to determine color
                      const categoryPercentage = categoryWeightage > 0 ? (categoryScore / categoryWeightage) * 100 : 0;
                      return (
                        <Grid item xs={12} sm={6} md={2.4} key={category}>
                          <CategoryScoreGauge
                            category={capitalizedCategory}
                            score={categoryScore}
                            maxScore={categoryWeightage}
                            rogStatus={getScoreStatus(categoryPercentage)}
                          />
                        </Grid>
                      );
                    })}
                  </Grid>
                );
              })()}
            </Box>}

            {/* KPI Performance Table */}
            {!dashboardData.inactive && <Box>
              <Typography variant="h6" gutterBottom>
                KPI Performance Details
              </Typography>
              <Chip 
                label={`${dashboardData.total_kpis} KPIs`} 
                color="primary" 
                size="small" 
                sx={{ mb: 2 }}
              />
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 'bold' }}>Goal Type</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Role</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>KPI ID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>KPI Name</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Direction</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold' }}>Actual</TableCell>
                      <Tooltip
                        title={
                          <Box sx={{ p: 0.5 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5 }}>Target Prorating as of {prorateInfo.dateFormatted}</Typography>
                            <Typography variant="body2">Quarterly: Week {prorateInfo.weeksQ}/13 ({prorateInfo.qPct}%)</Typography>
                            <Typography variant="body2">Annual: Week {prorateInfo.weeksAnnual}/52 ({prorateInfo.annualPct}%)</Typography>
                            <Typography variant="body2" sx={{ mt: 0.5, fontStyle: 'italic' }}>Weekly &amp; Monthly: not prorated</Typography>
                            {prorateInfo.isPartialPeriod && (
                              <Typography variant="body2" sx={{ mt: 0.5, color: 'warning.light', fontWeight: 'bold' }}>⚠ Partial period — joined {prorateInfo.joinDateFormatted}</Typography>
                            )}
                          </Box>
                        }
                        arrow
                        placement="top"
                      >
                        <TableCell align="right" sx={{ fontWeight: 'bold', cursor: 'help' }}>Target</TableCell>
                      </Tooltip>
                      <TableCell align="right" sx={{ fontWeight: 'bold' }}>%</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {dashboardData.kpi_performance.map((kpi: KPIPerformance, idx: number) => {
                      // Build tooltip content
                      const tooltipContent = (
                        <Box sx={{ p: 0.5 }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5 }}>
                            {kpi.kpi_id}: {kpi.kpi_name}
                          </Typography>
                          {kpi.measurement_criteria && (
                            <Typography variant="body2" sx={{ mb: 0.5 }}>
                              <strong>Measurement:</strong> {kpi.measurement_criteria}
                            </Typography>
                          )}
                          {kpi.tool && (
                            <Typography variant="body2" sx={{ mb: 0.5 }}>
                              <strong>Tool:</strong> {kpi.tool}
                            </Typography>
                          )}
                          {kpi.measure && (
                            <Typography variant="body2">
                              <strong>Measure:</strong> {kpi.measure}
                            </Typography>
                          )}
                        </Box>
                      )

                      return (
                      <TableRow key={idx} hover>
                        <TableCell>
                          <Chip 
                            label={CATEGORY_LABELS[kpi.category as keyof typeof CATEGORY_LABELS]} 
                            size="small"
                            sx={{ fontSize: '0.7rem' }}
                          />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={kpi.role_type} 
                            size="small" 
                            variant="outlined"
                            color={
                              kpi.role_type === 'Primary' ? 'primary' : 
                              kpi.role_type === 'Secondary' ? 'secondary' : 
                              'default'
                            }
                          />
                        </TableCell>
                        <Tooltip title={tooltipContent} arrow placement="top">
                          <TableCell sx={{ cursor: 'help' }}>{kpi.kpi_id}</TableCell>
                        </Tooltip>
                        <Tooltip title={tooltipContent} arrow placement="top">
                          <TableCell sx={{ cursor: 'help' }}>{kpi.kpi_name}</TableCell>
                        </Tooltip>
                        <TableCell>
                          <Chip 
                            icon={getGoalTypeIcon(kpi.goal_type) || undefined}
                            label={kpi.goal_type} 
                            size="small" 
                            variant="outlined"
                            color={getGoalTypeColor(kpi.goal_type)}
                          />
                        </TableCell>
                        <TableCell align="right">{kpi.actual != null ? kpi.actual.toFixed(1) : '-'}</TableCell>
                        <Tooltip
                          title={
                            kpi.prorated_target !== undefined && kpi.period && !['Weekly', 'Monthly'].includes(kpi.period) && kpi.prorate !== false
                              ? (
                                <Box sx={{ p: 0.5 }}>
                                  <Typography variant="body2">
                                    Prorated: {kpi.prorated_target.toFixed(1)}
                                    {' '}({kpi.period === 'Quarterly'
                                      ? `Week ${prorateInfo.weeksQ}/13, ${prorateInfo.qPct}%`
                                      : `Week ${prorateInfo.weeksAnnual}/52, ${prorateInfo.annualPct}%`})
                                  </Typography>
                                  {prorateInfo.isPartialPeriod && (
                                    <Typography variant="body2" sx={{ mt: 0.5, color: 'warning.light', fontWeight: 'bold' }}>⚠ Partial period — joined {prorateInfo.joinDateFormatted}</Typography>
                                  )}
                                </Box>
                              )
                              : ''
                          }
                          arrow
                          placement="top"
                          disableHoverListener={kpi.prorated_target === undefined || ['Weekly', 'Monthly'].includes(kpi.period ?? '') || kpi.prorate === false}
                        >
                          <TableCell align="right" sx={{ cursor: (kpi.period && !['Weekly', 'Monthly'].includes(kpi.period)) ? 'help' : 'default' }}>
                            {kpi.target.toFixed(1)}
                          </TableCell>
                        </Tooltip>
                        <TableCell align="right">{kpi.percentage != null ? `${kpi.percentage.toFixed(0)}%` : '-'}</TableCell>
                        <TableCell align="center">
                          <Tooltip
                            title={
                              kpi.rog_status === 'not_configured'
                                ? 'This KPI is not configured for this team and is excluded from score calculation.'
                                : 'KPI status based on actual vs target.'
                            }
                            arrow
                            placement="top"
                          >
                            <Chip
                              label={ROG_LABELS[kpi.rog_status as keyof typeof ROG_LABELS] || kpi.rog_status}
                              size="small"
                              sx={{
                                bgcolor: ROG_COLORS[kpi.rog_status as keyof typeof ROG_COLORS] || 'grey.500',
                                color: 'white',
                                fontWeight: 600
                              }}
                            />
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>}

            {/* Assigned Tasks Section */}
            {!dashboardData.inactive && <Box sx={{ mt: 4 }}>
              <Typography variant="h6" gutterBottom>
                Assigned Tasks
              </Typography>
              {loadingTasks ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress />
                </Box>
              ) : assignedTasks.length === 0 ? (
                <Box sx={{ py: 3, textAlign: 'center' }}>
                  <BugReportIcon sx={{ fontSize: 50, color: 'text.disabled', mb: 2 }} />
                  <Typography variant="body2" color="text.secondary">
                    No assigned tasks currently
                  </Typography>
                </Box>
              ) : (
                <TableContainer component={Paper} sx={{ borderRadius: 1 }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow sx={{ bgcolor: 'grey.100' }}>
                        <TableCell><strong>Issue Key</strong></TableCell>
                        <TableCell><strong>Summary</strong></TableCell>
                        <TableCell><strong>Status</strong></TableCell>
                        <TableCell><strong>Issue Type</strong></TableCell>
                        <TableCell><strong>Priority</strong></TableCell>
                        <TableCell><strong>Due Date</strong></TableCell>
                        <TableCell align="center"><strong>Status</strong></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {assignedTasks.map((task) => (
                        <TableRow key={task.key} sx={{ '&:hover': { bgcolor: 'grey.50' } }}>
                          <TableCell>
                            {canOpenIssueTransitionHistory ? (
                              <Link
                                component="button"
                                variant="body2"
                                onClick={() => handleOpenIssueTransitionHistory(task.key)}
                                sx={{ textDecoration: 'none' }}
                              >
                                <Chip
                                  label={task.key}
                                  size="small"
                                  variant="outlined"
                                  color="secondary"
                                  clickable
                                />
                              </Link>
                            ) : (
                              <Tooltip title="Only Admin or Team Manager of this team can view issue transition history">
                                <span>
                                  <Chip
                                    label={task.key}
                                    size="small"
                                    variant="outlined"
                                  />
                                </span>
                              </Tooltip>
                            )}
                          </TableCell>
                          <TableCell sx={{ maxWidth: 300 }}>
                            <Typography variant="body2" title={task.summary}>
                              {task.summary.length > 50 ? task.summary.substring(0, 50) + '...' : task.summary}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={task.status}
                              size="small"
                              variant="filled"
                              color={task.status.toLowerCase() === 'in progress' ? 'info' : 'default'}
                            />
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={task.issue_type}
                              size="small"
                              variant="outlined"
                              color="default"
                            />
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={task.priority}
                              size="small"
                              color={
                                task.priority === 'Highest' ? 'error' :
                                task.priority === 'High' ? 'warning' :
                                'default'
                              }
                              variant="filled"
                            />
                          </TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <CalendarTodayIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                              <Typography variant="body2">
                                {task.due_date || '—'}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="center">
                            {task.is_delayed ? (
                              <Tooltip title={`${task.days_delayed} days overdue`}>
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                                  <WarningIcon sx={{ fontSize: 18, color: 'error.main' }} />
                                  <Typography variant="caption" color="error" fontWeight={600}>
                                    {task.days_delayed}d Delayed
                                  </Typography>
                                </Box>
                              </Tooltip>
                            ) : task.due_date && task.due_date !== 'No due date' ? (
                              <Chip
                                label="On Track"
                                size="small"
                                color="success"
                                variant="filled"
                              />
                            ) : (
                              <Chip
                                label="No Plan"
                                size="small"
                                color="default"
                                variant="outlined"
                              />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </Box>}
          </>
        )}

        {/* No Selection State */}
        {!loading && !dashboardData && !error && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <PersonIcon sx={{ fontSize: 80, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary">
              Select an employee to view their dashboard
            </Typography>
          </Box>
        )}

        {/* Issue Transition History Drawer */}
        <Drawer
          anchor="right"
          open={issueHistoryDialogOpen}
          onClose={() => setIssueHistoryDialogOpen(false)}
          sx={{ zIndex: (muiTheme) => muiTheme.zIndex.modal + 5 }}
          PaperProps={{
            sx: {
              width: { xs: '100%', md: 720 },
              p: 2.5,
              display: 'flex',
              flexDirection: 'column'
            }
          }}
        >
          <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
              <Typography variant="h6">Issue Transition History</Typography>
              <IconButton size="small" onClick={() => setIssueHistoryDialogOpen(false)}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>

            {selectedTransitionIssueKey && (
              <Chip
                label={`Issue: ${selectedTransitionIssueKey}`}
                color="secondary"
                variant="outlined"
                size="small"
                sx={{ mb: 1.5 }}
              />
            )}

            {loadingIssueTransitions ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
                <CircularProgress size={24} />
              </Box>
            ) : issueTransitionsError ? (
              <Alert severity="error" sx={{ mb: 1 }}>{issueTransitionsError}</Alert>
            ) : issueTransitionsDetails ? (
              <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
                <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                  <Chip label={`Delay: ${formatDelayInDays(issueTransitionsDetails.delay_computation.delay_days)}d`} size="small" variant="outlined" />
                  <Chip label={`Basis: ${issueTransitionsDetails.delay_computation.basis}`} size="small" variant="outlined" />
                </Stack>

                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                  {issueTransitionsDetails.delay_computation.formula}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                  Sprint End: {formatDateAsYyyyMmDd(issueTransitionsDetails.delay_computation.sprint_end_date)} | Delay Baseline: {formatDateAsYyyyMmDd(issueTransitionsDetails.delay_computation.delay_baseline_date || issueTransitionsDetails.delay_computation.sprint_end_date)} ({issueTransitionsDetails.delay_computation.delay_baseline_source || 'sprint_end_date'}) | Effective End: {formatDateAsYyyyMmDd(issueTransitionsDetails.delay_computation.effective_end_date)}
                </Typography>

                <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Assignment Timeline</Typography>
                {issueTransitionsDetails.assignee_timeline.length > 0 ? (
                  <TableContainer sx={{ maxHeight: 220, mb: 1.5 }}>
                    <Table stickyHeader size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 'bold', minWidth: 140 }}>Assignee</TableCell>
                          <TableCell sx={{ fontWeight: 'bold', minWidth: 120 }}>From</TableCell>
                          <TableCell sx={{ fontWeight: 'bold', minWidth: 120 }}>To</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }} align="right">Duration (d)</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }} align="right">Delay Attributed (d)</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {issueTransitionsDetails.assignee_timeline.map((timelineRow, index) => (
                          <TableRow key={`${timelineRow.assignee}-${timelineRow.period_start}-${index}`} hover>
                            <TableCell>{timelineRow.assignee || 'Unassigned'}</TableCell>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(timelineRow.period_start)}</TableCell>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(timelineRow.period_end)}</TableCell>
                            <TableCell align="right">{formatDelayInDays(timelineRow.duration_days)}</TableCell>
                            <TableCell align="right">{formatDelayInDays(timelineRow.delay_days)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Alert severity="info" sx={{ mb: 1.5 }}>No assignee timeline available for this issue.</Alert>
                )}

                <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Transition Events</Typography>

                {issueTransitionsDetails.transitions.length > 0 ? (
                  <TableContainer sx={{ flex: 1, minHeight: 0 }}>
                    <Table stickyHeader size="small" sx={{ tableLayout: 'fixed' }}>
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 'bold', width: 130, whiteSpace: 'nowrap' }}>Change Date</TableCell>
                          <TableCell sx={{ fontWeight: 'bold', width: 120, py: 0.75 }} align="right">
                            <Box sx={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.15 }}>
                              <span>Accumulated</span>
                              <span>Delay (d)</span>
                            </Box>
                          </TableCell>
                          <TableCell sx={{ fontWeight: 'bold', width: 110 }}>Field</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>From</TableCell>
                          <TableCell sx={{ fontWeight: 'bold' }}>To</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {issueTransitionsDetails.transitions.map((transition, index) => (
                          <TableRow key={`${transition.change_date}-${transition.field}-${index}`} hover>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(transition.change_date)}</TableCell>
                            <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>{formatDelayInDays(transition.accumulated_delay_days)}</TableCell>
                            <TableCell>{transition.field || 'NA'}</TableCell>
                            <TableCell>{transition.from_value || 'NA'}</TableCell>
                            <TableCell>{transition.to_value || 'NA'}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Alert severity="info">No transition history found for this issue.</Alert>
                )}
              </Box>
            ) : (
              <Alert severity="info">Click an issue ID to view transition history.</Alert>
            )}
          </Box>
        </Drawer>

        {/* Employee Details Drawer */}
        <Drawer
          anchor="right"
          open={detailsDrawerOpen}
          onClose={() => setDetailsDrawerOpen(false)}
          PaperProps={{ sx: { width: { xs: '100%', sm: 500 } } }}
        >
          {employeeDetails && (
            <Box sx={{ p: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                <Typography variant="h5">Employee Details</Typography>
                <IconButton onClick={() => setDetailsDrawerOpen(false)}>
                  <CloseIcon />
                </IconButton>
              </Box>

              <Divider sx={{ mb: 3 }} />

              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <Typography variant="overline" color="text.secondary">Basic Information</Typography>
                </Grid>
                
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">SAPID</Typography>
                  <Typography variant="body1" fontWeight={600}>{employeeDetails.sapid}</Typography>
                </Grid>
                
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Name</Typography>
                  <Typography variant="body1" fontWeight={600}>{employeeDetails.name}</Typography>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Dashboard</Typography>
                  <Typography variant="body1">
                    <Link
                      component="button"
                      onClick={() => navigate(`/dashboard/employee?sapid=${encodeURIComponent(employeeDetails.sapid)}`)}
                    >
                      View Dashboard
                    </Link>
                  </Typography>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Start Date</Typography>
                  <Typography variant="body1">{employeeDetails.start_date || '-'}</Typography>
                </Grid>

                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="overline" color="text.secondary">Team & Role</Typography>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Team</Typography>
                  <Box sx={{ mt: 0.5 }}>
                    <Chip
                      label={employeeDetails.team}
                      size="small"
                      sx={{
                        bgcolor: getTeamColor(employeeDetails.team),
                        color: 'white'
                      }}
                    />
                  </Box>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Scrum</Typography>
                  <Typography variant="body1">{employeeDetails.scrum}</Typography>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Primary Role</Typography>
                  <Typography variant="body1">{employeeDetails.primary_role}</Typography>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Secondary Role</Typography>
                  <Typography variant="body1">{employeeDetails.secondary_role || '-'}</Typography>
                </Grid>

                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="overline" color="text.secondary">Management</Typography>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Manager</Typography>
                  <Typography variant="body1">{employeeDetails.manager_name || '-'}</Typography>
                </Grid>

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Manager SAPID</Typography>
                  <Typography variant="body1">{employeeDetails.manager || '-'}</Typography>
                </Grid>

                {employeeDetails.reporting !== undefined && (
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Reporting</Typography>
                    <Typography variant="body1">{employeeDetails.reporting}</Typography>
                  </Grid>
                )}

                <Grid item xs={12}>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="overline" color="text.secondary">Contact & Tools</Typography>
                </Grid>

                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">Email</Typography>
                  <Typography variant="body1">
                    {employeeDetails.email ? (
                      <Link href={`mailto:${employeeDetails.email}`}>{employeeDetails.email}</Link>
                    ) : (
                      '-'
                    )}
                  </Typography>
                </Grid>

                {employeeDetails.jira_name && (
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">JIRA Name</Typography>
                    <Typography variant="body1">{employeeDetails.jira_name}</Typography>
                  </Grid>
                )}

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">GitHub Name</Typography>
                  <Typography variant="body1">{employeeDetails.github_name || '-'}</Typography>
                </Grid>

                {employeeDetails.git_email && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Git Email</Typography>
                    <Typography variant="body1">{employeeDetails.git_email}</Typography>
                  </Grid>
                )}

                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">UDE ID</Typography>
                  <Typography variant="body1">{employeeDetails.udeid || '-'}</Typography>
                </Grid>

                {employeeDetails.tacid && (
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">TAC ID</Typography>
                    <Typography variant="body1">{employeeDetails.tacid}</Typography>
                  </Grid>
                )}

              </Grid>
            </Box>
          )}
        </Drawer>
      </Paper>
    </Container>
  )
}
