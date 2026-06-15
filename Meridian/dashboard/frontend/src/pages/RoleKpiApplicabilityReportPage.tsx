import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Drawer,
  Grid,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography
} from '@mui/material'
import RefreshIcon from '@mui/icons-material/Refresh'
import FactCheckIcon from '@mui/icons-material/FactCheck'
import CloseIcon from '@mui/icons-material/Close'
import { reportsApi, RoleKpiApplicabilityItem } from '../services/reportsApi'

const ALL_KPIS_ROLE_LABEL = 'All KPIs'

const TYPE_LABELS: Record<string, string> = {
  PG: 'Percentage Greater than',
  NG: 'Number Greater than',
  NL: 'Number Lower than',
  PL: 'Percentage Lower than',
  RG: 'Ratio Greater than',
  TG: 'Team Goal',
  AG: 'Aggregate Greater than',
  AL: 'Aggregate Lower than',
  F: 'Fixed Value',
}

const AGGREGATION_TYPE_LABELS: Record<string, string> = {
  ANG: 'Aggregated Number Greater than',
  ANL: 'Aggregated Number Lower than',
  APG: 'Aggregated Percentage Greater than',
  APL: 'Aggregated Percentage Lower than',
}

const getExpandedTypeLabel = (code: string): string => {
  const normalized = (code || '').trim().toUpperCase()
  if (!normalized) {
    return '-'
  }
  const expanded = TYPE_LABELS[normalized]
  return expanded ? `${normalized} - ${expanded}` : normalized
}

const getExpandedAggregationTypeLabel = (code: string): string => {
  const normalized = (code || '').trim().toUpperCase()
  if (!normalized) {
    return '-'
  }
  const expanded = AGGREGATION_TYPE_LABELS[normalized]
  return expanded ? `${normalized} - ${expanded}` : normalized
}

export default function RoleKpiApplicabilityReportPage() {
  const [roles, setRoles] = useState<string[]>([])
  const [selectedRole, setSelectedRole] = useState('')
  const [data, setData] = useState<RoleKpiApplicabilityItem[]>([])
  const [sharedRoleBuckets, setSharedRoleBuckets] = useState<string[]>([])
  const [appliedRoleBuckets, setAppliedRoleBuckets] = useState<string[]>([])
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({})
  const [totalKpis, setTotalKpis] = useState(0)
  const [implementedKpis, setImplementedKpis] = useState(0)
  const [pendingKpis, setPendingKpis] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false)
  const [selectedKpi, setSelectedKpi] = useState<RoleKpiApplicabilityItem | null>(null)
  const [goalTypeFilter, setGoalTypeFilter] = useState<string>('has_value')
  const [implementationStatusFilter, setImplementationStatusFilter] = useState<string>('implemented')

  useEffect(() => {
    loadReport(ALL_KPIS_ROLE_LABEL)
  }, [])

  const loadReport = async (role?: string) => {
    setLoading(true)
    setError(null)

    try {
      const response = await reportsApi.getRoleKpiApplicabilityReport(role)
      setRoles(response.roles.includes(ALL_KPIS_ROLE_LABEL) ? response.roles : [...response.roles, ALL_KPIS_ROLE_LABEL])
      setSelectedRole(response.selected_role)
      setData(response.data)
      setSharedRoleBuckets(response.shared_role_buckets)
      setAppliedRoleBuckets(response.applied_role_buckets)
      setSourceCounts(response.source_counts)
      setTotalKpis(response.total_kpis)
      setImplementedKpis(response.implemented_kpis)
      setPendingKpis(response.pending_kpis)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load role KPI applicability report')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleRoleChange = (role: string) => {
    setSelectedRole(role)
    loadReport(role)
  }

  const handleViewKpi = (kpi: RoleKpiApplicabilityItem) => {
    setSelectedKpi(kpi)
    setDetailsDrawerOpen(true)
  }

  const getSourceColor = (sourceRole: string) => {
    if (sourceRole === selectedRole) {
      return 'primary'
    }
    if (sourceRole === 'Common') {
      return 'secondary'
    }
    if (sourceRole === 'All') {
      return 'info'
    }
    return 'default'
  }

  const frozenColumnSx = (left: number, isHeader = false) => ({
    position: 'sticky',
    left,
    backgroundColor: 'background.paper',
    zIndex: isHeader ? 6 : 2,
    boxShadow: '1px 0 0 rgba(0, 0, 0, 0.08)'
  })

  const availableGoalTypes = useMemo(() => {
    const unique = new Set<string>()
    data.forEach((item) => {
      const value = (item.goal_type || '').trim()
      if (value) {
        unique.add(value)
      }
    })
    return Array.from(unique).sort((a, b) => a.localeCompare(b))
  }, [data])

  const filteredData = useMemo(() => {
    return data.filter((item) => {
      const hasGoalType = Boolean((item.goal_type || '').trim())

      const goalTypeMatches =
        goalTypeFilter === 'all' ? true :
        goalTypeFilter === 'has_value' ? hasGoalType :
        (item.goal_type || '').trim() === goalTypeFilter

      const implementationMatches =
        implementationStatusFilter === 'all' ? true :
        implementationStatusFilter === 'implemented' ? item.implemented :
        !item.implemented

      return goalTypeMatches && implementationMatches
    })
  }, [data, goalTypeFilter, implementationStatusFilter])

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <FactCheckIcon sx={{ fontSize: 32, color: 'primary.main' }} />
              <Typography variant="h4">
                Role KPI Applicability Report
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary">
              Roles are derived from Roles.csv. Each report includes role-specific KPIs plus shared buckets from Common, All, and Metric/Metrics when present.
            </Typography>
          </Box>
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            size="small"
            onClick={() => loadReport(selectedRole || undefined)}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>

        <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
          <TextField
            select
            label="Role"
            value={selectedRole}
            onChange={(e) => handleRoleChange(e.target.value)}
            size="small"
            sx={{ minWidth: 280 }}
            disabled={loading || roles.length === 0}
          >
            {roles.map((role) => (
              <MenuItem key={role} value={role}>{role}</MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Goal Type"
            value={goalTypeFilter}
            onChange={(e) => setGoalTypeFilter(e.target.value)}
            size="small"
            sx={{ minWidth: 220 }}
            disabled={loading}
          >
            <MenuItem value="all">All Goal Types</MenuItem>
            <MenuItem value="has_value">Has Value</MenuItem>
            {availableGoalTypes.map((goalType) => (
              <MenuItem key={goalType} value={goalType}>{goalType}</MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Implementation Status"
            value={implementationStatusFilter}
            onChange={(e) => setImplementationStatusFilter(e.target.value)}
            size="small"
            sx={{ minWidth: 220 }}
            disabled={loading}
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="implemented">Implemented</MenuItem>
            <MenuItem value="not_implemented">Not yet implemented</MenuItem>
          </TextField>
        </Box>

        {!loading && !error && (
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 2 }}>
            <Chip label={`${totalKpis} Applicable KPIs`} color="primary" variant="outlined" />
            <Chip label={`${filteredData.length} Filtered KPIs`} color="info" variant="outlined" />
            <Chip label={`${implementedKpis} Implemented`} color="success" variant="outlined" />
            <Chip label={`${pendingKpis} Not yet implemented`} color="warning" variant="outlined" />
            {sharedRoleBuckets.length > 0 && (
              <Chip
                label={`Shared buckets: ${sharedRoleBuckets.join(', ')}`}
                color="default"
                variant="outlined"
              />
            )}
          </Stack>
        )}

        {!loading && !error && appliedRoleBuckets.length > 0 && (
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 3 }}>
            {appliedRoleBuckets.map((bucket) => (
              <Chip
                key={bucket}
                label={`${bucket}: ${sourceCounts[bucket] ?? 0}`}
                color={getSourceColor(bucket)}
                variant={bucket === selectedRole ? 'filled' : 'outlined'}
                size="small"
              />
            ))}
          </Stack>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        )}

        {!loading && !error && filteredData.length > 0 && (
          <TableContainer sx={{ maxHeight: 'calc(100vh - 360px)' }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 90, ...frozenColumnSx(0, true) }}>KPI</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 150, ...frozenColumnSx(90, true) }}>Goal Type</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 280 }}>KPI Name</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 120 }}>Applies Via</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 220 }}>Type</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 240 }}>Aggregation Type</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>Weekly</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>Quarterly</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>Annual</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 110 }}>Prorated</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 210 }}>Implementation</TableCell>
                  <TableCell sx={{ fontWeight: 'bold', minWidth: 280 }}>Details</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredData.map((kpi) => (
                  <TableRow key={`${kpi.index}-${kpi.source_role}`} hover onClick={() => handleViewKpi(kpi)} sx={{ cursor: 'pointer' }}>
                    <TableCell sx={frozenColumnSx(0)}>
                      <Chip label={kpi.index.toUpperCase()} size="small" variant="outlined" />
                    </TableCell>
                    <TableCell sx={frozenColumnSx(90)}>{kpi.goal_type || '-'}</TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {kpi.name}
                      </Typography>
                      {(kpi.tool || kpi.measure) && (
                        <Typography variant="caption" color="text.secondary" display="block">
                          {[kpi.tool, kpi.measure].filter(Boolean).join(' • ')}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={kpi.source_role}
                        size="small"
                        color={getSourceColor(kpi.source_role)}
                        variant={kpi.source_role === selectedRole ? 'filled' : 'outlined'}
                      />
                    </TableCell>
                    <TableCell>{getExpandedTypeLabel(kpi.type_code)}</TableCell>
                    <TableCell>{getExpandedAggregationTypeLabel(kpi.aggregation_type)}</TableCell>
                    <TableCell>{kpi.weekly_target || '-'}</TableCell>
                    <TableCell>{kpi.quarterly_target || '-'}</TableCell>
                    <TableCell>{kpi.annual_target || '-'}</TableCell>
                    <TableCell>
                      <Chip
                        label={kpi.prorate !== false ? 'Yes' : 'No'}
                        size="small"
                        color={kpi.prorate !== false ? 'info' : 'default'}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                        <Chip
                          label={kpi.implementation_status}
                          size="small"
                          color={kpi.implemented ? 'success' : 'warning'}
                        />
                        <Chip label={kpi.implementation_type} size="small" variant="outlined" />
                        {kpi.base_kpi && (
                          <Chip label={`Base ${kpi.base_kpi}`} size="small" variant="outlined" />
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{kpi.implementation_details}</Typography>
                      {kpi.measurement_criteria && (
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                          {kpi.measurement_criteria}
                        </Typography>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {!loading && !error && filteredData.length === 0 && (
          <Box sx={{ textAlign: 'center', py: 8 }}>
            <Typography variant="body1" color="text.secondary">
              No KPIs match the selected filters
            </Typography>
          </Box>
        )}

        <Drawer
          anchor="right"
          open={detailsDrawerOpen}
          onClose={() => setDetailsDrawerOpen(false)}
          sx={{
            '& .MuiDrawer-paper': {
              width: { xs: '100%', sm: 500 },
              p: 3
            }
          }}
        >
          {selectedKpi && (
            <Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                <Typography variant="h5">Role/KPI Details</Typography>
                <IconButton onClick={() => setDetailsDrawerOpen(false)}>
                  <CloseIcon />
                </IconButton>
              </Box>

              <Divider sx={{ mb: 3 }} />

              <Box sx={{ mb: 3 }}>
                <Typography variant="h6" gutterBottom color="primary">
                  Basic Information
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">KPI Index</Typography>
                    <Typography variant="body1">
                      <Chip label={selectedKpi.index} size="small" variant="outlined" />
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Source Role</Typography>
                    <Typography variant="body1">{selectedKpi.source_role || '-'}</Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">KPP Goals</Typography>
                    <Typography variant="body1">{selectedKpi.name || '-'}</Typography>
                  </Grid>
                  {selectedKpi.measurement_criteria && (
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">Measurement Criteria</Typography>
                      <Typography variant="body1">{selectedKpi.measurement_criteria}</Typography>
                    </Grid>
                  )}
                  {selectedKpi.tool && (
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">Tool</Typography>
                      <Typography variant="body1">{selectedKpi.tool}</Typography>
                    </Grid>
                  )}
                  {selectedKpi.measure && (
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">Measure</Typography>
                      <Typography variant="body1">{selectedKpi.measure}</Typography>
                    </Grid>
                  )}
                </Grid>
              </Box>

              <Divider sx={{ mb: 3 }} />

              <Box sx={{ mb: 3 }}>
                <Typography variant="h6" gutterBottom color="primary">
                  KPI Configuration
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Goal Type</Typography>
                    <Typography variant="body1">{selectedKpi.goal_type || '-'}</Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Type</Typography>
                    <Typography variant="body1">{getExpandedTypeLabel(selectedKpi.type_code)}</Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Aggregation Type</Typography>
                    <Typography variant="body1">{getExpandedAggregationTypeLabel(selectedKpi.aggregation_type)}</Typography>
                  </Grid>
                </Grid>
              </Box>

              <Divider sx={{ mb: 3 }} />

              <Box sx={{ mb: 3 }}>
                <Typography variant="h6" gutterBottom color="primary">
                  Targets
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={4}>
                    <Typography variant="caption" color="text.secondary">Weekly Target</Typography>
                    <Typography variant="body1" fontWeight="medium">{selectedKpi.weekly_target || '-'}</Typography>
                  </Grid>
                  <Grid item xs={4}>
                    <Typography variant="caption" color="text.secondary">Quarterly Target</Typography>
                    <Typography variant="body1" fontWeight="medium">{selectedKpi.quarterly_target || '-'}</Typography>
                  </Grid>
                  <Grid item xs={4}>
                    <Typography variant="caption" color="text.secondary">Annual Target</Typography>
                    <Typography variant="body1" fontWeight="medium">{selectedKpi.annual_target || '-'}</Typography>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Target Prorating</Typography>
                    <Typography variant="body1">
                      <Chip
                        label={selectedKpi.prorate !== false ? 'Prorated' : 'Not Prorated'}
                        size="small"
                        color={selectedKpi.prorate !== false ? 'info' : 'default'}
                        variant="outlined"
                      />
                    </Typography>
                  </Grid>
                </Grid>
              </Box>

              <Divider sx={{ mb: 3 }} />

              <Box sx={{ mb: 3 }}>
                <Typography variant="h6" gutterBottom color="primary">
                  Implementation
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                      <Chip
                        label={selectedKpi.implementation_status}
                        size="small"
                        color={selectedKpi.implemented ? 'success' : 'warning'}
                      />
                      <Chip label={selectedKpi.implementation_type} size="small" variant="outlined" />
                      {selectedKpi.base_kpi && (
                        <Chip label={`Base ${selectedKpi.base_kpi}`} size="small" variant="outlined" />
                      )}
                    </Stack>
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Details</Typography>
                    <Typography variant="body1">{selectedKpi.implementation_details || '-'}</Typography>
                  </Grid>
                </Grid>
              </Box>
            </Box>
          )}
        </Drawer>
      </Paper>
    </Container>
  )
}
