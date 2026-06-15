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
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tooltip as MuiTooltip
} from '@mui/material'
import GroupWorkIcon from '@mui/icons-material/GroupWork'
import GroupIcon from '@mui/icons-material/Group'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import CleaningServicesIcon from '@mui/icons-material/CleaningServices'
import VerifiedIcon from '@mui/icons-material/Verified'
import CalendarTodayIcon from '@mui/icons-material/CalendarToday'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { scrumDashboardApi, ScrumOption, KPIPerformance } from '../services/scrumDashboardApi'
import { fetchAvailableDates } from '../services/teamDashboardApi'
import CategoryScoreGauge from '../components/CategoryScoreGauge';

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

const CHART_COLORS = [
  '#1976d2', '#dc004e', '#9c27b0', '#f57c00', '#388e3c',
  '#00796b', '#5d4037', '#303f9f', '#c2185b', '#7b1fa2'
]

function getProrateInfo(asOfDateInput: string) {
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
  const ms = 86400000
  const daysAnnual = Math.floor((ref.getTime() - fyStart.getTime()) / ms)
  const weeksAnnual = Math.min(Math.max(1, Math.ceil((daysAnnual + 1) / 7)), 52)
  const daysQ = Math.floor((ref.getTime() - qStart.getTime()) / ms)
  const weeksQ = Math.min(Math.max(1, Math.ceil((daysQ + 1) / 7)), 13)
  const annualPct = (weeksAnnual / 52 * 100).toFixed(1)
  const qPct = (weeksQ / 13 * 100).toFixed(1)
  const dateFormatted = ref.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  return { weeksAnnual, weeksQ, annualPct, qPct, dateFormatted }
}

export default function ScrumDashboardPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [scrums, setScrums] = useState<ScrumOption[]>([])
  const [selectedScrum, setSelectedScrum] = useState<ScrumOption | null>(null)
  const [period, setPeriod] = useState('Annual')
  const [asOfDate, setAsOfDate] = useState<string>('')
  const [maxDate, setMaxDate] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const dateInputRef = useRef<HTMLInputElement>(null)
  const [loadingScrums, setLoadingScrums] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const [dashboardData, setDashboardData] = useState<any>(null)

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

  // Load scrums on mount
  useEffect(() => {
    const loadScrums = async () => {
      setLoadingScrums(true)
      try {
        const response = await scrumDashboardApi.listScrums()
        setScrums(response.scrums)
        
        // Check if scrum parameter is in URL
        const scrumParam = searchParams.get('scrum')
        if (scrumParam && response.scrums.length > 0) {
          const scrum = response.scrums.find(s => s.name === scrumParam)
          if (scrum) {
            setSelectedScrum(scrum)
          }
        }
      } catch (err: any) {
        console.error('Failed to load scrums:', err)
        setError('Failed to load scrum list')
      } finally {
        setLoadingScrums(false)
      }
    }
    loadScrums()
  }, [searchParams])

  // Load dashboard data when scrum or period or date changes
  useEffect(() => {
    if (!selectedScrum) return
    const timer = setTimeout(() => { loadDashboardData() }, 400)
    return () => clearTimeout(timer)
  }, [selectedScrum, period, asOfDate])

  const loadDashboardData = async () => {
    if (!selectedScrum) return
    
    setLoading(true)
    setError(null)
    try {
      const data = await scrumDashboardApi.getScrumDashboard(selectedScrum.name, period, asOfDate ? asOfDate.replace(/-/g, '') : '')
      setDashboardData(data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load scrum dashboard')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const prorateInfo = getProrateInfo(asOfDate)

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ mb: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <GroupWorkIcon sx={{ fontSize: 32, color: 'primary.main' }} />
            <Typography variant="h4">
              Scrum Dashboard
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary">
            Aggregated performance view for scrum teams
          </Typography>
        </Box>

        {/* Scrum Selection and Period Filter */}
        <Box sx={{ mb: 3 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Autocomplete
                options={scrums}
                value={selectedScrum}
                onChange={(_, newValue) => setSelectedScrum(newValue)}
                getOptionLabel={(option) => `${option.name} (${option.member_count} members)`}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Select Scrum"
                    placeholder="Search by scrum name"
                  />
                )}
                loading={loadingScrums}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                select
                fullWidth
                label="Period"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                disabled={!selectedScrum}
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
                  disabled={!selectedScrum}
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
            {/* Scrum Profile Accordion - Collapsible */}
            <Accordion sx={{ mb: 3 }} defaultExpanded={false}>
              <AccordionSummary
                expandIcon={<ExpandMoreIcon />}
                sx={{ bgcolor: '#f5f5f5' }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
                  <GroupIcon sx={{ fontSize: 32, color: 'primary.main' }} />
                  <Box>
                    <Typography variant="h6" fontWeight={600}>
                      {dashboardData.scrum.name} - Scrum Details
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {dashboardData.scrum.member_count} scrum members • Click to expand
                    </Typography>
                  </Box>
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                {/* Role Distribution Charts - Horizontal Layout */}
                <Box sx={{ mb: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                    Role Distribution
                  </Typography>
                  <Grid container spacing={2}>
                    {/* Primary Role Distribution */}
                    <Grid item xs={12} md={6}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle2" fontWeight={600} gutterBottom align="center">
                            Primary Roles
                          </Typography>
                          {dashboardData.scrum.primary_role_distribution && dashboardData.scrum.primary_role_distribution.length > 0 ? (
                            <>
                              <ResponsiveContainer width="100%" height={250}>
                                <PieChart>
                                  <Pie
                                    data={dashboardData.scrum.primary_role_distribution}
                                    dataKey="count"
                                    nameKey="role"
                                    cx="50%"
                                    cy="50%"
                                    outerRadius={80}
                                  >
                                    {dashboardData.scrum.primary_role_distribution.map((_: any, index: number) => (
                                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                    ))}
                                  </Pie>
                                  <Tooltip />
                                </PieChart>
                              </ResponsiveContainer>
                              <Box sx={{ mt: 2 }}>
                                {dashboardData.scrum.primary_role_distribution.map((item: any, index: number) => (
                                  <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                    <Box sx={{ width: 12, height: 12, bgcolor: CHART_COLORS[index % CHART_COLORS.length], borderRadius: '50%' }} />
                                    <Typography variant="body2" sx={{ fontSize: '0.75rem' }}>
                                      {item.role}: {item.count}
                                    </Typography>
                                  </Box>
                                ))}
                              </Box>
                            </>
                          ) : (
                            <Typography variant="body2" color="text.secondary" align="center">
                              No role data
                            </Typography>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                    
                    {/* Secondary Role Distribution */}
                    <Grid item xs={12} md={6}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle2" fontWeight={600} gutterBottom align="center">
                            Secondary Roles
                          </Typography>
                          {dashboardData.scrum.secondary_role_distribution && dashboardData.scrum.secondary_role_distribution.length > 0 ? (
                            <>
                              <ResponsiveContainer width="100%" height={250}>
                                <PieChart>
                                  <Pie
                                    data={dashboardData.scrum.secondary_role_distribution}
                                    dataKey="count"
                                    nameKey="role"
                                    cx="50%"
                                    cy="50%"
                                    outerRadius={80}
                                  >
                                    {dashboardData.scrum.secondary_role_distribution.map((_: any, index: number) => (
                                      <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                                    ))}
                                  </Pie>
                                  <Tooltip />
                                </PieChart>
                              </ResponsiveContainer>
                              <Box sx={{ mt: 2 }}>
                                {dashboardData.scrum.secondary_role_distribution.map((item: any, index: number) => (
                                  <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                    <Box sx={{ width: 12, height: 12, bgcolor: CHART_COLORS[index % CHART_COLORS.length], borderRadius: '50%' }} />
                                    <Typography variant="body2" sx={{ fontSize: '0.75rem' }}>
                                      {item.role}: {item.count}
                                    </Typography>
                                  </Box>
                                ))}
                              </Box>
                            </>
                          ) : (
                            <Typography variant="body2" color="text.secondary" align="center">
                              No secondary role data
                            </Typography>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                  </Grid>
                </Box>

                {/* Scrum Members - Below Charts */}
                <Box>
                  <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                    Scrum Members ({dashboardData.scrum.member_count})
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {(dashboardData.scrum.member_details || dashboardData.scrum.members.map((member: string) => ({ name: member, sapid: '' }))).map((member: any) => (
                      <Chip 
                        key={member.sapid || member.name} 
                        label={member.name} 
                        size="small" 
                        variant="outlined"
                        onClick={() => navigate(`/dashboard/employee?${member.sapid ? `sapid=${encodeURIComponent(member.sapid)}` : `name=${encodeURIComponent(member.name)}`}`)}
                        sx={{ cursor: 'pointer' }}
                      />
                    ))}
                  </Box>
                </Box>
              </AccordionDetails>
            </Accordion>

            {/* Category Score Gauges - All in Single Row */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" gutterBottom>
                Scrum Performance Score - {period}
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
            </Box>

            {/* KPI Performance Table */}
            <Box>
              <Typography variant="h6" gutterBottom>
                KPI Performance Details (Aggregated)
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
                      <TableCell sx={{ fontWeight: 'bold' }}>KPI ID</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>KPI Name</TableCell>
                      <TableCell sx={{ fontWeight: 'bold' }}>Direction</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold' }}>Avg Actual</TableCell>
                      <MuiTooltip
                        title={
                          <Box sx={{ p: 0.5 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5 }}>Target Prorating as of {prorateInfo.dateFormatted}</Typography>
                            <Typography variant="body2">Quarterly: Week {prorateInfo.weeksQ}/13 ({prorateInfo.qPct}%)</Typography>
                            <Typography variant="body2">Annual: Week {prorateInfo.weeksAnnual}/52 ({prorateInfo.annualPct}%)</Typography>
                            <Typography variant="body2" sx={{ mt: 0.5, fontStyle: 'italic' }}>Weekly &amp; Monthly: not prorated</Typography>
                          </Box>
                        }
                        arrow
                        placement="top"
                      >
                        <TableCell align="right" sx={{ fontWeight: 'bold', cursor: 'help' }}>Target</TableCell>
                      </MuiTooltip>
                      <TableCell align="right" sx={{ fontWeight: 'bold' }}>%</TableCell>
                      <TableCell align="center" sx={{ fontWeight: 'bold' }}>Members</TableCell>
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
                        <MuiTooltip title={tooltipContent} arrow placement="top">
                          <TableCell sx={{ cursor: 'help' }}>{kpi.kpi_id}</TableCell>
                        </MuiTooltip>
                        <MuiTooltip title={tooltipContent} arrow placement="top">
                          <TableCell sx={{ cursor: 'help' }}>{kpi.kpi_name}</TableCell>
                        </MuiTooltip>
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
                        <MuiTooltip
                          title={kpi.prorated_target !== undefined && kpi.period && !['Weekly', 'Monthly'].includes(kpi.period) && kpi.prorate !== false ? `Prorated: ${kpi.prorated_target.toFixed(1)}` : ''}
                          arrow
                          placement="top"
                          disableHoverListener={kpi.prorated_target === undefined || ['Weekly', 'Monthly'].includes(kpi.period ?? '') || kpi.prorate === false}
                        >
                          <TableCell align="right" sx={{ cursor: (kpi.period && !['Weekly', 'Monthly'].includes(kpi.period)) ? 'help' : 'default' }}>
                            {kpi.target.toFixed(1)}
                          </TableCell>
                        </MuiTooltip>
                        <TableCell align="right">{kpi.percentage != null ? `${kpi.percentage.toFixed(0)}%` : '-'}</TableCell>
                        <TableCell align="center">
                          <Chip label={kpi.member_count} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell align="center">
                          <MuiTooltip
                            title={
                              kpi.rog_status === 'not_configured'
                                ? 'This KPI is not configured for this team and is excluded from score calculation.'
                                : 'KPI status based on average actual vs target.'
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
                          </MuiTooltip>
                        </TableCell>
                      </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          </>
        )}

        {/* No Selection State */}
        {!loading && !dashboardData && !error && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <GroupWorkIcon sx={{ fontSize: 80, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" color="text.secondary">
              Select a scrum team to view their dashboard
            </Typography>
          </Box>
        )}
      </Paper>
    </Container>
  )
}
