import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Chip,
  Container,
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
  Typography,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DownloadForOfflineIcon from '@mui/icons-material/DownloadForOffline'
import FilterListIcon from '@mui/icons-material/FilterList'
import {
  reportsApi,
  UdeInstallationEmployeeDetailsResponse,
  UdeInstallationsFiltersResponse,
  UdeInstallationsReportResponse,
  UdeInstallationsReportRow,
} from '../services/reportsApi'
import { useAuth } from '../context/AuthContext'

type ComplianceFilter = 'all' | 'compliant' | 'non_compliant'
type EmployeeScope = 'active' | 'all'

const formatDays = (value: number): string => `${Number.isFinite(value) ? value.toFixed(1) : '0.0'}d`

const isDeviceRow = (row: UdeInstallationsReportRow): boolean => (
  row.row_type === 'DEVICE' || row.row_type === 'DEVICE_EXCEPTION'
)

const formatDetailDate = (value: string, fallback = '-'): string => {
  if (!value) return fallback
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString()
}

const displayDelay = (row: UdeInstallationsReportRow, value: number, deviceOnly = false): string => {
  if (deviceOnly && !isDeviceRow(row)) return '-'
  return formatDays(value)
}

export default function UdeInstallationsReportPage() {
  const [loading, setLoading] = useState(false)
  const [filtersLoading, setFiltersLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<UdeInstallationsReportResponse | null>(null)
  const [filters, setFilters] = useState<UdeInstallationsFiltersResponse | null>(null)

  const { user } = useAuth()
  const [team, setTeam] = useState('')
  const [scrum, setScrum] = useState('')
  const [version, setVersion] = useState('')
  const [compliance, setCompliance] = useState<ComplianceFilter>('non_compliant')
  const [employeeScope, setEmployeeScope] = useState<EmployeeScope>('active')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selectedRow, setSelectedRow] = useState<UdeInstallationsReportRow | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [employeeDetails, setEmployeeDetails] = useState<UdeInstallationEmployeeDetailsResponse | null>(null)

  const loadFilters = async (scope: EmployeeScope = employeeScope) => {
    console.log('loadFilters called with scope:', scope, 'user:', user)
    setFiltersLoading(true)
    setError(null)
    try {
      console.log('Calling API with employee_scope:', scope)
      const f = await reportsApi.getUdeInstallationsFilters({ employee_scope: scope })
      console.log('Filters response:', f)
      setFilters(f)

      // Set defaults: use latest version and try to match user's first team
      if (f.versions.length > 0 && !version) {
        const latestVersion = f.versions[0]
        console.log('Setting default version to:', latestVersion)
        setVersion(latestVersion)
      }
      if (f.teams.length > 0 && !team && user?.team_ids?.length) {
        const firstTeam = f.teams[0]
        console.log('Setting default team to:', firstTeam)
        setTeam(firstTeam)
      }
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail || err?.message || 'Failed to load UDE filter options'
      console.error('Error loading filters:', errMsg, err)
      setError(errMsg)
    } finally {
      setFiltersLoading(false)
    }
  }

  const loadReport = async (override?: Partial<{ team: string; scrum: string; version: string; compliance: ComplianceFilter; employeeScope: EmployeeScope }>) => {
    const selectedTeam = override?.team ?? team
    const selectedScrum = override?.scrum ?? scrum
    const selectedVersion = override?.version ?? version
    const selectedCompliance = override?.compliance ?? compliance
    const selectedScope = override?.employeeScope ?? employeeScope

    try {
      setLoading(true)
      setError(null)

      const response = await reportsApi.getUdeInstallationsReport({
        team: selectedTeam || undefined,
        scrum: selectedScrum || undefined,
        version: selectedVersion || undefined,
        compliance_filter: selectedCompliance,
        employee_scope: selectedScope,
      })

      setReport(response)

      if (!version && response.applied_filters.version) {
        setVersion(response.applied_filters.version)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load UDE installations report')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadFilters()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const rows = report?.data ?? []
  const summary = report?.summary

  const summaryCards = useMemo(() => {
    if (!summary) return []
    return [
      { label: 'Employees', value: `${summary.total_employees}` },
      { label: 'Employee Compliance', value: `${summary.employee_compliance_percent.toFixed(1)}%` },
      { label: 'Device Compliance', value: `${summary.device_compliance_percent.toFixed(1)}%` },
      { label: 'Rows (Filtered / Total)', value: `${summary.filtered_rows}/${summary.total_rows}` },
    ]
  }, [summary])

  const handleCloseDrawer = () => {
    setDrawerOpen(false)
    setSelectedRow(null)
    setDetailError(null)
    setEmployeeDetails(null)
  }

  const handleOpenDrawer = async (row: UdeInstallationsReportRow) => {
    setSelectedRow(row)
    setDrawerOpen(true)
    setDetailLoading(true)
    setDetailError(null)

    try {
      const response = await reportsApi.getUdeInstallationEmployeeDetails(row.sapid, {
        employee_scope: employeeScope,
      })
      setEmployeeDetails(response)
    } catch (err: any) {
      setEmployeeDetails(null)
      setDetailError(err?.response?.data?.detail || err?.message || 'Failed to load employee UDE installation details')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleRowKeyDown = async (event: React.KeyboardEvent, row: UdeInstallationsReportRow) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      await handleOpenDrawer(row)
    }
  }

  return (
    <Container maxWidth={false} sx={{ py: 3 }}>
      <Stack spacing={2.5}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <DownloadForOfflineIcon sx={{ fontSize: 32, color: 'primary.main' }} />
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            UDE Installations Report
          </Typography>
        </Box>

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ xs: 'stretch', md: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel id="ude-team-label">Team</InputLabel>
              <Select
                labelId="ude-team-label"
                value={team}
                label="Team"
                onChange={(event) => setTeam(event.target.value)}
              >
                <MenuItem value="">All Teams</MenuItem>
                {(filters?.teams ?? []).map((item) => (
                  <MenuItem key={item} value={item}>{item}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel id="ude-scrum-label">Scrum</InputLabel>
              <Select
                labelId="ude-scrum-label"
                value={scrum}
                label="Scrum"
                onChange={(event) => setScrum(event.target.value)}
              >
                <MenuItem value="">All Scrums</MenuItem>
                {(filters?.scrums ?? []).map((item) => (
                  <MenuItem key={item} value={item}>{item}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id="ude-version-label">UDE Version</InputLabel>
              <Select
                labelId="ude-version-label"
                value={version}
                label="UDE Version"
                onChange={(event) => setVersion(event.target.value)}
              >
                {(filters?.versions ?? []).map((item) => (
                  <MenuItem key={item} value={item}>{item}</MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel id="ude-compliance-label">Compliance</InputLabel>
              <Select
                labelId="ude-compliance-label"
                value={compliance}
                label="Compliance"
                onChange={(event) => setCompliance(event.target.value as ComplianceFilter)}
              >
                <MenuItem value="non_compliant">Non-compliant</MenuItem>
                <MenuItem value="compliant">Compliant</MenuItem>
                <MenuItem value="all">All</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 150 }}>
              <InputLabel id="ude-scope-label">Employee Scope</InputLabel>
              <Select
                labelId="ude-scope-label"
                value={employeeScope}
                label="Employee Scope"
                onChange={(event) => setEmployeeScope(event.target.value as EmployeeScope)}
              >
                <MenuItem value="active">Active</MenuItem>
                <MenuItem value="all">All</MenuItem>
              </Select>
            </FormControl>

            <Button
              variant="contained"
              startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <FilterListIcon />}
              onClick={() => loadReport()}
              disabled={loading || filtersLoading}
            >
              Apply Filters
            </Button>
          </Stack>
        </Paper>

        {error && <Alert severity="error">{error}</Alert>}

        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.2} flexWrap="wrap" useFlexGap>
          {summaryCards.map((card) => (
            <Paper key={card.label} variant="outlined" sx={{ px: 1.5, py: 1, minWidth: 170 }}>
              <Typography variant="caption" color="text.secondary">{card.label}</Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>{card.value}</Typography>
            </Paper>
          ))}
        </Stack>

        <Paper variant="outlined">
          <TableContainer sx={{ maxHeight: '72vh' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Row Type</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>SAPID</TableCell>
                  <TableCell>Team</TableCell>
                  <TableCell>Scrum</TableCell>
                  <TableCell>Compliance</TableCell>
                  <TableCell>Target Version</TableCell>
                  <TableCell align="right">Current Delay</TableCell>
                  <TableCell align="right">Devices (C/NC)</TableCell>
                  <TableCell>Device Id</TableCell>
                  <TableCell>Installed Version</TableCell>
                  <TableCell align="right">Device Delay</TableCell>
                  <TableCell align="center">Details</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={13} align="center" sx={{ py: 4 }}>
                      <CircularProgress size={24} />
                      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Loading report...</Typography>
                    </TableCell>
                  </TableRow>
                ) : report === null ? (
                  <TableRow>
                    <TableCell colSpan={13} align="center" sx={{ py: 6 }}>
                      <FilterListIcon sx={{ fontSize: 40, color: 'text.disabled', mb: 1 }} />
                      <Typography variant="body1" color="text.secondary">Select filters above and click <strong>Apply Filters</strong> to load the report.</Typography>
                    </TableCell>
                  </TableRow>
                ) : rows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={13} align="center" sx={{ py: 4 }}>
                      <Typography variant="body2" color="text.secondary">No rows found for selected filters.</Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((row, index) => (
                    <TableRow
                      key={`${row.sapid}-${row.row_type}-${row.device_id || 'summary'}-${index}`}
                      hover
                      onClick={() => handleOpenDrawer(row)}
                      onKeyDown={(event) => handleRowKeyDown(event, row)}
                      tabIndex={0}
                      role="button"
                      sx={{ cursor: 'pointer' }}
                    >
                      <TableCell>
                        <Chip
                          size="small"
                          label={row.row_type === 'EMPLOYEE_SUMMARY' ? 'Summary' : 'Device'}
                          color={row.row_type === 'EMPLOYEE_SUMMARY' ? 'primary' : 'info'}
                          variant={row.row_type === 'EMPLOYEE_SUMMARY' ? 'outlined' : 'filled'}
                        />
                      </TableCell>
                      <TableCell>{row.name}</TableCell>
                      <TableCell>{row.sapid}</TableCell>
                      <TableCell>{row.team || '-'}</TableCell>
                      <TableCell>{row.scrum || '-'}</TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={row.compliance_status === 'COMPLIANT' ? 'Compliant' : 'Non-compliant'}
                          color={row.compliance_status === 'COMPLIANT' ? 'success' : 'error'}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>{row.current_version}</TableCell>
                      <TableCell align="right">{displayDelay(row, row.current_delay_days)}</TableCell>
                      <TableCell align="right">{`${row.compliant_devices}/${row.non_compliant_devices}`}</TableCell>
                      <TableCell>{isDeviceRow(row) ? (row.device_id || '-') : '-'}</TableCell>
                      <TableCell>{isDeviceRow(row) ? (row.device_version || '-') : '-'}</TableCell>
                      <TableCell align="right">{displayDelay(row, row.device_delay_days, true)}</TableCell>
                      <TableCell align="center">
                        <Button
                          size="small"
                          variant="text"
                          onClick={(event) => {
                            event.stopPropagation()
                            void handleOpenDrawer(row)
                          }}
                        >
                          Open
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>

        <Drawer
          anchor="right"
          open={drawerOpen}
          onClose={handleCloseDrawer}
          PaperProps={{
            sx: {
              width: { xs: '100%', sm: 720 },
              display: 'flex',
            },
          }}
        >
          <Box
            sx={{
              p: 2,
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              minHeight: 0,
            }}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Box>
                <Typography variant="h6">{selectedRow?.name || 'Employee'} UDE Installations</Typography>
                <Typography variant="body2" color="text.secondary">
                  SAPID: {selectedRow?.sapid || '-'}
                  {employeeDetails?.latest_target_version ? ` • Latest Target: ${employeeDetails.latest_target_version}` : ''}
                </Typography>
              </Box>
              <IconButton onClick={handleCloseDrawer} size="small">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Box>

            {detailLoading ? (
              <Box display="flex" justifyContent="center" alignItems="center" flex={1}>
                <CircularProgress size={28} />
              </Box>
            ) : detailError ? (
              <Alert severity="error">{detailError}</Alert>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, gap: 1.5 }}>
                <Typography variant="body2" color="text.secondary">
                  {employeeDetails?.employee.team ? `Team: ${employeeDetails.employee.team}` : 'Team: -'}
                  {' • '}
                  {employeeDetails?.employee.scrum ? `Scrum: ${employeeDetails.employee.scrum}` : 'Scrum: -'}
                  {' • '}
                  Installations: {employeeDetails?.data.length ?? 0}
                </Typography>

                <TableContainer sx={{ flex: 1, minHeight: 0 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>UDE Version</TableCell>
                        <TableCell>Device ID</TableCell>
                        <TableCell>Device Label</TableCell>
                        <TableCell>Date Version Available</TableCell>
                        <TableCell>Date of Install</TableCell>
                        <TableCell align="right">Computed Delay</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(employeeDetails?.data ?? []).length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} align="center" sx={{ py: 4 }}>
                            <Typography variant="body2" color="text.secondary">
                              No installation details found for this employee.
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ) : (
                        (employeeDetails?.data ?? []).map((detail, detailIndex) => (
                          <TableRow key={`${detail.device_id}-${detail.ude_version}-${detail.installed_date || detailIndex}`}>
                            <TableCell>
                              <Stack direction="row" spacing={1} alignItems="center">
                                <Typography variant="body2">{detail.ude_version}</Typography>
                                {detail.is_latest_target_version && (
                                  <Chip size="small" label="Latest" color="success" variant="outlined" />
                                )}
                              </Stack>
                            </TableCell>
                            <TableCell>{detail.device_id}</TableCell>
                            <TableCell>{detail.device_label || '-'}</TableCell>
                            <TableCell>{formatDetailDate(detail.release_date)}</TableCell>
                            <TableCell>{formatDetailDate(detail.installed_date, 'Not Installed')}</TableCell>
                            <TableCell align="right">{formatDays(detail.computed_delay_days)}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            )}
          </Box>
        </Drawer>
      </Stack>
    </Container>
  )
}
