import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Autocomplete,
  Checkbox,
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
  Button,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Drawer,
  IconButton,
  Divider,
  FormControlLabel,
  Link
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import UploadIcon from '@mui/icons-material/Upload'
import DownloadIcon from '@mui/icons-material/Download'
import VisibilityIcon from '@mui/icons-material/Visibility'
import EditIcon from '@mui/icons-material/Edit'
import CloseIcon from '@mui/icons-material/Close'
import DeleteIcon from '@mui/icons-material/Delete'
import BlockIcon from '@mui/icons-material/Block'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import { employeeApi } from '../services/employeeApi'
import type { Employee, RoleOption } from '../types'
import { useAuth } from '../context/AuthContext'
import LockIcon from '@mui/icons-material/Lock'

const getFiscalYearStart = () => {
  const today = new Date()
  const year = today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1
  return `${year}-04-01`
}

const createEmptyEmployeeDraft = (): Partial<Employee> => ({
  sapid: '',
  name: '',
  team: '',
  scrum: '',
  primary_role: '',
  secondary_role: '',
  manager: '',
  manager_name: '',
  reporting: 0,
  email: '',
  ref: '',
  resource_sheet_name: '',
  resource_sheet_id: '',
  jira_name: '',
  git_email: '',
  udeid: '',
  tacid: '',
  url: '',
  github_name: '',
  copilot_user: '',
  employment_status: 'Active',
  start_date: getFiscalYearStart(),
  create_rbac_user: false,
})

const createEmployeeDraftFromEmployee = (employee: Employee): Partial<Employee> => ({
  sapid: employee.sapid,
  name: employee.name,
  team: employee.team,
  scrum: employee.scrum,
  primary_role: employee.primary_role,
  secondary_role: employee.secondary_role || '',
  manager: employee.manager || '',
  manager_name: employee.manager_name || '',
  reporting: employee.reporting ?? 0,
  email: employee.email || '',
  ref: employee.ref || '',
  resource_sheet_name: employee.resource_sheet_name || '',
  resource_sheet_id: employee.resource_sheet_id || '',
  jira_name: employee.jira_name || '',
  git_email: employee.git_email || '',
  udeid: employee.udeid || '',
  tacid: employee.tacid || '',
  url: employee.url || '',
  github_name: employee.github_name || '',
  copilot_user: employee.copilot_user || '',
  employment_status: employee.employment_status || 'Active',
  start_date: employee.start_date || getFiscalYearStart(),
})

const isNewOptionValue = (value: string | undefined, options: string[]): boolean => {
  const normalized = (value || '').trim().toLowerCase()
  if (!normalized) return false
  return !options.some((option) => option.trim().toLowerCase() === normalized)
}

export default function EmployeeManagementPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const isReadOnly = user?.role === 'Admin Viewer'
  const readOnlyMessage = 'Read-only access: Admin Viewer users cannot modify employee data'
  const [employees, setEmployees] = useState<Employee[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)

  // Filter states
  const [teamFilter, setTeamFilter] = useState('')
  const [scrumFilter, setScrumFilter] = useState('')
  const [primaryRoleFilter, setPrimaryRoleFilter] = useState('')
  const [secondaryRoleFilter, setSecondaryRoleFilter] = useState('')
  const [searchFilter, setSearchFilter] = useState('')

  // Options for dropdowns
  const [teams, setTeams] = useState<string[]>([])
  const [scrums, setScrums] = useState<string[]>([])
  const [primaryRoles, setPrimaryRoles] = useState<RoleOption[]>([])
  const [secondaryRoles, setSecondaryRoles] = useState<RoleOption[]>([])
  const [managerOptions, setManagerOptions] = useState<RoleOption[]>([])

  // Add employee dialog
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [newEmployee, setNewEmployee] = useState<Partial<Employee>>(createEmptyEmployeeDraft())
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editEmployee, setEditEmployee] = useState<Partial<Employee> | null>(null)

  // Details drawer
  const [detailsDrawerOpen, setDetailsDrawerOpen] = useState(false)
  const [selectedEmployee, setSelectedEmployee] = useState<Employee | null>(null)
  const [editingStartDate, setEditingStartDate] = useState(false)
  const [startDateDraft, setStartDateDraft] = useState('')

  // Import dialog
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<{ added: number, updated: number, errors: string[] } | null>(null)

  const isNewAddTeam = isNewOptionValue(newEmployee.team, teams)
  const isNewAddScrum = isNewOptionValue(newEmployee.scrum, scrums)
  const isNewEditTeam = isNewOptionValue(editEmployee?.team, teams)
  const isNewEditScrum = isNewOptionValue(editEmployee?.scrum, scrums)

  // Load dropdown options on mount
  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [teamsData, scrumsData, rolesData, managersData] = await Promise.all([
          employeeApi.getTeams(),
          employeeApi.getScrums(),
          employeeApi.getRoleOptions(),
          employeeApi.getManagerOptions()
        ])
        setTeams(teamsData)
        setScrums(scrumsData)
        setPrimaryRoles(rolesData.primary_roles)
        setSecondaryRoles(rolesData.secondary_roles)
        setManagerOptions(managersData)
      } catch (err) {
        console.error('Failed to load options:', err)
      }
    }
    loadOptions()
  }, [])

  const reloadEmployees = async () => {
    const response = await employeeApi.getEmployees({
      team: teamFilter || undefined,
      scrum: scrumFilter || undefined,
      primary_role: primaryRoleFilter || undefined,
      secondary_role: secondaryRoleFilter || undefined,
      search: searchFilter || undefined,
      page: page + 1,
      page_size: rowsPerPage,
      include_inactive: true
    })
    setEmployees(response.data)
    setTotal(response.total)
  }

  // Load employees
  useEffect(() => {
    const loadEmployees = async () => {
      setLoading(true)
      setError(null)
      try {
        await reloadEmployees()
      } catch (err) {
        setError('Failed to load employees. Please try again.')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    loadEmployees()
  }, [page, rowsPerPage, teamFilter, scrumFilter, primaryRoleFilter, secondaryRoleFilter, searchFilter])

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage)
  }

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10))
    setPage(0)
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

  const handleEmployeeUpdate = async (sapid: string, updates: Partial<Employee>) => {
    try {
      await employeeApi.updateEmployee(sapid, updates)
      setSuccess('Employee updated successfully')
    } catch (err) {
      setError('Failed to update employee. Please try again.')
      console.error(err)
      return
    }
    try {
      await reloadEmployees()
    } catch (err) {
      console.error('Failed to reload employee list after update:', err)
    }
  }

  const handleEmployeeStatusToggle = async (employee: Employee) => {
    const nextStatus = employee.employment_status === 'Inactive' ? 'Active' : 'Inactive'
    const confirmed = window.confirm(
      `Are you sure you want to mark ${employee.name} (${employee.sapid}) as ${nextStatus}?`
    )
    if (!confirmed) return

    try {
      await employeeApi.updateEmployeeStatus(employee.sapid, nextStatus)
      await reloadEmployees()
      setSuccess(`Employee marked ${nextStatus} successfully`)
    } catch (err) {
      setError(`Failed to mark employee as ${nextStatus}. Please try again.`)
      console.error(err)
    }
  }

  const handleEmployeeDelete = async (employee: Employee) => {
    const confirmed = window.confirm(
      `Delete employee ${employee.name} (${employee.sapid}) permanently? This cannot be undone.`
    )
    if (!confirmed) return

    try {
      await employeeApi.deleteEmployee(employee.sapid)
      await reloadEmployees()
      setSuccess('Employee deleted successfully')
    } catch (err) {
      setError('Failed to delete employee. Please try again.')
      console.error(err)
    }
  }

  const handleAddEmployee = async () => {
    try {
      const response = await employeeApi.addEmployee(newEmployee)
      const password = response.rbac_default_password
      if (response.rbac_user_created && password) {
        const emailSuffix = response.rbac_email_notification_message
          ? ` ${response.rbac_email_notification_message}`
          : ''
        setSuccess(`Employee + RBAC user created. Default password: ${password}.${emailSuffix}`)
      } else {
        setSuccess(response.message || 'Employee added successfully')
      }
      setAddDialogOpen(false)
      setNewEmployee(createEmptyEmployeeDraft())
    } catch (err) {
      setError('Failed to add employee. Please try again.')
      console.error(err)
      return
    }
    // Reload outside the add try/catch so a list-refresh hiccup never
    // shows a false "Failed to add" error when the add itself succeeded.
    try {
      await reloadEmployees()
    } catch (err) {
      console.error('Failed to reload employee list after add:', err)
    }
  }

  const handleOpenEditDialog = (employee: Employee) => {
    setEditEmployee(createEmployeeDraftFromEmployee(employee))
    setEditDialogOpen(true)
  }

  const handleSaveEditedEmployee = async () => {
    if (!editEmployee?.sapid) return

    try {
      await employeeApi.updateEmployee(editEmployee.sapid, editEmployee)
      setEditDialogOpen(false)
      setEditEmployee(null)
      setSuccess('Employee updated successfully')
    } catch (err) {
      setError('Failed to update employee. Please try again.')
      console.error(err)
      return
    }
    // Reload outside the update try/catch to prevent a refresh error
    // from showing a false "Failed to update" message.
    try {
      await reloadEmployees()
      if (selectedEmployee && selectedEmployee.sapid === editEmployee?.sapid) {
        const refreshed = await employeeApi.getEmployee(editEmployee.sapid)
        setSelectedEmployee(refreshed)
      }
    } catch (err) {
      console.error('Failed to reload employee list after update:', err)
    }
  }

  const handleExport = async () => {
    try {
      const blob = await employeeApi.exportCSV()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `employees_${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      setSuccess('Employees exported successfully')
    } catch (err) {
      setError('Failed to export employees. Please try again.')
      console.error(err)
    }
  }
  const handleImport = async () => {
    if (!importFile) return
    
    setImporting(true)
    setError(null)
    setSuccess(null)
    setImportResult(null)
    
    try {
      const result = await employeeApi.importCSV(importFile)
      setImportResult(result.details)
      setSuccess(result.message)
      
      // Reload employees after successful import
      await reloadEmployees()
      
      // Keep dialog open to show results
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to import employees. Please check the file format.')
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
        return
      }
      setImportFile(file)
      setError(null)
    }
  }
  const handleViewEmployee = (employee: Employee) => {
    setSelectedEmployee(employee)
    setDetailsDrawerOpen(true)
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box>
            <Typography variant="h4" gutterBottom>
              Employee Management
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Manage employee information, roles, and team assignments
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
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              size="small"
              onClick={() => setAddDialogOpen(true)}
              disabled={isReadOnly}
              title={isReadOnly ? readOnlyMessage : ''}
            >
              Add Employee
            </Button>
          </Stack>
        </Box>

        {/* Success/Error Messages */}
        {isReadOnly && (
          <Alert severity="info" icon={<LockIcon />} sx={{ mb: 2 }}>
            <strong>Read-Only Access:</strong> You are viewing this page with Admin Viewer role. Employee management operations are disabled.
          </Alert>
        )}
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

        {/* Filters */}
        <Box sx={{ mb: 3 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <TextField
                fullWidth
                label="Search"
                placeholder="Name or SAPID"
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
                label="Team"
                value={teamFilter}
                onChange={(e) => {
                  setTeamFilter(e.target.value)
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="">All Teams</MenuItem>
                {teams.map((team) => (
                  <MenuItem key={team} value={team}>{team}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2}>
              <TextField
                fullWidth
                select
                label="Scrum"
                value={scrumFilter}
                onChange={(e) => {
                  setScrumFilter(e.target.value)
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="">All Scrums</MenuItem>
                {scrums.map((scrum) => (
                  <MenuItem key={scrum} value={scrum}>{scrum}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2.5}>
              <TextField
                fullWidth
                select
                label="Primary Role"
                value={primaryRoleFilter}
                onChange={(e) => {
                  setPrimaryRoleFilter(e.target.value)
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="">All Roles</MenuItem>
                {primaryRoles.map((role) => (
                  <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6} md={2.5}>
              <TextField
                fullWidth
                select
                label="Secondary Role"
                value={secondaryRoleFilter}
                onChange={(e) => {
                  setSecondaryRoleFilter(e.target.value)
                  setPage(0)
                }}
                size="small"
              >
                <MenuItem value="">All Roles</MenuItem>
                {secondaryRoles.map((role) => (
                  <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
                ))}
              </TextField>
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
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* Employees Table */}
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell><strong>SAPID</strong></TableCell>
                    <TableCell><strong>Name</strong></TableCell>
                    <TableCell><strong>Team</strong></TableCell>
                    <TableCell><strong>Scrum</strong></TableCell>
                    <TableCell><strong>Primary Role</strong></TableCell>
                    <TableCell><strong>Secondary Role</strong></TableCell>
                    <TableCell><strong>Manager</strong></TableCell>
                    <TableCell><strong>Status</strong></TableCell>
                    <TableCell align="center"><strong>Actions</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {employees.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={9} align="center" sx={{ py: 4 }}>
                        <Typography variant="body2" color="text.secondary">
                          No employees found matching the filters
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    employees.map((employee) => (
                      <EmployeeRow
                        key={employee.sapid}
                        employee={employee}
                        teams={teams}
                        scrums={scrums}
                        primaryRoles={primaryRoles}
                        secondaryRoles={secondaryRoles}
                        onUpdate={handleEmployeeUpdate}
                        onEdit={handleOpenEditDialog}
                        onView={handleViewEmployee}
                        onToggleStatus={handleEmployeeStatusToggle}
                        onDelete={handleEmployeeDelete}
                        getTeamColor={getTeamColor}
                        isReadOnly={isReadOnly}
                        readOnlyMessage={readOnlyMessage}
                      />
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

      {/* Add Employee Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Employee</DialogTitle>
        <DialogContent>
          {(isNewAddTeam || isNewAddScrum) && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {`New ${isNewAddTeam && isNewAddScrum ? 'Team and Scrum are' : isNewAddTeam ? 'Team is' : 'Scrum is'} being introduced. Metrics and dashboard aggregates for this value will reflect from the next day run.`}
            </Alert>
          )}
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="SAPID *"
                value={newEmployee.sapid}
                onChange={(e) => setNewEmployee({ ...newEmployee, sapid: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Name *"
                value={newEmployee.name}
                onChange={(e) => setNewEmployee({ ...newEmployee, name: e.target.value })}
                required
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Autocomplete
                fullWidth
                freeSolo
                options={teams}
                value={newEmployee.team}
                onInputChange={(_, value) => setNewEmployee({ ...newEmployee, team: value })}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Team *"
                    required
                    helperText="Select an existing team or type a new one"
                  />
                )}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <Autocomplete
                fullWidth
                freeSolo
                options={scrums}
                value={newEmployee.scrum || ''}
                onChange={(_, value) => setNewEmployee({ ...newEmployee, scrum: (value || '').toString() })}
                onInputChange={(_, value) => setNewEmployee({ ...newEmployee, scrum: value })}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Scrum *"
                    required
                    helperText="Select an existing scrum or type a new one"
                  />
                )}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                select
                label="Primary Role *"
                value={newEmployee.primary_role}
                onChange={(e) => setNewEmployee({ ...newEmployee, primary_role: e.target.value })}
                required
              >
                {primaryRoles.map((role) => (
                  <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                select
                label="Secondary Role"
                value={newEmployee.secondary_role}
                onChange={(e) => setNewEmployee({ ...newEmployee, secondary_role: e.target.value })}
              >
                <MenuItem value="">(None)</MenuItem>
                {secondaryRoles.map((role) => (
                  <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12}>
              <Autocomplete
                fullWidth
                freeSolo
                options={managerOptions.map((manager) => manager.label)}
                value={newEmployee.manager || ''}
                onChange={(_, value) => {
                  const nextValue = (value || '').toString()
                  const matched = managerOptions.find((manager) => manager.label === nextValue)
                  setNewEmployee({
                    ...newEmployee,
                    manager: matched ? matched.value : nextValue,
                    manager_name: matched ? matched.label.split(' - ').slice(1).join(' - ') : nextValue,
                  })
                }}
                onInputChange={(_, value) => {
                  if (!value) {
                    setNewEmployee({ ...newEmployee, manager: '', manager_name: '' })
                    return
                  }
                  const matched = managerOptions.find((manager) => manager.label === value)
                  setNewEmployee({
                    ...newEmployee,
                    manager: matched ? matched.value : value,
                    manager_name: matched ? matched.label.split(' - ').slice(1).join(' - ') : value,
                  })
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Manager"
                    helperText="Choose from suggestions or type a manager SAPID/name"
                  />
                )}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Manager Name"
                value={newEmployee.manager_name || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, manager_name: e.target.value })}
                helperText="Optional display name override"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Start Date"
                type="date"
                value={newEmployee.start_date || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, start_date: e.target.value })}
                InputLabelProps={{ shrink: true }}
                helperText="Defaults to fiscal year start (April 1)"
              />
            </Grid>

            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                select
                label="Employment Status"
                value={newEmployee.employment_status || 'Active'}
                onChange={(e) => setNewEmployee({ ...newEmployee, employment_status: e.target.value as 'Active' | 'Inactive' })}
              >
                <MenuItem value="Active">Active</MenuItem>
                <MenuItem value="Inactive">Inactive</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Ref"
                value="(auto-assigned)"
                disabled
                helperText="Unique sequential ID assigned automatically"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                type="number"
                label="Reporting"
                value={newEmployee.reporting ?? 0}
                onChange={(e) => setNewEmployee({ ...newEmployee, reporting: Number(e.target.value || 0) })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Email"
                value={newEmployee.email || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, email: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="ResourceSheetName"
                value={newEmployee.resource_sheet_name || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, resource_sheet_name: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="ResourceSheetID"
                value={newEmployee.resource_sheet_id || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, resource_sheet_id: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="JIRA Name"
                value={newEmployee.jira_name || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, jira_name: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="GIT Email"
                value={newEmployee.git_email || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, git_email: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="UDEID"
                value={newEmployee.udeid || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, udeid: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="TACID"
                value={newEmployee.tacid || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, tacid: e.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="URL"
                value={newEmployee.url || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, url: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="GitHUB Name"
                value={newEmployee.github_name || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, github_name: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="copilot_user"
                value={newEmployee.copilot_user || ''}
                onChange={(e) => setNewEmployee({ ...newEmployee, copilot_user: e.target.value })}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={(
                  <Checkbox
                    checked={Boolean(newEmployee.create_rbac_user)}
                    onChange={(e) => setNewEmployee({ ...newEmployee, create_rbac_user: e.target.checked })}
                  />
                )}
                label="Create RBAC entry with default User role and selected Team"
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleAddEmployee}
            disabled={isReadOnly || !newEmployee.sapid || !newEmployee.name || !newEmployee.team || !newEmployee.scrum || !newEmployee.primary_role}
            title={isReadOnly ? readOnlyMessage : ''}
          >
            Add Employee
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Employee Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Edit Employee</DialogTitle>
        <DialogContent>
          {(isNewEditTeam || isNewEditScrum) && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {`New ${isNewEditTeam && isNewEditScrum ? 'Team and Scrum are' : isNewEditTeam ? 'Team is' : 'Scrum is'} being introduced. Metrics and dashboard aggregates for this value will reflect from the next day run.`}
            </Alert>
          )}
          {editEmployee && (
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="SAPID"
                  value={editEmployee.sapid || ''}
                  disabled
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Name *"
                  value={editEmployee.name || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, name: e.target.value })}
                  required
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <Autocomplete
                  fullWidth
                  freeSolo
                  options={teams}
                  value={editEmployee.team || ''}
                  onInputChange={(_, value) => setEditEmployee({ ...editEmployee, team: value })}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Team *"
                      required
                      helperText="Select an existing team or type a new one"
                    />
                  )}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <Autocomplete
                  fullWidth
                  freeSolo
                  options={scrums}
                  value={editEmployee.scrum || ''}
                  onChange={(_, value) => setEditEmployee({ ...editEmployee, scrum: (value || '').toString() })}
                  onInputChange={(_, value) => setEditEmployee({ ...editEmployee, scrum: value })}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Scrum *"
                      required
                      helperText="Select an existing scrum or type a new one"
                    />
                  )}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  select
                  label="Primary Role *"
                  value={editEmployee.primary_role || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, primary_role: e.target.value })}
                  required
                >
                  {primaryRoles.map((role) => (
                    <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  select
                  label="Secondary Role"
                  value={editEmployee.secondary_role || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, secondary_role: e.target.value })}
                >
                  <MenuItem value="">(None)</MenuItem>
                  {secondaryRoles.map((role) => (
                    <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
                  ))}
                </TextField>
              </Grid>

              <Grid item xs={12}>
                <Autocomplete
                  fullWidth
                  freeSolo
                  options={managerOptions.map((manager) => manager.label)}
                  value={
                    managerOptions.find((m) => m.value === editEmployee.manager)?.label ||
                    editEmployee.manager_name ||
                    editEmployee.manager ||
                    ''
                  }
                  onChange={(_, value) => {
                    const nextValue = (value || '').toString()
                    const matched = managerOptions.find((manager) => manager.label === nextValue)
                    setEditEmployee({
                      ...editEmployee,
                      manager: matched ? matched.value : nextValue,
                      manager_name: matched ? matched.label.split(' - ').slice(1).join(' - ') : nextValue,
                    })
                  }}
                  onInputChange={(_, value) => {
                    if (!value) {
                      setEditEmployee({ ...editEmployee, manager: '', manager_name: '' })
                      return
                    }
                    const matched = managerOptions.find((manager) => manager.label === value)
                    setEditEmployee({
                      ...editEmployee,
                      manager: matched ? matched.value : value,
                      manager_name: matched ? matched.label.split(' - ').slice(1).join(' - ') : value,
                    })
                  }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Manager"
                      helperText="Choose from suggestions or type a manager SAPID/name"
                    />
                  )}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Manager Name"
                  value={editEmployee.manager_name || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, manager_name: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  type="number"
                  label="Reporting"
                  value={editEmployee.reporting ?? 0}
                  onChange={(e) => setEditEmployee({ ...editEmployee, reporting: Number(e.target.value || 0) })}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Start Date"
                  type="date"
                  value={editEmployee.start_date || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, start_date: e.target.value })}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  select
                  label="Employment Status"
                  value={editEmployee.employment_status || 'Active'}
                  onChange={(e) => setEditEmployee({ ...editEmployee, employment_status: e.target.value as 'Active' | 'Inactive' })}
                >
                  <MenuItem value="Active">Active</MenuItem>
                  <MenuItem value="Inactive">Inactive</MenuItem>
                </TextField>
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Ref (internal key)"
                  value={editEmployee.ref || ''}
                  disabled
                  helperText="Internal manager-link key — cannot be changed"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Email"
                  value={editEmployee.email || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, email: e.target.value })}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="ResourceSheetName"
                  value={editEmployee.resource_sheet_name || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, resource_sheet_name: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="ResourceSheetID"
                  value={editEmployee.resource_sheet_id || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, resource_sheet_id: e.target.value })}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="JIRA Name"
                  value={editEmployee.jira_name || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, jira_name: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="GIT Email"
                  value={editEmployee.git_email || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, git_email: e.target.value })}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="UDEID"
                  value={editEmployee.udeid || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, udeid: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="TACID"
                  value={editEmployee.tacid || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, tacid: e.target.value })}
                />
              </Grid>

              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="URL"
                  value={editEmployee.url || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, url: e.target.value })}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="GitHUB Name"
                  value={editEmployee.github_name || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, github_name: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="copilot_user"
                  value={editEmployee.copilot_user || ''}
                  onChange={(e) => setEditEmployee({ ...editEmployee, copilot_user: e.target.value })}
                />
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSaveEditedEmployee}
            disabled={isReadOnly || !editEmployee?.name || !editEmployee?.team || !editEmployee?.scrum || !editEmployee?.primary_role}
            title={isReadOnly ? readOnlyMessage : ''}
          >
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>

      {/* Employee Details Drawer */}
      <Drawer
        anchor="right"
        open={detailsDrawerOpen}
        onClose={() => setDetailsDrawerOpen(false)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 500 } } }}
      >
        {selectedEmployee && (
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
                <Typography variant="body1" fontWeight={600}>{selectedEmployee.sapid}</Typography>
              </Grid>
              
              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Name</Typography>
                <Typography variant="body1" fontWeight={600}>{selectedEmployee.name}</Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Dashboard</Typography>
                <Typography variant="body1">
                  <Link
                    component="button"
                    onClick={() => navigate(`/dashboard/employee?sapid=${encodeURIComponent(selectedEmployee.sapid)}`)}
                  >
                    View Dashboard
                  </Link>
                </Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Start Date</Typography>
                {editingStartDate ? (
                  <Box sx={{ mt: 0.5 }}>
                    <TextField
                      type="date"
                      size="small"
                      value={startDateDraft}
                      onChange={(e) => setStartDateDraft(e.target.value)}
                      InputLabelProps={{ shrink: true }}
                      sx={{ mb: 1 }}
                      fullWidth
                    />
                    <Stack direction="row" spacing={1}>
                      <Button size="small" variant="contained" onClick={async () => {
                        await handleEmployeeUpdate(selectedEmployee.sapid, { start_date: startDateDraft })
                        setSelectedEmployee(prev => prev ? { ...prev, start_date: startDateDraft } : prev)
                        setEditingStartDate(false)
                      }}>Save</Button>
                      <Button size="small" onClick={() => setEditingStartDate(false)}>Cancel</Button>
                    </Stack>
                  </Box>
                ) : (
                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 0.25 }}>
                    <Typography variant="body1">{selectedEmployee.start_date || '-'}</Typography>
                    <Button size="small" onClick={() => {
                      setStartDateDraft(selectedEmployee.start_date || '')
                      setEditingStartDate(true)
                    }}>Edit</Button>
                  </Box>
                )}
              </Grid>

              <Grid item xs={12}>
                <Divider sx={{ my: 2 }} />
                <Typography variant="overline" color="text.secondary">Team & Role</Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Team</Typography>
                <Box sx={{ mt: 0.5 }}>
                  <Chip
                    label={selectedEmployee.team}
                    size="small"
                    sx={{
                      bgcolor: getTeamColor(selectedEmployee.team),
                      color: 'white'
                    }}
                  />
                </Box>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Scrum</Typography>
                <Typography variant="body1">{selectedEmployee.scrum}</Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Primary Role</Typography>
                <Typography variant="body1">{selectedEmployee.primary_role}</Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Secondary Role</Typography>
                <Typography variant="body1">{selectedEmployee.secondary_role || '-'}</Typography>
              </Grid>

              <Grid item xs={12}>
                <Divider sx={{ my: 2 }} />
                <Typography variant="overline" color="text.secondary">Management</Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Manager</Typography>
                <Typography variant="body1">{selectedEmployee.manager_name || '-'}</Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="caption" color="text.secondary">Manager SAPID</Typography>
                <Typography variant="body1">{selectedEmployee.manager || '-'}</Typography>
              </Grid>

              {selectedEmployee.reporting !== undefined && (
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">Reporting</Typography>
                  <Typography variant="body1">{selectedEmployee.reporting}</Typography>
                </Grid>
              )}

              <Grid item xs={12}>
                <Divider sx={{ my: 2 }} />
                <Typography variant="overline" color="text.secondary">Contact & Tools</Typography>
              </Grid>

              {selectedEmployee.email && (
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">Email</Typography>
                  <Typography variant="body1">
                    <Link href={`mailto:${selectedEmployee.email}`}>{selectedEmployee.email}</Link>
                  </Typography>
                </Grid>
              )}

              {selectedEmployee.jira_name && (
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">JIRA Name</Typography>
                  <Typography variant="body1">{selectedEmployee.jira_name}</Typography>
                </Grid>
              )}

              {selectedEmployee.github_name && (
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">GitHub Name</Typography>
                  <Typography variant="body1">{selectedEmployee.github_name}</Typography>
                </Grid>
              )}

              {selectedEmployee.git_email && (
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">Git Email</Typography>
                  <Typography variant="body1">{selectedEmployee.git_email}</Typography>
                </Grid>
              )}

              {selectedEmployee.udeid && (
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">UDE ID</Typography>
                  <Typography variant="body1">{selectedEmployee.udeid}</Typography>
                </Grid>
              )}

              {selectedEmployee.tacid && (
                <Grid item xs={6}>
                  <Typography variant="caption" color="text.secondary">TAC ID</Typography>
                  <Typography variant="body1">{selectedEmployee.tacid}</Typography>
                </Grid>
              )}

            </Grid>
          </Box>
        )}
      </Drawer>

      {/* Import CSV Dialog */}
      <Dialog open={importDialogOpen} onClose={handleCloseImportDialog} maxWidth="sm" fullWidth>
        <DialogTitle>Import Employees from CSV</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Upload a CSV file to import or update employee records. The file must include these required columns: SAPID, Name, Team, Scrum, Primary Role
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
                <Typography>Importing employees...</Typography>
              </Box>
            )}

            {importResult && (
              <Box sx={{ mt: 2 }}>
                <Alert severity="success" sx={{ mb: 2 }}>
                  Import completed successfully!
                </Alert>
                <Typography variant="body2">
                  <strong>Added:</strong> {importResult.added} employees<br />
                  <strong>Updated:</strong> {importResult.updated} employees<br />
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

interface EmployeeRowProps {
  employee: Employee
  teams: string[]
  scrums: string[]
  primaryRoles: RoleOption[]
  secondaryRoles: RoleOption[]
  onUpdate: (sapid: string, updates: Partial<Employee>) => void
  onEdit: (employee: Employee) => void
  onView: (employee: Employee) => void
  onToggleStatus: (employee: Employee) => void
  onDelete: (employee: Employee) => void
  getTeamColor: (team: string) => string
  isReadOnly?: boolean
  readOnlyMessage?: string
}

function EmployeeRow({ employee, teams, scrums, primaryRoles, secondaryRoles, onUpdate, onEdit, onView, onToggleStatus, onDelete, getTeamColor, isReadOnly, readOnlyMessage }: EmployeeRowProps) {
  const [editing, setEditing] = useState<string | null>(null)
  const [editValues, setEditValues] = useState({
    team: employee.team,
    scrum: employee.scrum,
    primary_role: employee.primary_role,
    secondary_role: employee.secondary_role || ''
  })

  const handleEdit = (field: string) => {
    setEditing(field)
  }

  const handleSave = async (field: string) => {
    if (field === 'Team') {
      const isNewTeam = isNewOptionValue(editValues.team, teams)
      if (isNewTeam) {
        const proceed = window.confirm(
          'You are introducing a new Team name. Metrics and dashboard aggregates for this Team will reflect from the next day run. Continue?'
        )
        if (!proceed) {
          handleCancel()
          return
        }
      }
    }

    if (field === 'Scrum') {
      const isNewScrum = isNewOptionValue(editValues.scrum, scrums)
      if (isNewScrum) {
        const proceed = window.confirm(
          'You are introducing a new Scrum name. Metrics and dashboard aggregates for this Scrum will reflect from the next day run. Continue?'
        )
        if (!proceed) {
          handleCancel()
          return
        }
      }
    }

    const updates: any = {}
    if (field === 'Team') updates.Team = editValues.team
    else if (field === 'Scrum') updates.Scrum = editValues.scrum
    else if (field === 'Primary Role') updates['Primary Role'] = editValues.primary_role
    else if (field === 'Secondary Role') updates['Secondary Role'] = editValues.secondary_role
    
    await onUpdate(employee.sapid, updates)
    setEditing(null)
  }

  const handleCancel = () => {
    setEditValues({
      team: employee.team,
      scrum: employee.scrum,
      primary_role: employee.primary_role,
      secondary_role: employee.secondary_role || ''
    })
    setEditing(null)
  }

  return (
    <TableRow hover>
      <TableCell>{employee.sapid}</TableCell>
      <TableCell>{employee.name}</TableCell>
      <TableCell onClick={() => !isReadOnly && handleEdit('Team')} sx={{ cursor: isReadOnly ? 'default' : 'pointer' }}>
        {editing === 'Team' ? (
          <Autocomplete
            freeSolo
            options={teams}
            value={editValues.team}
            onChange={(_, value) => setEditValues({ ...editValues, team: (value || '').toString() })}
            onInputChange={(_, value) => setEditValues({ ...editValues, team: value })}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                autoFocus
                fullWidth
                onBlur={() => handleSave('Team')}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSave('Team')
                  if (e.key === 'Escape') handleCancel()
                }}
              />
            )}
          />
        ) : (
          <Chip
            label={employee.team}
            size="small"
            sx={{
              bgcolor: getTeamColor(employee.team),
              color: 'white',
              cursor: 'pointer'
            }}
          />
        )}
      </TableCell>
      <TableCell onClick={() => !isReadOnly && handleEdit('Scrum')} sx={{ cursor: isReadOnly ? 'default' : 'pointer' }}>
        {editing === 'Scrum' ? (
          <Autocomplete
            freeSolo
            options={scrums}
            value={editValues.scrum}
            onChange={(_, value) => setEditValues({ ...editValues, scrum: (value || '').toString() })}
            onInputChange={(_, value) => setEditValues({ ...editValues, scrum: value })}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                autoFocus
                fullWidth
                onBlur={() => handleSave('Scrum')}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSave('Scrum')
                  if (e.key === 'Escape') handleCancel()
                }}
              />
            )}
          />
        ) : (
          employee.scrum
        )}
      </TableCell>
      <TableCell onClick={() => !isReadOnly && handleEdit('Primary Role')} sx={{ cursor: isReadOnly ? 'default' : 'pointer' }}>
        {editing === 'Primary Role' ? (
          <TextField
            select
            size="small"
            value={editValues.primary_role}
            onChange={(e) => setEditValues({ ...editValues, primary_role: e.target.value })}
            onBlur={() => handleSave('Primary Role')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave('Primary Role')
              if (e.key === 'Escape') handleCancel()
            }}
            autoFocus
            fullWidth
          >
            {primaryRoles.map((role) => (
              <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
            ))}
          </TextField>
        ) : (
          employee.primary_role
        )}
      </TableCell>
      <TableCell onClick={() => !isReadOnly && handleEdit('Secondary Role')} sx={{ cursor: isReadOnly ? 'default' : 'pointer' }}>
        {editing === 'Secondary Role' ? (
          <TextField
            select
            size="small"
            value={editValues.secondary_role}
            onChange={(e) => setEditValues({ ...editValues, secondary_role: e.target.value })}
            onBlur={() => handleSave('Secondary Role')}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave('Secondary Role')
              if (e.key === 'Escape') handleCancel()
            }}
            autoFocus
            fullWidth
          >
            <MenuItem value="">(None)</MenuItem>
            {secondaryRoles.map((role) => (
              <MenuItem key={role.value} value={role.value}>{role.label}</MenuItem>
            ))}
          </TextField>
        ) : (
          employee.secondary_role || '-'
        )}
      </TableCell>
      <TableCell>{employee.manager_name || '-'}</TableCell>
      <TableCell>
        <Chip
          label={employee.employment_status || 'Active'}
          size="small"
          color={employee.employment_status === 'Inactive' ? 'warning' : 'success'}
          variant={employee.employment_status === 'Inactive' ? 'outlined' : 'filled'}
        />
      </TableCell>
      <TableCell align="center">
        <IconButton
          size="small"
          onClick={() => onEdit(employee)}
          title={isReadOnly ? readOnlyMessage : 'Edit All Fields'}
          disabled={isReadOnly}
        >
          <EditIcon fontSize="small" color={isReadOnly ? 'disabled' : 'primary'} />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => onView(employee)}
          title="View Details"
        >
          <VisibilityIcon fontSize="small" />
        </IconButton>
        <IconButton
          size="small"
          onClick={() => onToggleStatus(employee)}
          title={isReadOnly ? readOnlyMessage : (employee.employment_status === 'Inactive' ? 'Mark Active' : 'Mark Inactive')}
          disabled={isReadOnly}
        >
          {employee.employment_status === 'Inactive' ? (
            <CheckCircleIcon fontSize="small" color={isReadOnly ? 'disabled' : 'success'} />
          ) : (
            <BlockIcon fontSize="small" color={isReadOnly ? 'disabled' : 'warning'} />
          )}
        </IconButton>
        <IconButton
          size="small"
          onClick={() => onDelete(employee)}
          title={isReadOnly ? readOnlyMessage : 'Delete Employee'}
          disabled={isReadOnly}
        >
          <DeleteIcon fontSize="small" color={isReadOnly ? 'disabled' : 'error'} />
        </IconButton>
      </TableCell>
    </TableRow>
  )
}
