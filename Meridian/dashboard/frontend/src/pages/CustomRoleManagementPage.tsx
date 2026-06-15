import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Chip,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/Delete'
import EditIcon from '@mui/icons-material/Edit'
import LockIcon from '@mui/icons-material/Lock'
import { adminRoleApi, AdminRole } from '../services/adminRoleApi'
import { useAuth } from '../context/AuthContext'

interface RoleFormState {
  name: string
  permissions: string[]
}

const emptyForm: RoleFormState = {
  name: '',
  permissions: []
}

export default function CustomRoleManagementPage() {
  const [roles, setRoles] = useState<AdminRole[]>([])
  const [availablePermissions, setAvailablePermissions] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingRole, setEditingRole] = useState<AdminRole | null>(null)
  const [form, setForm] = useState<RoleFormState>(emptyForm)
  
  const { user } = useAuth()
  const isReadOnly = user?.role === 'Admin Viewer'
  const readOnlyMessage = 'Read-only access: Admin Viewer users cannot modify role data'

  const sortedRoles = useMemo(() => {
    return [...roles].sort((a, b) => {
      if (a.is_built_in !== b.is_built_in) {
        return a.is_built_in ? -1 : 1
      }
      return a.name.localeCompare(b.name)
    })
  }, [roles])

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [roleData, permissionData] = await Promise.all([
        adminRoleApi.listRoles(),
        adminRoleApi.listAvailablePermissions()
      ])
      setRoles([...roleData.built_in, ...roleData.custom])
      setAvailablePermissions(permissionData)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to load role management data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const openCreateDialog = () => {
    setEditingRole(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  const openEditDialog = (role: AdminRole) => {
    if (role.is_built_in) return
    setEditingRole(role)
    setForm({
      name: role.name,
      permissions: role.permissions
    })
    setDialogOpen(true)
  }

  const closeDialog = () => {
    setDialogOpen(false)
    setEditingRole(null)
    setForm(emptyForm)
  }

  const handleSave = async () => {
    try {
      if (editingRole) {
        await adminRoleApi.updateRole(editingRole.name, form.permissions)
        setSuccess('Role updated successfully')
      } else {
        await adminRoleApi.createRole(form.name.trim(), form.permissions)
        setSuccess('Role created successfully')
      }
      closeDialog()
      await loadData()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to save role')
    }
  }

  const handleDelete = async (role: AdminRole) => {
    if (role.is_built_in) return
    if (!window.confirm(`Delete custom role ${role.name}?`)) {
      return
    }

    try {
      await adminRoleApi.deleteRole(role.name)
      setSuccess('Role deleted successfully')
      await loadData()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to delete role')
    }
  }

  const handlePermissionsChange = (value: string[]) => {
    setForm((prev) => ({ ...prev, permissions: value }))
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box>
            <Typography variant="h4">Role Management</Typography>
            <Typography variant="body2" color="text.secondary">
              Create and maintain custom RBAC roles and permissions.
            </Typography>
          </Box>
          <Button 
            variant="contained" 
            startIcon={<AddIcon />} 
            onClick={openCreateDialog}
            disabled={isReadOnly}
            title={isReadOnly ? readOnlyMessage : ''}
          >
            Add Custom Role
          </Button>
        </Box>

        {isReadOnly && (
          <Alert severity="info" icon={<LockIcon />} sx={{ mb: 2 }}>
            <strong>Read-Only Access:</strong> You are viewing this page with Admin Viewer role. Role management operations are disabled.
          </Alert>
        )}

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Role</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Permissions</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sortedRoles.map((role) => (
              <TableRow key={role.name}>
                <TableCell>{role.name}</TableCell>
                <TableCell>
                  <Chip size="small" label={role.is_built_in ? 'Built-in' : 'Custom'} color={role.is_built_in ? 'default' : 'primary'} />
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} flexWrap="wrap">
                    {role.permissions.map((permission) => (
                      <Chip key={`${role.name}-${permission}`} size="small" label={permission} sx={{ mb: 0.5 }} />
                    ))}
                  </Stack>
                </TableCell>
                <TableCell align="right">
                  <Tooltip title={role.is_built_in ? 'Built-in roles cannot be edited' : isReadOnly ? readOnlyMessage : 'Edit'}>
                    <span>
                      <IconButton 
                        size="small" 
                        onClick={() => openEditDialog(role)} 
                        disabled={role.is_built_in || isReadOnly}
                      >
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={role.is_built_in ? 'Built-in roles cannot be deleted' : isReadOnly ? readOnlyMessage : 'Delete'}>
                    <span>
                      <IconButton 
                        size="small" 
                        onClick={() => handleDelete(role)} 
                        disabled={role.is_built_in || isReadOnly}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {!loading && sortedRoles.length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>No roles found.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={dialogOpen} onClose={closeDialog} fullWidth maxWidth="md">
        <DialogTitle>{editingRole ? 'Edit Custom Role' : 'Add Custom Role'}</DialogTitle>
        <DialogContent>
          <TextField
            margin="normal"
            fullWidth
            label="Role Name"
            value={form.name}
            disabled={!!editingRole}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />

          <TextField
            select
            SelectProps={{ multiple: true }}
            margin="normal"
            fullWidth
            label="Permissions"
            value={form.permissions}
            onChange={(event) => {
              const value = event.target.value
              handlePermissionsChange(Array.isArray(value) ? value : String(value).split(','))
            }}
            helperText="Select one or more permissions for this role"
          >
            {availablePermissions.map((permission) => (
              <MenuItem key={permission} value={permission}>
                {permission}
              </MenuItem>
            ))}
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={!form.name.trim() || form.permissions.length === 0}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  )
}
