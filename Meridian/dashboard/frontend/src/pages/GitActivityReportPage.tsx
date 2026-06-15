import { useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Drawer,
  FormControl,
  IconButton,
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
  Tooltip,
  Typography,
} from '@mui/material'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import CommitIcon from '@mui/icons-material/Commit'
import CloseIcon from '@mui/icons-material/Close'
import RefreshIcon from '@mui/icons-material/Refresh'
import NavigateBeforeIcon from '@mui/icons-material/NavigateBefore'
import NavigateNextIcon from '@mui/icons-material/NavigateNext'
import DownloadIcon from '@mui/icons-material/Download'
import {
  GitActivityCommitDetail,
  GitActivityCommitFileDetailsResponse,
  GitActivityDetailedExportStatus,
  GitActivityEmployeeDetailsResponse,
  GitActivityPersonRow,
  reportsApi,
} from '../services/reportsApi'

type ActivityType = 'total_commits' | 'merges' | 'commits' | 'lines_added' | 'lines_deleted' | 'lines_changed' | 'files_changed' | 'repos_touched'
type EmployeeScope = 'active' | 'inactive' | 'all'

type ScoreDisplayThresholds = {
  green_min: number
  orange_min: number
  red_max: number
}

type ActionMessage = {
  severity: 'success' | 'info' | 'warning' | 'error'
  text: string
}

const formatMonthLabel = (month: string): string => {
  if (!month || month.length !== 7) {
    return month
  }
  const [year, monthNum] = month.split('-')
  const date = new Date(Number(year), Number(monthNum) - 1, 1)
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

const formatDateColumnLabel = (dateValue: string): string => {
  const parsed = new Date(`${dateValue}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) {
    return dateValue
  }

  return parsed.toLocaleDateString('en-US', {
    day: '2-digit',
    month: 'short',
  })
}

const escapeCsv = (value: string | number): string => {
  const stringValue = String(value ?? '')
  if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
    return `"${stringValue.replace(/"/g, '""')}"`
  }
  return stringValue
}

const triggerCsvDownload = (filename: string, headers: string[], rows: Array<Array<string | number>>) => {
  const lines = [headers.join(',')]
  for (const row of rows) {
    lines.push(row.map(escapeCsv).join(','))
  }

  const csv = lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

const triggerBlobDownload = (filename: string, blob: Blob) => {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

const slugifyFilePart = (value: string): string => {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'all'
}

const shortSha = (sha: string): string => {
  const clean = (sha || '').trim()
  return clean ? clean.slice(0, 8) : '-'
}

const stickyColumnConfig = {
  name: { left: 0, width: 140 },
  sapid: { left: 140, width: 76 },
  team: { left: 216, width: 96 },
  scrum: { left: 312, width: 280 },
  total: { left: 592, width: 72 },
} as const

const stickyColumnSx = (left: number, width: number, isHeader = false, showDivider = false) => ({
  position: 'sticky',
  left,
  minWidth: width,
  maxWidth: width,
  backgroundColor: 'background.paper',
  zIndex: isHeader ? 4 : 2,
  ...(showDivider ? { boxShadow: '2px 0 0 rgba(0, 0, 0, 0.08)' } : {}),
})

const clampScore = (score: number): number => {
  if (!Number.isFinite(score)) {
    return 0
  }
  return Math.max(0, Math.min(100, Math.round(score)))
}

const defaultScoreDisplayThresholds: ScoreDisplayThresholds = {
  green_min: 70,
  orange_min: 36,
  red_max: 35,
}

const rgba = (hex: string, alpha: number): string => {
  const normalized = hex.replace('#', '')
  const value = normalized.length === 3
    ? normalized.split('').map((char) => char + char).join('')
    : normalized
  const red = Number.parseInt(value.slice(0, 2), 16)
  const green = Number.parseInt(value.slice(2, 4), 16)
  const blue = Number.parseInt(value.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

const getScoreBand = (score: number, thresholds: ScoreDisplayThresholds): 'green' | 'orange' | 'red' => {
  if (score >= thresholds.green_min) {
    return 'green'
  }
  if (score >= thresholds.orange_min) {
    return 'orange'
  }
  return 'red'
}

const getDialStyles = (score: number, thresholds: ScoreDisplayThresholds) => {
  const band = getScoreBand(score, thresholds)
  const colors = {
    green: '#66BB6A',
    orange: '#FFA726',
    red: '#EF5350',
  } as const
  const foreground = colors[band]

  return {
    band,
    foreground,
    track: rgba(foreground, 0.18),
    border: rgba(foreground, 0.3),
    shadow: rgba(foreground, 0.22),
    background: `linear-gradient(135deg, ${rgba(foreground, 0.14)} 0%, ${rgba(foreground, 0.04)} 100%)`,
  }
}

const defaultScorecard = {
  overall_score: 0,
  productivity_score: 0,
  consistency_score: 0,
  collaboration_score: 0,
  weights: {
    productivity: 40,
    consistency: 35,
    collaboration: 25,
  },
  strictness: 'balanced' as const,
  display_format: 'integer' as const,
  baseline_months: [] as string[],
  selected_month: '',
  gauge_layout: 'overall+3-components' as const,
  rows_scored: 0,
}

const buildThresholdLegend = (thresholds: ScoreDisplayThresholds): string => {
  const orangeUpper = thresholds.green_min - 1
  return `\nColour:  🟢 Green ≥ ${thresholds.green_min}   🟡 Orange ${thresholds.orange_min}–${orangeUpper}   🔴 Red ≤ ${thresholds.red_max}`
}

const buildGaugeTooltips = (thresholds: ScoreDisplayThresholds): Record<string, string> => ({
  Overall:
    'Weighted average of the three component scores.\n' +
    '  = (Productivity × 40%) + (Consistency × 35%) + (Collaboration × 25%)\n' +
    'Baseline: personal 3-month average used as target.' +
    buildThresholdLegend(thresholds),
  Productivity:
    'Measures output volume relative to elapsed working days.\n' +
    '  actual  = total_commits / elapsed_working_days_this_month\n' +
    '  score   = min(100, actual / target × 100)\n' +
    'Target: personal 3-month average daily commit rate (× 1.2 strictness).\n' +
    'For in-progress months, only elapsed working days are counted\n' +
    'so uncommitted future days never penalise the score.\n' +
    'Start Date is respected (pro-rated for new joiners).' +
    buildThresholdLegend(thresholds),
  Consistency:
    'Measures how many elapsed working days had at least one commit.\n' +
    '  actual  = active_days / elapsed_working_days_this_month\n' +
    '  score   = min(100, actual / target × 100)\n' +
    'Target: personal 3-month average active-day ratio (× 1.2 strictness).\n' +
    'For in-progress months, only elapsed working days are counted.\n' +
    'Weekends excluded; Start Date is respected.' +
    buildThresholdLegend(thresholds),
  Collaboration:
    'Measures collaboration via merge ratio.\n' +
    '  actual  = merge_commits / total_commits\n' +
    '  score   = min(100, actual / target × 100)\n' +
    'Target: personal 3-month average merge ratio (× 1.2 strictness).\n' +
    'Falls back to cohort average when personal baseline is thin.' +
    buildThresholdLegend(thresholds),
})

function ScoreGaugeCard({
  label,
  score,
  thresholds,
}: {
  label: string
  score: number
  thresholds: ScoreDisplayThresholds
}) {
  const normalizedScore = clampScore(score)
  const dialStyles = getDialStyles(normalizedScore, thresholds)
  const tooltipText = buildGaugeTooltips(thresholds)[label] ?? ''
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        minWidth: 200,
        flex: '1 1 210px',
        background: dialStyles.background,
        borderColor: dialStyles.border,
        transition: 'transform 0.2s, box-shadow 0.2s, border-color 0.2s',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: `0 8px 24px ${dialStyles.shadow}`,
          borderColor: dialStyles.foreground,
        },
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 1 }}>
        <Typography variant="body2" color="text.secondary">{label}</Typography>
        {tooltipText && (
          <Tooltip
            title={
              <Typography variant="caption" sx={{ whiteSpace: 'pre-line', lineHeight: 1.5 }}>
                {tooltipText}
              </Typography>
            }
            arrow
            placement="top"
          >
            <InfoOutlinedIcon sx={{ fontSize: 14, color: 'text.disabled', cursor: 'help' }} />
          </Tooltip>
        )}
      </Box>
      <Box sx={{ position: 'relative', display: 'inline-flex' }}>
        <CircularProgress variant="determinate" value={100} size={78} thickness={4.6} sx={{ color: dialStyles.track }} />
        <CircularProgress
          variant="determinate"
          value={normalizedScore}
          size={78}
          thickness={4.6}
          sx={{ position: 'absolute', left: 0, color: dialStyles.foreground }}
        />
        <Box
          sx={{
            top: 0,
            left: 0,
            bottom: 0,
            right: 0,
            position: 'absolute',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography variant="h6" component="div" sx={{ fontWeight: 700, color: dialStyles.foreground }}>{normalizedScore}</Typography>
        </Box>
      </Box>
    </Paper>
  )
}

export default function GitActivityReportPage() {
  const [metadataLoading, setMetadataLoading] = useState(false)
  const [loading, setLoading] = useState(false)
  const [detailExportStarting, setDetailExportStarting] = useState(false)
  const [detailExportDownloading, setDetailExportDownloading] = useState(false)
  const [hasRequested, setHasRequested] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<ActionMessage | null>(null)
  const [detailExportJobId, setDetailExportJobId] = useState<string | null>(null)
  const [detailExportStatus, setDetailExportStatus] = useState<GitActivityDetailedExportStatus | null>(null)

  const [rows, setRows] = useState<GitActivityPersonRow[]>([])
  const [availableMonths, setAvailableMonths] = useState<string[]>([])
  const [month, setMonth] = useState('')

  const [availableTeams, setAvailableTeams] = useState<string[]>([])
  const [availableScrums, setAvailableScrums] = useState<string[]>([])
  const [dateColumns, setDateColumns] = useState<string[]>([])
  const [metricLabel, setMetricLabel] = useState('Total Commits')

  const [team, setTeam] = useState('')
  const [scrum, setScrum] = useState('')
  const [activityType, setActivityType] = useState<ActivityType>('total_commits')
  const [employeeScope, setEmployeeScope] = useState<EmployeeScope>('active')
  const [scoreDisplayThresholds, setScoreDisplayThresholds] = useState<ScoreDisplayThresholds>(defaultScoreDisplayThresholds)
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState<string | null>(null)
  const [selectedRow, setSelectedRow] = useState<GitActivityPersonRow | null>(null)
  const [detailsData, setDetailsData] = useState<GitActivityEmployeeDetailsResponse | null>(null)
  const [commitDrawerOpen, setCommitDrawerOpen] = useState(false)
  const [commitDetailsLoading, setCommitDetailsLoading] = useState(false)
  const [commitDetailsError, setCommitDetailsError] = useState<string | null>(null)
  const [selectedCommit, setSelectedCommit] = useState<GitActivityCommitDetail | null>(null)
  const [commitDetailsData, setCommitDetailsData] = useState<GitActivityCommitFileDetailsResponse | null>(null)

  const tableContainerRef = useRef<HTMLDivElement>(null)
  const downloadedDetailExportJobIdRef = useRef<string | null>(null)

  const [summary, setSummary] = useState({
    total_rows: 0,
    metric_total: 0,
    git_activity_scorecard: defaultScorecard,
  })

  useEffect(() => {
    let isMounted = true

    const loadMetadata = async () => {
      setMetadataLoading(true)
      try {
        const response = await reportsApi.getGitActivityMetadata()
        if (!isMounted) {
          return
        }

        setAvailableMonths(response.available_months || [])
        setAvailableTeams(response.available_filters.teams || [])
        setAvailableScrums(response.available_filters.scrums || [])
        if (response.selected_month) {
          setMonth((currentMonth) => currentMonth || response.selected_month)
        }
      } catch (err: any) {
        if (!isMounted) {
          return
        }
        setError(err.response?.data?.detail || 'Failed to load git activity filters')
      } finally {
        if (isMounted) {
          setMetadataLoading(false)
        }
      }
    }

    void loadMetadata()

    return () => {
      isMounted = false
    }
  }, [])

  const loadData = async (monthOverride?: string) => {
    setLoading(true)
    setHasRequested(true)
    setError(null)
    setActionMessage(null)
    try {
      const resolvedMonth = monthOverride ?? month
      const response = await reportsApi.getGitActivityReport({
        month: resolvedMonth || undefined,
        team: team || undefined,
        scrum: scrum || undefined,
        activity_type: activityType,
        employee_scope: employeeScope,
      })

      setRows(response.data)
      setSummary({
        ...response.summary,
        git_activity_scorecard: response.summary.git_activity_scorecard ?? defaultScorecard,
      })
      if (response.score_display_thresholds) {
        setScoreDisplayThresholds(response.score_display_thresholds)
      }
      setDateColumns(response.date_columns || [])
      setMetricLabel(response.metric_label || 'Total Commits')
      setAvailableMonths(response.available_months)
      if (!month || month !== response.selected_month) {
        setMonth(response.selected_month)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load git activity report')
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (hasRequested) {
      void loadData()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activityType])

  const selectedMonthIndex = useMemo(() => availableMonths.findIndex((item) => item === month), [availableMonths, month])
  const canGoPrevious = selectedMonthIndex >= 0 && selectedMonthIndex < availableMonths.length - 1
  const canGoNext = selectedMonthIndex > 0
  const baselineMonthsLabel = useMemo(
    () => summary.git_activity_scorecard.baseline_months.map((monthItem) => formatMonthLabel(monthItem)).join(', '),
    [summary.git_activity_scorecard.baseline_months]
  )

  useEffect(() => {
    if (rows.length > 0 && tableContainerRef.current) {
      tableContainerRef.current.scrollLeft = 0
    }
  }, [rows])

  const lastDataDateKey = useMemo(() => {
    for (let i = dateColumns.length - 1; i >= 0; i--) {
      const key = dateColumns[i]
      if (rows.some((r) => (r.daily_counts?.[key] ?? 0) > 0)) {
        return key
      }
    }
    return dateColumns[dateColumns.length - 1] ?? null
  }, [dateColumns, rows])

  const visibleDateColumns = useMemo(() => {
    if (!lastDataDateKey || dateColumns.length === 0) return [...dateColumns].reverse()
    const idx = dateColumns.indexOf(lastDataDateKey)
    return idx >= 0 ? dateColumns.slice(0, idx + 1).reverse() : [...dateColumns].reverse()
  }, [dateColumns, lastDataDateKey])

  const goToPreviousMonth = () => {
    if (!canGoPrevious) {
      return
    }
    setMonth(availableMonths[selectedMonthIndex + 1])
  }

  const goToNextMonth = () => {
    if (!canGoNext) {
      return
    }
    setMonth(availableMonths[selectedMonthIndex - 1])
  }

  const downloadCurrentView = () => {
    if (rows.length === 0) {
      return
    }

    const headers = [
      'name',
      'sapid',
      'team',
      'scrum',
      'metric_total',
      ...visibleDateColumns,
      'metric_label',
    ]

    const csvRows = rows.map((row) => {
      return [
        row.name,
        row.sapid,
        row.team,
        row.scrum,
        row.metric_total,
        ...visibleDateColumns.map((dateKey) => row.daily_counts?.[dateKey] ?? 0),
        metricLabel,
      ]
    })

    triggerCsvDownload(`git-activity-${month || 'latest'}-${activityType}-matrix.csv`, headers, csvRows)
  }

  const downloadDetailedTeamCsv = async () => {
    if (!team.trim()) {
      setActionMessage({
        severity: 'warning',
        text: 'Detailed CSV export can be generated only on a per-team basis. Select a team and try again.',
      })
      return
    }

    if (!month) {
      setActionMessage({
        severity: 'warning',
        text: 'Select a month before downloading the detailed CSV export.',
      })
      return
    }

    if (detailExportStarting || detailExportDownloading || detailExportStatus?.status === 'pending' || detailExportStatus?.status === 'running') {
      return
    }

    setActionMessage(null)
    setDetailExportStarting(true)
    downloadedDetailExportJobIdRef.current = null

    try {
      const response = await reportsApi.startGitActivityDetailedExport({
        month,
        team,
        scrum: scrum || undefined,
        activity_type: activityType,
        employee_scope: employeeScope,
      })
      setDetailExportJobId(response.job_id)
      setDetailExportStatus(response.status)
      setActionMessage({
        severity: 'info',
        text: `Detailed CSV export started for team ${team}. The file will download automatically when ready.`,
      })
    } catch (err: any) {
      if (err.response?.status === 409 && err.response?.data?.job_id) {
        setDetailExportJobId(err.response.data.job_id)
        if (err.response.data.status) {
          setDetailExportStatus(err.response.data.status)
        }
        setActionMessage({
          severity: 'info',
          text: 'A detailed CSV export is already running. Status tracking has been resumed.',
        })
      } else {
      setActionMessage({
        severity: 'error',
        text: err.response?.data?.detail || 'Failed to generate the detailed Git Activity CSV export',
      })
      }
    } finally {
      setDetailExportStarting(false)
    }
  }

  useEffect(() => {
    if (!detailExportJobId) {
      return
    }

    const exportStatus = detailExportStatus?.status
    if (exportStatus && !['pending', 'running'].includes(exportStatus)) {
      return
    }

    let isMounted = true

    const pollExportStatus = async () => {
      try {
        const status = await reportsApi.getGitActivityDetailedExportStatus(detailExportJobId)
        if (!isMounted) {
          return
        }
        setDetailExportStatus(status)
      } catch (err: any) {
        if (!isMounted) {
          return
        }
        setActionMessage({
          severity: 'error',
          text: err.response?.data?.detail || 'Failed to refresh detailed CSV export status',
        })
      }
    }

    void pollExportStatus()
    const intervalId = window.setInterval(() => {
      void pollExportStatus()
    }, 3000)

    return () => {
      isMounted = false
      window.clearInterval(intervalId)
    }
  }, [detailExportJobId, detailExportStatus?.status])

  useEffect(() => {
    if (!detailExportStatus) {
      return
    }

    if (detailExportStatus.status === 'failed') {
      setActionMessage({
        severity: 'error',
        text: detailExportStatus.error_message || detailExportStatus.message || 'Detailed CSV export failed',
      })
      return
    }

    if (detailExportStatus.status !== 'completed' || !detailExportStatus.download_ready) {
      return
    }

    if (downloadedDetailExportJobIdRef.current === detailExportStatus.job_id) {
      return
    }

    let isMounted = true
    downloadedDetailExportJobIdRef.current = detailExportStatus.job_id
    setDetailExportDownloading(true)

    const downloadCompletedExport = async () => {
      try {
        const blob = await reportsApi.downloadGitActivityDetailedExport(detailExportStatus.job_id)
        if (!isMounted) {
          return
        }
        triggerBlobDownload(
          detailExportStatus.download_filename || `git-activity-${detailExportStatus.selected_month || month}-${slugifyFilePart(team)}-${activityType}-details.csv`,
          blob,
        )
        setActionMessage({
          severity: 'success',
          text: `Detailed CSV exported for team ${detailExportStatus.team || team} in ${formatMonthLabel(detailExportStatus.selected_month || month)}.`,
        })
      } catch (err: any) {
        downloadedDetailExportJobIdRef.current = null
        if (!isMounted) {
          return
        }
        setActionMessage({
          severity: 'error',
          text: err.response?.data?.detail || 'Failed to download the completed detailed CSV export',
        })
      } finally {
        if (isMounted) {
          setDetailExportDownloading(false)
        }
      }
    }

    void downloadCompletedExport()

    return () => {
      isMounted = false
    }
  }, [activityType, detailExportStatus, month, team])

  const detailExportBusy = detailExportStarting
    || detailExportDownloading
    || detailExportStatus?.status === 'pending'
    || detailExportStatus?.status === 'running'

  const handleCloseDetailsDrawer = () => {
    setDetailsDrawerOpen(false)
    setCommitDrawerOpen(false)
    setSelectedCommit(null)
    setCommitDetailsData(null)
    setCommitDetailsError(null)
  }

  const handleCloseCommitDrawer = () => {
    setCommitDrawerOpen(false)
  }

  const handleOpenDetailsDrawer = async (row: GitActivityPersonRow) => {
    if (!month) {
      return
    }

    setSelectedRow(row)
    setDetailsData(null)
    setDetailsError(null)
    setDetailsLoading(true)
    setDetailsDrawerOpen(true)

    try {
      const response = await reportsApi.getGitActivityEmployeeDetails({
        month,
        sapid: row.sapid || undefined,
        author_email: row.author_email || undefined,
      })
      setDetailsData(response)
    } catch (err: any) {
      setDetailsError(err.response?.data?.detail || 'Failed to load commit details')
    } finally {
      setDetailsLoading(false)
    }
  }

  const handleOpenCommitDrawer = async (commit: GitActivityCommitDetail) => {
    if (!month) {
      return
    }

    if (!commit.commit_sha || !commit.commit_sha.trim()) {
      return
    }

    setSelectedCommit(commit)
    setCommitDetailsData(null)
    setCommitDetailsError(null)
    setCommitDetailsLoading(true)
    setCommitDrawerOpen(true)

    try {
      const response = await reportsApi.getGitActivityCommitFileDetails({
        month,
        commit_sha: commit.commit_sha,
        repository: commit.repository || undefined,
        sapid: detailsData?.person?.sapid || selectedRow?.sapid || undefined,
        author_email: detailsData?.person?.author_email || selectedRow?.author_email || undefined,
      })
      setCommitDetailsData(response)
    } catch (err: any) {
      setCommitDetailsError(err.response?.data?.detail || 'Failed to load commit file details')
    } finally {
      setCommitDetailsLoading(false)
    }
  }

  const handleCommitRowCtrlClick = (
    event: ReactMouseEvent<HTMLTableRowElement>,
    commit: GitActivityCommitDetail
  ) => {
    if (!commit.commit_sha || !commit.commit_sha.trim()) {
      return
    }

    if (!event.ctrlKey) {
      return
    }

    event.preventDefault()
    event.stopPropagation()
    void handleOpenCommitDrawer(commit)
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <CommitIcon sx={{ fontSize: 32, color: 'primary.main' }} />
              <Typography variant="h4">Git Activity Report</Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              Monthly per-person Git activity from the shared GitHub + GitLab commit dataset.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} sx={{ ml: 1 }}>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={downloadCurrentView}
              disabled={loading || rows.length === 0}
            >
              Download Matrix CSV
            </Button>
            <Button
              variant="contained"
              startIcon={<DownloadIcon />}
              onClick={() => { void downloadDetailedTeamCsv() }}
              disabled={loading || metadataLoading || detailExportBusy || !month}
            >
              {detailExportStarting
                ? 'Starting Detailed CSV...'
                : detailExportDownloading
                  ? 'Downloading Detailed CSV...'
                  : detailExportStatus?.status === 'pending' || detailExportStatus?.status === 'running'
                    ? 'Detailed CSV Running...'
                    : 'Download Detailed CSV'}
            </Button>
          </Stack>
        </Box>

        <Stack direction="row" spacing={2} flexWrap="wrap" sx={{ mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Month</InputLabel>
            <Select value={month} label="Month" onChange={(e) => setMonth(e.target.value)}>
              {availableMonths.map((item) => (
                <MenuItem key={item} value={item}>{formatMonthLabel(item)}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Button variant="outlined" size="small" startIcon={<NavigateBeforeIcon />} onClick={goToPreviousMonth} disabled={!canGoPrevious || loading}>
              Older
            </Button>
            <Button variant="outlined" size="small" endIcon={<NavigateNextIcon />} onClick={goToNextMonth} disabled={!canGoNext || loading}>
              Newer
            </Button>
          </Box>

          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Employees</InputLabel>
            <Select value={employeeScope} label="Employees" onChange={(e) => setEmployeeScope(e.target.value as EmployeeScope)}>
              <MenuItem value="active">Active Only</MenuItem>
              <MenuItem value="inactive">Inactive Only</MenuItem>
              <MenuItem value="all">All Employees</MenuItem>
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

          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={() => loadData(month)}
            disabled={loading || metadataLoading || availableMonths.length === 0}
            sx={{ alignSelf: 'center', height: 40 }}
          >
            Run Report
          </Button>

        </Stack>

        {!loading && !error && (
          <Box sx={{ mb: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <Chip label={`Month: ${formatMonthLabel(month)}`} color="primary" variant="outlined" />
            <Chip label={`People: ${summary.total_rows}`} variant="outlined" />
            <Chip label={`${metricLabel}: ${summary.metric_total}`} color="success" variant="outlined" />
            {summary.git_activity_scorecard.rows_scored > 0 && (
              <Chip label={`Baseline: ${baselineMonthsLabel || 'N/A'}`} variant="outlined" />
            )}
          </Box>
        )}

        {!loading && !error && summary.git_activity_scorecard.rows_scored > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Git Activity Score (0-100)</Typography>
            <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
              <ScoreGaugeCard label="Overall" score={summary.git_activity_scorecard.overall_score} thresholds={scoreDisplayThresholds} />
              <ScoreGaugeCard label="Productivity" score={summary.git_activity_scorecard.productivity_score} thresholds={scoreDisplayThresholds} />
              <ScoreGaugeCard label="Consistency" score={summary.git_activity_scorecard.consistency_score} thresholds={scoreDisplayThresholds} />
              <ScoreGaugeCard label="Collaboration" score={summary.git_activity_scorecard.collaboration_score} thresholds={scoreDisplayThresholds} />
            </Box>
          </Box>
        )}

        <Box sx={{ mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 170 }}>
            <InputLabel>Activity</InputLabel>
            <Select value={activityType} label="Activity" onChange={(e) => setActivityType(e.target.value as ActivityType)}>
              <MenuItem value="total_commits">Total Commits</MenuItem>
              <MenuItem value="merges">Merges Only</MenuItem>
              <MenuItem value="commits">Non-Merge Commits</MenuItem>
              <MenuItem value="lines_added">Added LOC</MenuItem>
              <MenuItem value="lines_deleted">Deleted LOC</MenuItem>
              <MenuItem value="lines_changed">Changed LOC</MenuItem>
              <MenuItem value="files_changed">Files Changed</MenuItem>
              <MenuItem value="repos_touched">Repos Touched</MenuItem>
            </Select>
          </FormControl>
        </Box>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

        {actionMessage && <Alert severity={actionMessage.severity} sx={{ mb: 2 }}>{actionMessage.text}</Alert>}

        {detailExportStatus && (
          <Alert
            severity={detailExportStatus.status === 'failed' ? 'error' : detailExportStatus.status === 'completed' ? 'success' : 'info'}
            sx={{ mb: 2 }}
          >
            {`Detailed export status: ${detailExportStatus.status.toUpperCase()} (${detailExportStatus.progress_percent}%). ${detailExportStatus.message || detailExportStatus.current_step}`}
          </Alert>
        )}

        {(loading || metadataLoading) && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        )}

        {!loading && !error && rows.length > 0 && (
          <TableContainer ref={tableContainerRef} sx={{ maxHeight: 'calc(100vh - 340px)' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell
                    sx={{
                      fontWeight: 'bold',
                      px: 1,
                      py: 0.75,
                      whiteSpace: 'nowrap',
                      ...stickyColumnSx(stickyColumnConfig.name.left, stickyColumnConfig.name.width, true),
                    }}
                  >
                    Name
                  </TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 'bold',
                      px: 1,
                      py: 0.75,
                      whiteSpace: 'nowrap',
                      ...stickyColumnSx(stickyColumnConfig.sapid.left, stickyColumnConfig.sapid.width, true),
                    }}
                  >
                    SAPID
                  </TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 'bold',
                      px: 1,
                      py: 0.75,
                      whiteSpace: 'nowrap',
                      ...stickyColumnSx(stickyColumnConfig.team.left, stickyColumnConfig.team.width, true),
                    }}
                  >
                    Team
                  </TableCell>
                  <TableCell
                    sx={{
                      fontWeight: 'bold',
                      px: 1,
                      py: 0.75,
                      whiteSpace: 'nowrap',
                      ...stickyColumnSx(stickyColumnConfig.scrum.left, stickyColumnConfig.scrum.width, true, true),
                    }}
                  >
                    Scrum
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      fontWeight: 'bold',
                      px: 1,
                      py: 0.75,
                      whiteSpace: 'nowrap',
                      ...stickyColumnSx(stickyColumnConfig.total.left, stickyColumnConfig.total.width, true, true),
                    }}
                  >
                    Total
                  </TableCell>
                  {visibleDateColumns.map((dateKey) => (
                    <TableCell
                      key={dateKey}
                      align="right"
                      sx={{
                        fontWeight: 'bold',
                        minWidth: 54,
                        px: 0.75,
                        py: 0.75,
                        fontSize: '0.72rem',
                        lineHeight: 1.15,
                        whiteSpace: 'nowrap',
                        ...(dateKey === lastDataDateKey ? { backgroundColor: '#e3f0fb', borderLeft: '2px solid rgba(25, 118, 210, 0.5)', zIndex: 5 } : {}),
                      }}
                    >
                      {formatDateColumnLabel(dateKey)}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={`${row.author_email}-${row.name}`}
                    hover
                    onClick={() => { void handleOpenDetailsDrawer(row) }}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell
                      sx={{
                        px: 1,
                        py: 0.5,
                        whiteSpace: 'nowrap',
                        ...stickyColumnSx(stickyColumnConfig.name.left, stickyColumnConfig.name.width),
                      }}
                    >
                      {row.name || '-'}
                    </TableCell>
                    <TableCell
                      sx={{
                        px: 1,
                        py: 0.5,
                        whiteSpace: 'nowrap',
                        ...stickyColumnSx(stickyColumnConfig.sapid.left, stickyColumnConfig.sapid.width),
                      }}
                    >
                      {row.sapid || '-'}
                    </TableCell>
                    <TableCell
                      sx={{
                        px: 1,
                        py: 0.5,
                        whiteSpace: 'nowrap',
                        ...stickyColumnSx(stickyColumnConfig.team.left, stickyColumnConfig.team.width),
                      }}
                    >
                      {row.team || '-'}
                    </TableCell>
                    <TableCell
                      sx={{
                        px: 1,
                        py: 0.5,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        ...stickyColumnSx(stickyColumnConfig.scrum.left, stickyColumnConfig.scrum.width, false, true),
                      }}
                      title={row.scrum || '-'}
                    >
                      {row.scrum || '-'}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        px: 1,
                        py: 0.5,
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                        ...stickyColumnSx(stickyColumnConfig.total.left, stickyColumnConfig.total.width, false, true),
                      }}
                    >
                      {row.metric_total}
                    </TableCell>
                    {visibleDateColumns.map((dateKey) => (
                      <TableCell
                        key={`${row.author_email}-${dateKey}`}
                        align="right"
                        sx={{
                          px: 0.75,
                          py: 0.5,
                          fontSize: '0.75rem',
                          whiteSpace: 'nowrap',
                          ...(dateKey === lastDataDateKey ? { backgroundColor: 'rgba(25, 118, 210, 0.06)', borderLeft: '2px solid rgba(25, 118, 210, 0.5)' } : {}),
                        }}
                      >
                        {row.daily_counts?.[dateKey] ?? 0}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {!loading && !error && hasRequested && rows.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="body1" color="text.secondary">No git activity rows for the selected filters.</Typography>
          </Box>
        )}

        {!loading && !error && !hasRequested && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="body1" color="text.secondary">
              Choose filters and click Run Report to load data.
            </Typography>
          </Box>
        )}
      </Paper>

      <Drawer
        anchor="right"
        open={detailsDrawerOpen}
        onClose={handleCloseDetailsDrawer}
        sx={{
          '& .MuiDrawer-paper': {
            width: { xs: '100%', sm: 900, md: 1040 },
            p: 2,
          },
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Box>
            <Typography variant="h6" sx={{ lineHeight: 1.2 }}>
              {(detailsData?.person?.name || selectedRow?.name || 'Employee') +
                ` activity details for month ${formatMonthLabel(month)}`}
            </Typography>
          </Box>
          <IconButton size="small" onClick={handleCloseDetailsDrawer}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1.5 }}>
          <Chip size="small" label={`SAPID: ${detailsData?.person?.sapid || selectedRow?.sapid || '-'}`} />
          <Chip size="small" label={`Team: ${detailsData?.person?.team || selectedRow?.team || '-'}`} />
          <Chip size="small" label={`Scrum: ${detailsData?.person?.scrum || selectedRow?.scrum || '-'}`} />
        </Stack>

        {detailsData && (
          <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1.5 }}>
            <Chip size="small" color="primary" variant="outlined" label={`Commits: ${detailsData.summary.total_commits}`} />
            <Chip size="small" variant="outlined" label={`Merges: ${detailsData.summary.merge_commits}`} />
            <Chip size="small" variant="outlined" label={`Non-Merge: ${detailsData.summary.non_merge_commits}`} />
            <Chip size="small" variant="outlined" label={`LOC Changed: ${detailsData.summary.total_lines_changed}`} />
            <Chip size="small" variant="outlined" label={`Files Changed: ${detailsData.summary.total_files_changed}`} />
          </Stack>
        )}

        <Divider sx={{ mb: 1.5 }} />

        {detailsError && (
          <Alert severity="error" sx={{ mb: 1.5 }}>
            {detailsError}
          </Alert>
        )}

        {detailsLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={24} />
          </Box>
        )}

        {!detailsLoading && !detailsError && detailsData && detailsData.commits.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No commits found for this user in the selected month.
          </Typography>
        )}

        {!detailsLoading && !detailsError && detailsData && detailsData.commits.length > 0 && (
          <TableContainer sx={{ maxHeight: 'calc(100vh - 220px)' }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }}>Date</TableCell>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }}>Type</TableCell>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }}>SHA</TableCell>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }} align="right">+/- LOC</TableCell>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }}>JIRA ID</TableCell>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }}>Repo</TableCell>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }}>Message</TableCell>
                  <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5 }} align="right">Files</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {detailsData.commits.map((commit: GitActivityCommitDetail) => (
                  <TableRow
                    key={`${commit.commit_sha}-${commit.date}-${commit.repository}`}
                    onClick={(event) => { handleCommitRowCtrlClick(event, commit) }}
                    onContextMenu={(event) => { handleCommitRowCtrlClick(event, commit) }}
                    sx={{ cursor: 'default' }}
                  >
                    <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                      {commit.date}
                    </TableCell>
                    <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                      {commit.is_merge ? (
                        <Chip size="small" color="warning" label="MERGE" sx={{ height: 18, fontSize: '0.65rem', fontWeight: 700 }} />
                      ) : (
                        <Chip size="small" variant="outlined" label="COMMIT" sx={{ height: 18, fontSize: '0.65rem' }} />
                      )}
                    </TableCell>
                    <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                      {shortSha(commit.commit_sha)}
                    </TableCell>
                    <TableCell align="right" sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                      {`${commit.lines_added}/${commit.lines_deleted}`}
                    </TableCell>
                    <TableCell
                      sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={commit.jira_id || '-'}
                    >
                      {commit.jira_id || '-'}
                    </TableCell>
                    <TableCell
                      sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={commit.repository}
                    >
                      {commit.repository || '-'}
                    </TableCell>
                    <TableCell
                      sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={commit.message}
                    >
                      {commit.message || '-'}
                    </TableCell>
                    <TableCell align="right" sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                      {commit.files_changed}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Drawer>

      <Drawer
        anchor="right"
        open={commitDrawerOpen}
        onClose={handleCloseCommitDrawer}
        sx={{
          '& .MuiDrawer-paper': {
            width: { xs: '100%', sm: 560 },
            p: 2,
            right: { xs: 0, md: 1040 },
            zIndex: 1400,
          },
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Box>
            <Typography variant="h6" sx={{ lineHeight: 1.2 }}>
              Commit Analysis {selectedCommit ? shortSha(selectedCommit.commit_sha) : ''}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              File and component LOC summary for the selected activity
            </Typography>
          </Box>
          <IconButton size="small" onClick={handleCloseCommitDrawer}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        {commitDetailsError && (
          <Alert severity="error" sx={{ mb: 1.5 }}>
            {commitDetailsError}
          </Alert>
        )}

        {commitDetailsLoading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={24} />
          </Box>
        )}

        {!commitDetailsLoading && !commitDetailsError && commitDetailsData && (
          <>
            {!!commitDetailsData.warning && (
              <Alert severity="warning" sx={{ mb: 1.5 }}>
                {commitDetailsData.warning}
              </Alert>
            )}

            <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1.5 }}>
              <Chip size="small" label={`Date: ${commitDetailsData.commit.date || '-'}`} />
              <Chip size="small" label={`Repo: ${commitDetailsData.commit.repository || '-'}`} />
              <Chip size="small" label={`JIRA: ${commitDetailsData.commit.jira_id || '-'}`} />
            </Stack>

            <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mb: 1.5 }}>
              <Chip size="small" color="primary" variant="outlined" label={`Files: ${commitDetailsData.summary.files_count}`} />
              <Chip size="small" variant="outlined" label={`+${commitDetailsData.summary.lines_added}`} />
              <Chip size="small" variant="outlined" label={`-${commitDetailsData.summary.lines_deleted}`} />
              <Chip size="small" variant="outlined" label={`Changed: ${commitDetailsData.summary.lines_changed}`} />
            </Stack>

            <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Component Summary</Typography>
            <TableContainer sx={{ maxHeight: 180, mb: 1.5 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }}>Component</TableCell>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">Files</TableCell>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">+/-</TableCell>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">Changed</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {commitDetailsData.components.map((component) => (
                    <TableRow key={component.component} hover>
                      <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem' }}>{component.component || '-'}</TableCell>
                      <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">{component.files_count}</TableCell>
                      <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">{`${component.lines_added}/${component.lines_deleted}`}</TableCell>
                      <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">{component.lines_changed}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Files</Typography>
            <TableContainer sx={{ maxHeight: 'calc(100vh - 360px)' }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }}>File</TableCell>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">+/-</TableCell>
                    <TableCell sx={{ fontWeight: 700, px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">Changed</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {commitDetailsData.files.map((file) => (
                    <TableRow key={`${file.filepath}-${file.status}-${file.lines_changed}`} hover>
                      <TableCell
                        sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem', maxWidth: 330, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                        title={file.filepath}
                      >
                        {file.filepath || '-'}
                      </TableCell>
                      <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem' }}>{file.status || '-'}</TableCell>
                      <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">{`${file.lines_added}/${file.lines_deleted}`}</TableCell>
                      <TableCell sx={{ px: 0.75, py: 0.5, fontSize: '0.75rem' }} align="right">{file.lines_changed}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}
      </Drawer>
    </Container>
  )
}
