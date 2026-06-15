import { useState, useEffect } from 'react'
import {
  Container,
  Paper,
  Typography,
  Box,
  TextField,
  MenuItem,
  Grid,
  CircularProgress,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Stack,
  Drawer,
  Divider
} from '@mui/material'
import EditIcon from '@mui/icons-material/Edit'
import UploadIcon from '@mui/icons-material/Upload'
import DownloadIcon from '@mui/icons-material/Download'
import VisibilityIcon from '@mui/icons-material/Visibility'
import CloseIcon from '@mui/icons-material/Close'
import LockIcon from '@mui/icons-material/Lock'
import { roleApi } from '../services/roleApi'
import type { Role } from '../types'
import { useAuth } from '../context/AuthContext'

export default function RoleManagementPage() {
  const { user } = useAuth()
  const isReadOnly = user?.role === 'Admin Viewer'
  const readOnlyMessage = 'Read-only access: Admin Viewer users cannot modify KPI targets'
  const [roles, setRoles] = useState<Role[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)

  // Filter states
  const [goalTypeFilter, setGoalTypeFilter] = useState('')
  const [primaryRoleFilter, setPrimaryRoleFilter] = useState('')
  const [searchFilter, setSearchFilter] = useState('')
  const [sortBy, setSortBy] = useState('index')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc')

  // Options for dropdowns
  const [goalTypes, setGoalTypes] = useState<string[]>([])
  const [primaryRoles, setPrimaryRoles] = useState<string[]>([])

  // Edit dialog state
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [editWeekly, setEditWeekly] = useState<number>(0)
  const [editQuarterly, setEditQuarterly] = useState<number>(0)
  const [editAnnual, setEditAnnual] = useState<number>(0)

  // Details drawer state
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false)
  const [selectedRole, setSelectedRole] = useState<Role | null>(null)

  // Import dialog state
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<{ added: number, updated: number, errors: string[] } | null>(null)

  // Load dropdown options on mount
  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [goalTypesData, primaryRolesData] = await Promise.all([
          roleApi.getGoalTypes(),
          roleApi.getPrimaryRoles()
        ])
        setGoalTypes(goalTypesData)
        setPrimaryRoles(primaryRolesData)
      } catch (err) {
        console.error('Failed to load options:', err)
      }
    }
    loadOptions()
  }, [])

  // Load roles
  useEffect(() => {
    const loadRoles = async () => {
      setLoading(true)
      setError(null)
      try {
        const response = await roleApi.getRoles({
          primary_role: primaryRoleFilter || undefined,
          goal_type: goalTypeFilter || undefined,
          search: searchFilter || undefined,
          page: page + 1,
          page_size: rowsPerPage,
          sort_by: sortBy,
          sort_order: sortOrder
        })
        setRoles(response.data)
        setTotal(response.total)
      } catch (err) {
        setError('Failed to load roles. Please try again.')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    loadRoles()
  }, [page, rowsPerPage, goalTypeFilter, primaryRoleFilter, searchFilter, sortBy, sortOrder])

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage)
  }

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10))
    setPage(0)
  }

  const handleEditClick = (role: Role) => {
    setEditingRole(role)
    setEditWeekly(role.weekly_target)
    setEditQuarterly(role.quarterly_target)
    setEditAnnual(role.annual_target)
    setEditDialogOpen(true)
  }

  const handleEditSave = async () => {
    if (!editingRole) return

    try {
      const response = await roleApi.updateTargets(editingRole.index, {
        weekly_target: editWeekly,
        quarterly_target: editQuarterly,
        annual_target: editAnnual
      })
      setSuccess(response.message)
      setEditDialogOpen(false)
      // Reload roles to get updated data
      const rolesResponse = await roleApi.getRoles({
        primary_role: primaryRoleFilter || undefined,
        goal_type: goalTypeFilter || undefined,
        search: searchFilter || undefined,
        page: page + 1,
        page_size: rowsPerPage,
        sort_by: sortBy,
        sort_order: sortOrder
      })
      setRoles(rolesResponse.data)
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError('Failed to update targets. Please try again.')
      console.error(err)
      setTimeout(() => setError(null), 5000)
    }
  }

  const handleExport = async () => {
    try {
      const blob = await roleApi.exportCSV()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `roles_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      setSuccess('Roles exported successfully')
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError('Failed to export roles. Please try again.')
      console.error(err)
      setTimeout(() => setError(null), 5000)
    }
  }

  const handleImport = async () => {
    if (!importFile) return
    
    setImporting(true)
    setError(null)
    setSuccess(null)
    setImportResult(null)
    
    try {
      const result = await roleApi.importCSV(importFile)
      setImportResult(result.details)
      setSuccess(result.message)
      
      // Reload roles after successful import
      const response = await roleApi.getRoles({
        primary_role: primaryRoleFilter || undefined,
        goal_type: goalTypeFilter || undefined,
        search: searchFilter || undefined,
        sort_by: sortBy,
        sort_order: sortOrder,
        page: page + 1,
        page_size: rowsPerPage
      })
      setRoles(response.data)
      setTotal(response.total)
      
      // Keep dialog open to show results
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to import roles. Please check the file format.')
      console.error(err)
    } finally {
      setImporting(false)
    }
  }

  const handleCloseImportDialog = () => {
    setImportDialogOpen(false)
    setImportFile(null)
    setImportResult(null)
  }

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      // Validate file type
      if (!file.name.endsWith('.csv')) {
        setError('Please select a CSV file')
        setTimeout(() => setError(null), 5000)
        return
      }
      setImportFile(file)
      setError(null)
    }
  }

  const handleViewRole = (role: Role) => {
    setSelectedRole(role)
    setDetailsDrawerOpen(true)
  }

  const getGoalTypeColor = (goalType: string) => {
    return goalType === 'Maximize' ? '#4caf50' : '#ff9800'
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box>
            <Typography variant="h4" gutterBottom>
              Role & KPI Management
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Manage role definitions, KPI targets, and performance thresholds
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              size="small"
              onClick={handleExport}
            >
              Export
            </Button>
            <Button
              variant="outlined"
              startIcon={<UploadIcon />}
              size="small"
              onClick={() => setImportDialogOpen(true)}
              disabled={isReadOnly}
              title={isReadOnly ? readOnlyMessage : ''}
            >
              Import
            </Button>
          </Stack>
        </Box>

        {isReadOnly && (
          <Alert severity="info" icon={<LockIcon />} sx={{ mb: 2 }}>
            <strong>Read-Only Access:</strong> You are viewing this page with Admin Viewer role. KPI target editing is disabled.
          </Alert>
        )}

        {/* Filters */}
        <Box sx={{ mb: 3 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <TextField
                fullWidth
                label="Search"
                placeholder="KPI Name or Index"
                value={searchFilter}
                onChange={(e) => {
                  setSearchFilter(e.target.value)
                  setPage(0)
                }}
                size="small"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                select
                label="Goal Type"
                value={goalTypeFilter}
                onChange={(e) => {
                  setGoalTypeFilter(e.target.value)
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="">All Types</MenuItem>
                {goalTypes.map((type) => (
                  <MenuItem key={type} value={type}>{type}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                select
                label="Role"
                value={primaryRoleFilter}
                onChange={(e) => {
                  setPrimaryRoleFilter(e.target.value)
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="">All Roles</MenuItem>
                {primaryRoles.map((role) => (
                  <MenuItem key={role} value={role}>{role}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                select
                label="Sort By"
                value={sortBy}
                onChange={(e) => {
                  setSortBy(e.target.value)
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="index">Index</MenuItem>
                <MenuItem value="name">Name</MenuItem>
                <MenuItem value="primary_role">Role</MenuItem>
                <MenuItem value="goal_type">Goal Type</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                select
                label="Order"
                value={sortOrder}
                onChange={(e) => {
                  setSortOrder(e.target.value as 'asc' | 'desc')
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="asc">Ascending</MenuItem>
                <MenuItem value="desc">Descending</MenuItem>
              </TextField>
            </Grid>
          </Grid>
        </Box>

        {/* Success/Error Messages */}
        {success && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Loading State */}
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* Roles Table */}
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell><strong>KPI</strong></TableCell>
                    <TableCell><strong>Name</strong></TableCell>
                    <TableCell><strong>Role</strong></TableCell>
                    <TableCell><strong>Goal Type</strong></TableCell>
                    <TableCell align="right"><strong>Weekly</strong></TableCell>
                    <TableCell align="right"><strong>Quarterly</strong></TableCell>
                    <TableCell align="right"><strong>Annual</strong></TableCell>
                    <TableCell><strong>Aggregation</strong></TableCell>
                    <TableCell align="center"><strong>Actions</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {roles.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={9} align="center" sx={{ py: 4 }}>
                        <Typography variant="body2" color="text.secondary">
                          No roles/KPIs found matching the filters
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    roles.map((role) => (
                      <TableRow key={role.index} hover>
                        <TableCell>
                          <Chip label={role.index} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell>{role.name}</TableCell>
                        <TableCell>{role.primary_role}</TableCell>
                        <TableCell>
                          <Chip
                            label={role.goal_type}
                            size="small"
                            sx={{
                              bgcolor: getGoalTypeColor(role.goal_type),
                              color: 'white'
                            }}
                          />
                        </TableCell>
                        <TableCell align="right">{role.weekly_target}</TableCell>
                        <TableCell align="right">{role.quarterly_target}</TableCell>
                        <TableCell align="right">{role.annual_target}</TableCell>
                        <TableCell>{role.aggregation_type}</TableCell>
                        <TableCell align="center">
                          <IconButton
                            size="small"
                            onClick={() => handleViewRole(role)}
                            title="View Details"
                          >
                            <VisibilityIcon fontSize="small" />
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => handleEditClick(role)}
                            title={isReadOnly ? readOnlyMessage : 'Edit Targets'}
                            disabled={isReadOnly}
                          >
                            <EditIcon fontSize="small" color={isReadOnly ? 'disabled' : 'inherit'} />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Pagination */}
            <TablePagination
              rowsPerPageOptions={[10, 25, 50, 100]}
              component="div"
              count={total}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={handleChangePage}
              onRowsPerPageChange={handleChangeRowsPerPage}
            />
          </>
        )}
      </Paper>

      {/* Edit Targets Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Edit Targets - {editingRole?.name} ({editingRole?.index})
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Weekly Target"
                  type="number"
                  value={editWeekly}
                  onChange={(e) => setEditWeekly(parseFloat(e.target.value))}
                  inputProps={{ step: 0.01 }}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Quarterly Target"
                  type="number"
                  value={editQuarterly}
                  onChange={(e) => setEditQuarterly(parseFloat(e.target.value))}
                  inputProps={{ step: 0.01 }}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Annual Target"
                  type="number"
                  value={editAnnual}
                  onChange={(e) => setEditAnnual(parseFloat(e.target.value))}
                  inputProps={{ step: 0.01 }}
                />
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleEditSave} variant="contained" color="primary" disabled={isReadOnly} title={isReadOnly ? readOnlyMessage : ''}>
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>

      {/* Role Details Drawer */}
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
        {selectedRole && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography variant="h5">Role/KPI Details</Typography>
              <IconButton onClick={() => setDetailsDrawerOpen(false)}>
                <CloseIcon />
              </IconButton>
            </Box>

            <Divider sx={{ mb: 3 }} />

            {/* Basic Information */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" gutterBottom color="primary">
                Basic Information
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">KPI Index</Typography>
                  <Typography variant="body1">
                    <Chip label={selectedRole.index} size="small" variant="outlined" />
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Status</Typography>
                  <Typography variant="body1">
                    <Chip
                      label={selectedRole.active ? 'Active' : 'Inactive'}
                      color={selectedRole.active ? 'success' : 'default'}
                      size="small"
                    />
                  </Typography>
                </Grid>
                {selectedRole.kpp_goals && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">KPP Goals</Typography>
                    <Typography variant="body1">{selectedRole.kpp_goals}</Typography>
                  </Grid>
                )}
                {selectedRole.measurement_criteria && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Measurement Criteria</Typography>
                    <Typography variant="body1">{selectedRole.measurement_criteria}</Typography>
                  </Grid>
                )}
                {selectedRole.tool && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Tool</Typography>
                    <Typography variant="body1">{selectedRole.tool}</Typography>
                  </Grid>
                )}
                {selectedRole.measure && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Measure</Typography>
                    <Typography variant="body1">{selectedRole.measure}</Typography>
                  </Grid>
                )}
              </Grid>
            </Box>

            <Divider sx={{ mb: 3 }} />

            {/* Role Information */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" gutterBottom color="primary">
                Role Information
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">Role</Typography>
                  <Typography variant="body1">{selectedRole.primary_role}</Typography>
                </Grid>
                {selectedRole.secondary_role && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Secondary Role</Typography>
                    <Typography variant="body1">{selectedRole.secondary_role}</Typography>
                  </Grid>
                )}
                {selectedRole.goal_type && (
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">Goal Type</Typography>
                    <Typography variant="body1">
                      <Chip
                        label={selectedRole.goal_type}
                        size="small"
                        sx={{
                          bgcolor: getGoalTypeColor(selectedRole.goal_type),
                          color: 'white'
                        }}
                      />
                    </Typography>
                  </Grid>
                )}
              </Grid>
            </Box>

            <Divider sx={{ mb: 3 }} />

            {/* Targets */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" gutterBottom color="primary">
                Targets
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Weekly Target</Typography>
                  <Typography variant="body1" fontWeight="medium">{selectedRole.weekly_target}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Quarterly Target</Typography>
                  <Typography variant="body1" fontWeight="medium">{selectedRole.quarterly_target}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Annual Target</Typography>
                  <Typography variant="body1" fontWeight="medium">{selectedRole.annual_target}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Target Prorating</Typography>
                  <Typography variant="body1">
                    <Chip
                      label={selectedRole.prorate !== false ? 'Prorated' : 'Not Prorated'}
                      size="small"
                      color={selectedRole.prorate !== false ? 'info' : 'default'}
                      variant="outlined"
                    />
                  </Typography>
                </Grid>
                {selectedRole.aggregation_type && (
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Aggregation Type</Typography>
                    <Typography variant="body1">{selectedRole.aggregation_type}</Typography>
                  </Grid>
                )}
              </Grid>
            </Box>

            {selectedRole.employee_count !== undefined && (
              <>
                <Divider sx={{ mb: 3 }} />
                <Box sx={{ mb: 3 }}>
                  <Typography variant="h6" gutterBottom color="primary">
                    Assignment
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">Employee Count</Typography>
                      <Typography variant="body1" fontWeight="medium">{selectedRole.employee_count}</Typography>
                    </Grid>
                  </Grid>
                </Box>
              </>
            )}
          </Box>
        )}
      </Drawer>

      {/* Import CSV Dialog */}
      <Dialog open={importDialogOpen} onClose={handleCloseImportDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Import Roles from CSV</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Upload a CSV file to import or update role/KPI records. The file must include these required columns: Index, Role, KPP Goals
            </Typography>
            
            <Button
              variant="outlined"
              component="label"
              fullWidth
              sx={{ mt: 2 }}
              disabled={importing || isReadOnly}
            >
              {importFile ? importFile.name : 'Choose CSV File'}
              <input
                type="file"
                hidden
                accept=".csv"
                onChange={handleFileSelect}
              />
            </Button>

            {importFile && !importing && !importResult && (
              <Box sx={{ mt: 2 }}>
                <Alert severity="info">
                  Ready to import: {importFile.name}
                </Alert>
              </Box>
            )}

            {importing && (
              <Box sx={{ mt: 2, display: 'flex', alignItems: 'center', gap: 2 }}>
                <CircularProgress size={24} />
                <Typography>Importing roles...</Typography>
              </Box>
            )}

            {importResult && (
              <Box sx={{ mt: 2 }}>
                <Alert severity="success" sx={{ mb: 2 }}>
                  Import completed successfully!
                </Alert>
                <Typography variant="body2">
                  <strong>Added:</strong> {importResult.added} roles<br />
                  <strong>Updated:</strong> {importResult.updated} roles<br />
                  <strong>Errors:</strong> {importResult.errors.length}
                </Typography>
                {importResult.errors.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="body2" color="error" gutterBottom>
                      <strong>Error Details:</strong>
                    </Typography>
                    {importResult.errors.map((msg: string, idx: number) => (
                      <Typography key={idx} variant="caption" color="error" display="block">
                        • {msg}
                      </Typography>
                    ))}
                  </Box>
                )}
              </Box>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseImportDialog}>
            {importResult ? 'Close' : 'Cancel'}
          </Button>
          {!importResult && (
            <Button
              variant="contained"
              onClick={handleImport}
              disabled={isReadOnly || !importFile || importing}
              title={isReadOnly ? readOnlyMessage : ''}
            >
              Import
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Container>
  )
}
