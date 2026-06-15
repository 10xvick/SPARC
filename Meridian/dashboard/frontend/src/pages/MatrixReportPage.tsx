import { useState, useEffect, useRef } from 'react'
import {
  Container,
  Paper,
  Typography,
  Box,
  TextField,
  MenuItem,
  CircularProgress,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Button,
  Stack,
  Chip,
  FormControl,
  InputLabel,
  Select,
  OutlinedInput,
  SelectChangeEvent,
  Tooltip
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import GridOnIcon from '@mui/icons-material/GridOn'
import CalendarTodayIcon from '@mui/icons-material/CalendarToday'
import { reportsApi, MatrixReportData, MatrixReportKpiMeta } from '../services/reportsApi'
import { fetchAvailableDates } from '../services/teamDashboardApi'

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

export default function MatrixReportPage() {
  const [data, setData] = useState<MatrixReportData[]>([])
  const [kpis, setKpis] = useState<string[]>([])
  const [availableKpis, setAvailableKpis] = useState<string[]>([])
  const [availableTeams, setAvailableTeams] = useState<string[]>([])
  const [kpiMeta, setKpiMeta] = useState<Record<string, MatrixReportKpiMeta | null>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  // Filter states
  const [period, setPeriod] = useState('Annual')
  const [selectedTeam, setSelectedTeam] = useState('')
  const [selectedKpis, setSelectedKpis] = useState<string[]>([])
  const [filterKpi, setFilterKpi] = useState('')
  const [minValue, setMinValue] = useState('')
  const [maxValue, setMaxValue] = useState('')
  const [sortBy, setSortBy] = useState('name')
  const [asOfDate, setAsOfDate] = useState<string>('')
  const [maxDate, setMaxDate] = useState<string>('')
  const dateInputRef = useRef<HTMLInputElement>(null)
  
  const [totalIndividuals, setTotalIndividuals] = useState(0)
  const [totalKpis, setTotalKpis] = useState(0)

  const periods = ['Weekly', 'Monthly', 'Quarterly', 'Annual']

  const toInputDate = (d: string): string =>
    d.length === 8 ? `${d.substring(0,4)}-${d.substring(4,6)}-${d.substring(6,8)}` : d

  const formatDisplayDate = (dateStr: string): string => {
    if (!dateStr || dateStr.length !== 10) return dateStr
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    const [year, month, day] = dateStr.split('-')
    return `${day}-${months[parseInt(month)-1]}-${year}`
  }

  // Load available KPIs on mount
  useEffect(() => {
    const loadAvailableKpis = async () => {
      try {
        const response = await reportsApi.getAvailableKpis()
        setAvailableKpis(response.kpis)
      } catch (err) {
        console.error('Failed to load available KPIs:', err)
      }
    }
    loadAvailableKpis()
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

  // Load matrix data
  useEffect(() => {
    const timer = setTimeout(() => { loadMatrixData() }, 400)
    return () => clearTimeout(timer)
  }, [period, selectedTeam, selectedKpis, sortBy, asOfDate])

  const loadMatrixData = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await reportsApi.getMatrixReport({
        period,
        team: selectedTeam || undefined,
        kpis: selectedKpis.length > 0 ? selectedKpis.join(',') : undefined,
        sort_by: sortBy !== 'name' ? sortBy : undefined,
        as_of_date: asOfDate ? asOfDate.replace(/-/g, '') : undefined
      })
      setData(response.data)
      setKpis(response.kpis)
      setKpiMeta(response.kpi_meta ?? {})
      setAvailableTeams(response.available_teams)
      setTotalIndividuals(response.total_individuals)
      setTotalKpis(response.total_kpis)

      if (selectedTeam && !response.available_teams.includes(selectedTeam)) {
        setSelectedTeam('')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load matrix report')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleKpisChange = (event: SelectChangeEvent<typeof selectedKpis>) => {
    const value = event.target.value
    setSelectedKpis(typeof value === 'string' ? value.split(',') : value)
  }

  const parseNumeric = (value: unknown): number | null => {
    if (typeof value === 'number') {
      return Number.isFinite(value) ? value : null
    }
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (!trimmed) {
        return null
      }
      const numeric = Number(trimmed.replace('%', '').replace(/,/g, ''))
      return Number.isFinite(numeric) ? numeric : null
    }
    return null
  }

  const formatValue = (value: any) => {
    if (typeof value === 'number') {
      if (Number.isInteger(value)) {
        return value.toString()
      }
      return value.toFixed(1)
    }
    return value
  }

  const getCellStatusColor = (value: any, kpi: string): 'error.main' | 'warning.main' | 'success.main' | 'text.primary' => {
    const meta = kpiMeta[kpi]
    if (!meta || typeof value !== 'number') {
      return 'text.primary'
    }

    // Use prorated_target for status comparison; fall back to target if not available
    const comparisonTarget = meta.prorated_target ?? meta.target ?? 0
    if (!comparisonTarget) {
      return 'text.primary'
    }

    const percentage = (value / comparisonTarget) * 100

    if (meta.goal_direction === 'Maximize') {
      if (percentage >= 100) return 'success.main'
      if (percentage >= 80) return 'warning.main'
      return 'error.main'
    }

    if (percentage <= 100) return 'success.main'
    if (percentage <= 120) return 'warning.main'
    return 'error.main'
  }

  const getKpiTooltip = (kpi: string) => {
    const meta = kpiMeta[kpi]
    if (!meta) {
      return `${kpi.toUpperCase()}\nKPI details not available`
    }
    const prorateInfo = getProrateInfo(asOfDate)
    const isProratedPeriod = period === 'Quarterly' || period === 'Annual'
    const proratedTarget = meta.prorated_target
    const weekLabel = period === 'Quarterly'
      ? `Week ${prorateInfo.weeksQ}/13 (${prorateInfo.qPct}%)`
      : `Week ${prorateInfo.weeksAnnual}/52 (${prorateInfo.annualPct}%)`
    return [
      `${kpi.toUpperCase()}`,
      meta.kpp_goals || '',
      meta.measurement_criteria ? `Criteria: ${meta.measurement_criteria}` : '',
      meta.tool ? `Tool: ${meta.tool}` : '',
      meta.measure ? `Measure: ${meta.measure}` : '',
      `Direction: ${meta.goal_direction}`,
      `Target (${period}): ${formatValue(meta.target)}`,
      isProratedPeriod && proratedTarget !== undefined && meta.prorate !== false
        ? `Prorated: ${proratedTarget.toFixed(1)} — ${weekLabel} as of ${prorateInfo.dateFormatted}`
        : null
    ].filter(Boolean).join('\n')
  }

  const effectiveKpiOptions = kpis.length > 0 ? kpis : availableKpis
  const minBound = minValue.trim() === '' ? null : Number(minValue)
  const maxBound = maxValue.trim() === '' ? null : Number(maxValue)
  const filteredData = data.filter((row) => {
    if (!filterKpi) {
      return true
    }

    const numericValue = parseNumeric(row[filterKpi])
    if (numericValue === null) {
      return false
    }

    if (minBound !== null && Number.isFinite(minBound) && numericValue < minBound) {
      return false
    }

    if (maxBound !== null && Number.isFinite(maxBound) && numericValue > maxBound) {
      return false
    }

    return true
  })

  const displayData = [...filteredData].sort((left, right) => {
    if (sortBy === 'name') {
      return String(left.name).localeCompare(String(right.name))
    }

    const leftValue = parseNumeric(left[sortBy]) ?? 0
    const rightValue = parseNumeric(right[sortBy]) ?? 0
    return rightValue - leftValue
  })

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <GridOnIcon sx={{ fontSize: 32, color: 'primary.main' }} />
              <Typography variant="h4">
                KPI Matrix Report
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              Comprehensive view of all individuals and their KPI performance metrics
            </Typography>
          </Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            size="small"
            onClick={loadMatrixData}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>

        {/* Filters */}
        <Box sx={{ mb: 3 }}>
          <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ mb: 2 }}>
            <TextField
              select
              label="Period"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              size="small"
              sx={{ minWidth: 150 }}
            >
              {periods.map((p) => (
                <MenuItem key={p} value={p}>{p}</MenuItem>
              ))}
            </TextField>

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
                style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%' }}
              />
            </Box>

            <TextField
              select
              label="Team"
              value={selectedTeam}
              onChange={(e) => setSelectedTeam(e.target.value)}
              size="small"
              sx={{ minWidth: 180 }}
            >
              <MenuItem value="">All Teams</MenuItem>
              {availableTeams.map((team) => (
                <MenuItem key={team} value={team}>{team}</MenuItem>
              ))}
            </TextField>

            <FormControl size="small" sx={{ minWidth: 300 }}>
              <InputLabel>Select KPIs (All if empty)</InputLabel>
              <Select
                multiple
                value={selectedKpis}
                onChange={handleKpisChange}
                input={<OutlinedInput label="Select KPIs (All if empty)" />}
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip key={value} label={value.toUpperCase()} size="small" />
                    ))}
                  </Box>
                )}
              >
                {availableKpis.map((kpi) => (
                  <MenuItem key={kpi} value={kpi}>
                    {kpi.toUpperCase()}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              select
              label="Sort By"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              size="small"
              sx={{ minWidth: 150 }}
            >
              <MenuItem value="name">Name (A-Z)</MenuItem>
              {kpis.map((kpi) => (
                <MenuItem key={kpi} value={kpi}>{kpi.toUpperCase()}</MenuItem>
              ))}
            </TextField>
          </Stack>

          <Stack direction="row" spacing={2} flexWrap="wrap">
            <TextField
              select
              label="Filter KPI"
              value={filterKpi}
              onChange={(e) => {
                const kpi = e.target.value
                setFilterKpi(kpi)
                if (kpi) {
                  setSortBy(kpi)
                }
              }}
              size="small"
              sx={{ minWidth: 150 }}
            >
              <MenuItem value="">None</MenuItem>
              {effectiveKpiOptions.map((kpi) => (
                <MenuItem key={kpi} value={kpi}>{kpi.toUpperCase()}</MenuItem>
              ))}
            </TextField>

            <TextField
              label="Min Value"
              type="number"
              value={minValue}
              onChange={(e) => setMinValue(e.target.value)}
              size="small"
              sx={{ minWidth: 120 }}
            />

            <TextField
              label="Max Value"
              type="number"
              value={maxValue}
              onChange={(e) => setMaxValue(e.target.value)}
              size="small"
              sx={{ minWidth: 120 }}
            />
          </Stack>
        </Box>

        {/* Summary Stats */}
        {!loading && !error && (
          <Box sx={{ mb: 2, display: 'flex', gap: 2 }}>
            <Chip
              label={`${totalIndividuals} Individuals`}
              color="primary"
              variant="outlined"
            />
            <Chip
              label={`${totalKpis} KPIs`}
              color="secondary"
              variant="outlined"
            />
            <Chip
              label={`${period} Period`}
              color="info"
              variant="outlined"
            />
            <Chip
              label={selectedTeam ? `Team: ${selectedTeam}` : 'All Teams'}
              color="default"
              variant="outlined"
            />
          </Box>
        )}

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

        {/* Matrix Table */}
        {!loading && !error && displayData.length > 0 && (
          <TableContainer sx={{ maxHeight: 'calc(100vh - 400px)' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 200, position: 'sticky', left: 0, bgcolor: 'background.paper', zIndex: 3 }}>
                    Name
                  </TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 110, position: 'sticky', left: 200, bgcolor: 'background.paper', zIndex: 3 }}>
                    SAPID
                  </TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 150, bgcolor: 'background.paper', zIndex: 3 }}>
                    Team
                  </TableCell>
                  {kpis.map((kpi) => (
                    <TableCell
                      key={kpi}
                      align="right"
                      sx={{ fontWeight: 'bold', minWidth: 80 }}
                    >
                      <Tooltip title={<Box sx={{ whiteSpace: 'pre-line' }}>{getKpiTooltip(kpi)}</Box>} arrow placement="top">
                        <span>{kpi.toUpperCase()}</span>
                      </Tooltip>
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {displayData.map((row, idx) => (
                  <TableRow key={idx} hover>
                    <TableCell sx={{ position: 'sticky', left: 0, bgcolor: 'background.paper', zIndex: 1 }}>
                      {row.name}
                    </TableCell>
                    <TableCell sx={{ position: 'sticky', left: 200, bgcolor: 'background.paper', zIndex: 1, color: 'text.secondary', fontSize: '0.75rem' }}>
                      {row.sapid}
                    </TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: '0.85rem' }}>
                      {row.team}
                    </TableCell>
                    {kpis.map((kpi) => (
                      <TableCell key={kpi} align="right" sx={{ color: getCellStatusColor(row[kpi], kpi), fontWeight: 600 }}>
                        {formatValue(row[kpi])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {/* No Data */}
        {!loading && !error && displayData.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="body1" color="text.secondary">
              No data available for the selected filters
            </Typography>
          </Box>
        )}
      </Paper>
    </Container>
  )
}
