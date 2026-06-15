import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Container,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Button
} from '@mui/material'
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents'
import RefreshIcon from '@mui/icons-material/Refresh'
import {
  reportsApi,
  EmployeeScoreComparisonData
} from '../services/reportsApi'
import { fetchAvailableDates } from '../services/teamDashboardApi'

const metricLabels: Array<{ key: 'overall' | 'input' | 'output' | 'quality' | 'hygiene'; label: string }> = [
  { key: 'overall', label: 'Overall' },
  { key: 'input', label: 'Input' },
  { key: 'output', label: 'Output' },
  { key: 'quality', label: 'Quality' },
  { key: 'hygiene', label: 'Hygiene' }
]

function getScore(
  row: EmployeeScoreComparisonData,
  period: 'Weekly' | 'Quarterly' | 'Annual',
  metric: 'overall' | 'input' | 'output' | 'quality' | 'hygiene'
): number {
  return row.scores?.[period]?.[metric] ?? 0
}

export default function EmployeeScoreComparisonReportPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<EmployeeScoreComparisonData[]>([])

  const [availableTeams, setAvailableTeams] = useState<string[]>([])
  const [availableScrums, setAvailableScrums] = useState<string[]>([])
  const [availablePrimaryRoles, setAvailablePrimaryRoles] = useState<string[]>([])
  const [availableSecondaryRoles, setAvailableSecondaryRoles] = useState<string[]>([])

  const [team, setTeam] = useState('')
  const [scrum, setScrum] = useState('')
  const [primaryRole, setPrimaryRole] = useState('')
  const [secondaryRole, setSecondaryRole] = useState('')
  const [period, setPeriod] = useState<'Annual' | 'Quarterly' | 'Weekly'>('Annual')
  const [asOfDate, setAsOfDate] = useState('')
  const [availableDates, setAvailableDates] = useState<string[]>([])
  const [datesInitialized, setDatesInitialized] = useState(false)
  const [scoreThresholds, setScoreThresholds] = useState<{ green_min: number; orange_min: number; red_max: number }>({
    green_min: 70,
    orange_min: 36,
    red_max: 35
  })
  const [categoryWeightages, setCategoryWeightages] = useState<{ input: number; output: number; quality: number; hygiene: number }>({
    input: 10,
    output: 50,
    quality: 30,
    hygiene: 10
  })

  const formatDisplayDate = (dateValue: string) => {
    if (!dateValue || dateValue.length !== 8) return dateValue
    return `${dateValue.substring(6, 8)}-${dateValue.substring(4, 6)}-${dateValue.substring(0, 4)}`
  }

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await reportsApi.getEmployeeScoreComparison({
        team: team || undefined,
        scrum: scrum || undefined,
        primary_role: primaryRole || undefined,
        secondary_role: secondaryRole || undefined,
        as_of_date: asOfDate || undefined
      })

      setData(response.data)
      setAvailableTeams(response.available_filters.teams || [])
      setAvailableScrums(response.available_filters.scrums || [])
      setAvailablePrimaryRoles(response.available_filters.primary_roles || [])
      setAvailableSecondaryRoles(response.available_filters.secondary_roles || [])
      if (response.score_display_thresholds) {
        setScoreThresholds(response.score_display_thresholds)
      }
      if (response.category_weightages) {
        setCategoryWeightages(response.category_weightages)
      }

      if (team && !response.available_filters.teams.includes(team)) {
        setTeam('')
      }
      if (scrum && !response.available_filters.scrums.includes(scrum)) {
        setScrum('')
      }
      if (primaryRole && !response.available_filters.primary_roles.includes(primaryRole)) {
        setPrimaryRole('')
      }
      if (secondaryRole && !response.available_filters.secondary_roles.includes(secondaryRole)) {
        setSecondaryRole('')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load employee score comparison report')
      setData([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let active = true
    fetchAvailableDates()
      .then((dates) => {
        if (!active) return
        setAvailableDates(dates)
        if (!asOfDate && dates.length > 0) {
          setAsOfDate(dates[0])
        }
      })
      .catch(() => {
        // Keep page functional even if dates endpoint fails
      })
      .finally(() => {
        if (!active) return
        setDatesInitialized(true)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!datesInitialized) {
      return
    }
    if (availableDates.length > 0 && !asOfDate) {
      return
    }
    loadData()
  }, [team, scrum, primaryRole, secondaryRole, asOfDate, datesInitialized, availableDates.length])

  const sortedData = useMemo(() => {
    const rows = [...data]
    rows.sort((a, b) => {
      const aAnnual = getScore(a, 'Annual', 'overall')
      const bAnnual = getScore(b, 'Annual', 'overall')
      if (bAnnual !== aAnnual) {
        return bAnnual - aAnnual
      }
      return a.name.localeCompare(b.name)
    })
    return rows
  }, [data])

  const getScoreColor = (scorePercent: number): string => {
    if (scorePercent >= scoreThresholds.green_min) return 'success.main'
    if (scorePercent >= scoreThresholds.orange_min) return 'warning.main'
    return 'error.main'
  }

  const getMetricPercent = (
    score: number,
    metric: 'overall' | 'input' | 'output' | 'quality' | 'hygiene'
  ): number => {
    if (metric === 'overall') {
      return score
    }
    const maxWeight = categoryWeightages[metric] ?? 0
    return maxWeight > 0 ? (score / maxWeight) * 100 : 0
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <EmojiEventsIcon sx={{ fontSize: 32, color: 'primary.main' }} />
              <Typography variant="h4">Score Report</Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              Weekly, Quarterly, and Annual employee scores derived from Employee Dashboard scoring.
            </Typography>
          </Box>
          <Button variant="outlined" startIcon={<RefreshIcon />} onClick={loadData} disabled={loading}>
            Refresh
          </Button>
        </Box>

        <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ mb: 3 }}>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Duration</InputLabel>
            <Select value={period} label="Duration" onChange={(e) => setPeriod(e.target.value as 'Annual' | 'Quarterly' | 'Weekly')}>
              <MenuItem value="Annual">Annual</MenuItem>
              <MenuItem value="Quarterly">Quarterly</MenuItem>
              <MenuItem value="Weekly">Weekly</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 170 }}>
            <InputLabel>As Of Date</InputLabel>
            <Select value={asOfDate} label="As Of Date" onChange={(e) => setAsOfDate(e.target.value)}>
              {availableDates.map((item) => (
                <MenuItem key={item} value={item}>{formatDisplayDate(item)}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Team</InputLabel>
            <Select value={team} label="Team" onChange={(e) => setTeam(e.target.value)}>
              <MenuItem value="">All Teams</MenuItem>
              {availableTeams.map((item) => (
                <MenuItem key={item} value={item}>{item}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Scrum</InputLabel>
            <Select value={scrum} label="Scrum" onChange={(e) => setScrum(e.target.value)}>
              <MenuItem value="">All Scrums</MenuItem>
              {availableScrums.map((item) => (
                <MenuItem key={item} value={item}>{item}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Primary Role</InputLabel>
            <Select value={primaryRole} label="Primary Role" onChange={(e) => setPrimaryRole(e.target.value)}>
              <MenuItem value="">All Primary Roles</MenuItem>
              {availablePrimaryRoles.map((item) => (
                <MenuItem key={item} value={item}>{item}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Secondary Role</InputLabel>
            <Select value={secondaryRole} label="Secondary Role" onChange={(e) => setSecondaryRole(e.target.value)}>
              <MenuItem value="">All Secondary Roles</MenuItem>
              {availableSecondaryRoles.map((item) => (
                <MenuItem key={item} value={item}>{item}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>

        {!loading && !error && (
          <Box sx={{ mb: 2, display: 'flex', gap: 2 }}>
            <Chip label={`${sortedData.length} Employees`} color="primary" variant="outlined" />
            <Chip label="Scores: Overall + Input/Output/Quality/Hygiene" color="info" variant="outlined" />
            <Chip label={`Duration: ${period}`} color="secondary" variant="outlined" />
            <Chip label={asOfDate ? `As Of: ${formatDisplayDate(asOfDate)}` : 'As Of: Latest'} variant="outlined" />
            <Chip label={team ? `Team: ${team}` : 'All Teams'} variant="outlined" />
            <Chip label={scrum ? `Scrum: ${scrum}` : 'All Scrums'} variant="outlined" />
            <Chip label="All scores are out of 100" variant="outlined" />
          </Box>
        )}

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        )}

        {!loading && !error && sortedData.length > 0 && (
          <TableContainer sx={{ maxHeight: 'calc(100vh - 360px)' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 180 }}>Name</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 90 }}>SAPID</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 130 }}>Team</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 130 }}>Scrum</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 150 }}>Primary Role</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 170 }}>Secondary Role</TableCell>
                  {metricLabels.map((metric) => (
                    <TableCell key={`${period}-${metric.key}`} align="right" sx={{ fontWeight: 'bold', minWidth: 110 }}>
                      {period} {metric.label}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedData.map((row) => (
                  <TableRow key={row.sapid} hover>
                    <TableCell>{row.name}</TableCell>
                    <TableCell sx={{ color: 'text.secondary' }}>{row.sapid}</TableCell>
                    <TableCell>{row.team}</TableCell>
                    <TableCell>{row.scrum}</TableCell>
                    <TableCell>{row.primary_role}</TableCell>
                    <TableCell>{row.secondary_role}</TableCell>
                    {metricLabels.map((metric) => (
                      (() => {
                        const scorePercent = getMetricPercent(getScore(row, period, metric.key), metric.key)
                        return (
                          <TableCell
                            key={`${row.sapid}-${period}-${metric.key}`}
                            align="right"
                            sx={{
                              fontWeight: metric.key === 'overall' ? 700 : 500,
                              color: getScoreColor(scorePercent)
                            }}
                          >
                            {scorePercent.toFixed(1)}
                          </TableCell>
                        )
                      })()
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {!loading && !error && sortedData.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="body1" color="text.secondary">No data available for selected filters.</Typography>
          </Box>
        )}
      </Paper>
    </Container>
  )
}
