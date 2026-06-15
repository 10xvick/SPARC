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
import SyncIcon from '@mui/icons-material/Sync'
import KeyIcon from '@mui/icons-material/Key'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import LockIcon from '@mui/icons-material/Lock'
import { adminUserApi, AdminUser } from '../services/adminUserApi'
import { adminRoleApi } from '../services/adminRoleApi'
import { adminNotificationApi } from '../services/adminNotificationApi'
import { useAuth } from '../context/AuthContext'

interface UserFormState {
  sapid: string
  name: string
  email: string
  role: string
  password: string
  team_ids: string
  is_active: boolean
}

const createDefaultPassword = (): string => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  let result = ''
  for (let i = 0; i < 8; i += 1) {
    result += chars.charAt(Math.floor(Math.random() * chars.length))
  }
  return result
}

const emptyForm = (): UserFormState => ({
  sapid: '',
  name: '',
  email: '',
  role: 'User',
  password: createDefaultPassword(),
  team_ids: '',
  is_active: true
})

export default function UserManagementConfigPage() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [roles, setRoles] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null)
  const [form, setForm] = useState<UserFormState>(emptyForm())
  
  const { user } = useAuth()
  const isReadOnly = user?.role === 'Admin Viewer'
  const readOnlyMessage = 'Read-only access: Admin Viewer users cannot modify user data'

  // Password reset dialog state

  // Password reset dialog state
  const [resetPasswordDialogOpen, setResetPasswordDialogOpen] = useState(false)
  const [resetPasswordData, setResetPasswordData] = useState<{
    mode: 'reset' | 'create'
    userName: string
    password: string
    userEmail: string | null
    userSapid: string
    emailDraft: string
    mailSubject: string
    emailNotificationStatus?: 'sent' | 'skipped' | 'failed'
    emailNotificationMessage?: string | null
  } | null>(null)
  const [sendingEmail, setSendingEmail] = useState(false)
    const buildCredentialEmail = (
      userName: string,
      userSapid: string,
      password: string,
      mode: 'reset' | 'create'
    ): { emailDraft: string; mailSubject: string } => {
      const dashboardUrl = window.location.origin
      const mailSubject = mode === 'create'
        ? 'TeamSight - New Account Credentials'
        : 'TeamSight - Password Reset'
      const introLine = mode === 'create'
        ? 'A TeamSight dashboard account has been created for you by an administrator.'
        : 'Your TeamSight dashboard password has been reset by an administrator.'

      const emailDraft = [
        `Dear ${userName},`,
        '',
        introLine,
        '',
        `Password: ${password}`,
        '',
        'Login Instructions:',
        `1. Go to: ${dashboardUrl}`,
        `2. Enter SAPID: ${userSapid}`,
        '3. Enter the password above',
        '4. After login, change your password via "Change Password" in the user menu',
        '',
        'WARNING: This password will not be resent. Save it securely.',
        '',
        '---',
        'TeamSight Admin',
        'Employee Metrics Dashboard'
      ].join('\r\n')

      return { emailDraft, mailSubject }
    }

  const [copyFeedback, setCopyFeedback] = useState<'password' | 'to' | 'body' | null>(null)
  const visibleUsers = useMemo(() => {
    return [...users].sort((a, b) => a.name.localeCompare(b.name))
  }, [users])

  const loadData = async () => {
    setLoading(true)
    setError(null)
    try {
      const [usersData, rolesData] = await Promise.all([
        adminUserApi.listUsers(),
        adminRoleApi.listRoles()
      ])
      setUsers(usersData)
      setRoles([
        ...rolesData.built_in.map((role) => role.name),
        ...rolesData.custom.map((role) => role.name)
      ])
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to load user management data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const openCreateDialog = () => {
    setEditingUser(null)
    setForm(emptyForm())
    setDialogOpen(true)
  }

  const openEditDialog = (user: AdminUser) => {
    setEditingUser(user)
    setForm({
      sapid: user.sapid,
      name: user.name,
      email: user.email ?? '',
      role: user.role,
      password: createDefaultPassword(),
      team_ids: (user.team_ids ?? []).join(', '),
      is_active: user.is_active
    })
    setDialogOpen(true)
  }

  const closeDialog = () => {
    setDialogOpen(false)
    setEditingUser(null)
    setForm(emptyForm())
  }

  const handleSave = async () => {
    try {
      const teamIds = form.team_ids
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean)

      if (editingUser) {
        await adminUserApi.updateUser(editingUser.id, {
          name: form.name,
          email: form.email || null,
          role: form.role,
          team_ids: teamIds,
          is_active: form.is_active
        })
        setSuccess('User updated successfully')
      } else {
        const createdPassword = form.password
        const createdName = form.name.trim()
        const createdSapid = form.sapid.trim()

        const created = await adminUserApi.createUser({
          sapid: form.sapid,
          name: form.name,
          email: form.email || null,
          role: form.role,
          password: form.password,
          team_ids: teamIds,
          is_active: form.is_active,
          source: 'manual'
        })

        setResetPasswordData({
          mode: 'create',
          userName: createdName,
          password: createdPassword,
          userEmail: created.user.email || null,
          userSapid: createdSapid,
          ...buildCredentialEmail(createdName, createdSapid, createdPassword, 'create'),
          emailNotificationStatus: created.email_notification_status,
          emailNotificationMessage: created.email_notification_message
        })
        setResetPasswordDialogOpen(true)
        setSuccess(`User created successfully for ${createdName}.`)
      }

      closeDialog()
      await loadData()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to save user')
    }
  }

  const handleDelete = async (user: AdminUser) => {
    if (!window.confirm(`Delete user ${user.name} (${user.sapid})?`)) {
      return
    }

    try {
      await adminUserApi.deleteUser(user.id)
      setSuccess('User deleted successfully')
      await loadData()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to delete user')
    }
  }

  const handleResetPassword = async (user: AdminUser) => {
    try {
      const result = await adminUserApi.resetPassword(user.id)
      const newPassword = result.new_password
      const userEmail = result.user_email
      const userName = result.user_name
      const userSapid = result.user_sapid
      
      setResetPasswordData({
        mode: 'reset',
        userName: userName || user.name,
        password: newPassword,
        userEmail: userEmail,
        userSapid: userSapid || user.sapid,
        ...buildCredentialEmail(userName || user.name, userSapid || user.sapid, newPassword, 'reset'),
        emailNotificationStatus: result.email_notification_status,
        emailNotificationMessage: result.email_notification_message
      })
      setResetPasswordDialogOpen(true)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to reset password')
    }
  }

  const copyText = async (text: string, target: 'password' | 'to' | 'body') => {
    const normalizedText = text.replace(/\r?\n/g, '\r\n')

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(normalizedText)
      } else {
        throw new Error('Clipboard API unavailable')
      }
    } catch {
      // Fallback for browsers/clients where Clipboard API is blocked.
      const textArea = document.createElement('textarea')
      textArea.value = normalizedText
      textArea.style.position = 'fixed'
      textArea.style.left = '-9999px'
      textArea.style.top = '-9999px'
      document.body.appendChild(textArea)
      textArea.focus()
      textArea.select()
      document.execCommand('copy')
      document.body.removeChild(textArea)
    }

    setCopyFeedback(target)
    setTimeout(() => setCopyFeedback(null), 2000)
  }

  const handleCopyPassword = () => {
    if (resetPasswordData) {
      void copyText(resetPasswordData.password, 'password')
    }
  }

  const handleCopyToAddress = () => {
    if (resetPasswordData?.userEmail) {
      void copyText(resetPasswordData.userEmail, 'to')
    }
  }

  const handleCopyEmailBody = () => {
    if (resetPasswordData?.emailDraft) {
      void copyText(resetPasswordData.emailDraft, 'body')
    }
  }

  const handleSendEmail = async () => {
    if (!resetPasswordData?.userEmail) {
      setError('User email is not available')
      return
    }

    setSendingEmail(true)
    setError(null)
    try {
      const result = await adminNotificationApi.sendCredentialsEmail({
        user_sapid: resetPasswordData.userSapid,
        password: resetPasswordData.password,
        mode: resetPasswordData.mode,
        dashboard_url: window.location.origin
      })

      setResetPasswordData((prev) => prev ? {
        ...prev,
        emailNotificationStatus: result.status as 'sent' | 'skipped' | 'failed',
        emailNotificationMessage: result.message
      } : prev)
      setSuccess(result.message)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setResetPasswordData((prev) => prev ? {
        ...prev,
        emailNotificationStatus: 'failed',
        emailNotificationMessage: typeof detail === 'string' ? detail : 'Failed to send email'
      } : prev)
      setError(typeof detail === 'string' ? detail : 'Failed to send email')
    } finally {
      setSendingEmail(false)
    }
  }

  const closeResetPasswordDialog = () => {
    setResetPasswordDialogOpen(false)
    setResetPasswordData(null)
    setCopyFeedback(null)
    setSendingEmail(false)
  }

  const handleSync = async () => {
    try {
      const result = await adminUserApi.syncFromResources()
      setSuccess(`Sync complete. Created: ${result.created}, Updated: ${result.updated}`)
      if (result.errors.length > 0) {
        setError(`Sync errors: ${result.errors.slice(0, 3).join('; ')}`)
      }
      await loadData()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to sync users')
    }
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      <Paper sx={{ p: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Box>
            <Typography variant="h4">User Management</Typography>
            <Typography variant="body2" color="text.secondary">
              Manage RBAC users, manual users, password resets, and Resources.csv sync.
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button 
              variant="outlined" 
              startIcon={<SyncIcon />} 
              onClick={handleSync}
              disabled={isReadOnly}
              title={isReadOnly ? readOnlyMessage : ''}
            >
              Sync from Resources.csv
            </Button>
            <Button 
              variant="contained" 
              startIcon={<AddIcon />} 
              onClick={openCreateDialog}
              disabled={isReadOnly}
              title={isReadOnly ? readOnlyMessage : ''}
            >
              Add User
            </Button>
          </Stack>
        </Box>

        {isReadOnly && (
          <Alert severity="info" icon={<LockIcon />} sx={{ mb: 2 }}>
            <strong>Read-Only Access:</strong> You are viewing this page with Admin Viewer role. User management operations are disabled.
          </Alert>
        )}

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>SAPID</TableCell>
              <TableCell>Role</TableCell>
              <TableCell>Teams</TableCell>
              <TableCell>Source</TableCell>
              <TableCell>Status</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {visibleUsers.map((user) => (
              <TableRow key={user.id}>
                <TableCell>{user.name}</TableCell>
                <TableCell>{user.sapid}</TableCell>
                <TableCell>{user.role}</TableCell>
                <TableCell>{(user.team_ids ?? []).join(', ') || '-'}</TableCell>
                <TableCell>
                  <Chip
                    size="small"
                    label={user.source === 'resources_csv' ? 'Resources.csv' : 'Manual'}
                  />
                </TableCell>
                <TableCell>
                  <Chip size="small" color={user.is_active ? 'success' : 'default'} label={user.is_active ? 'Active' : 'Inactive'} />
                </TableCell>
                <TableCell align="right">
                  <Tooltip title={isReadOnly ? readOnlyMessage : 'Reset Password'}>
                    <span>
                      <IconButton 
                        size="small" 
                        onClick={() => handleResetPassword(user)}
                        disabled={isReadOnly}
                      >
                        <KeyIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={isReadOnly ? readOnlyMessage : 'Edit'}>
                    <span>
                      <IconButton 
                        size="small" 
                        onClick={() => openEditDialog(user)}
                        disabled={isReadOnly}
                      >
                        <EditIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title={isReadOnly ? readOnlyMessage : 'Delete'}>
                    <span>
                      <IconButton 
                        size="small" 
                        onClick={() => handleDelete(user)} 
                        disabled={user.sapid === 'admin' || isReadOnly}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {!loading && visibleUsers.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>No users found.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={resetPasswordDialogOpen} onClose={closeResetPasswordDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {resetPasswordData?.mode === 'create' ? 'New User Credentials' : 'Password Reset'}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {resetPasswordData?.mode === 'create'
                ? <>User created for <strong>{resetPasswordData?.userName}</strong></>
                : <>Password reset for <strong>{resetPasswordData?.userName}</strong></>}
            </Typography>

            {resetPasswordData?.emailNotificationStatus === 'sent' && (
              <Alert severity="success" sx={{ mb: 2 }}>
                {resetPasswordData.emailNotificationMessage || `Credential email sent to ${resetPasswordData.userEmail}`}
              </Alert>
            )}

            {resetPasswordData?.emailNotificationStatus === 'skipped' && (
              <Alert severity="info" sx={{ mb: 2 }}>
                {resetPasswordData.emailNotificationMessage || 'Credential email was skipped.'}
              </Alert>
            )}

            {resetPasswordData?.emailNotificationStatus === 'failed' && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                {resetPasswordData.emailNotificationMessage || 'Credential email could not be sent.'}
              </Alert>
            )}

            {resetPasswordData && (
              <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
                <Tooltip title={resetPasswordData.userEmail ? (copyFeedback === 'to' ? 'Copied!' : 'Copy To address') : 'User email is missing'}>
                  <span>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={handleCopyToAddress}
                      startIcon={<ContentCopyIcon />}
                      disabled={!resetPasswordData.userEmail}
                    >
                      {copyFeedback === 'to' ? 'Copied To' : 'Copy To'}
                    </Button>
                  </span>
                </Tooltip>
                <Tooltip title="Email body is sent from server template">
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={handleCopyEmailBody}
                    startIcon={<ContentCopyIcon />}
                  >
                    {copyFeedback === 'body' ? 'Copied Body' : 'Copy Body'}
                  </Button>
                </Tooltip>
              </Stack>
            )}

            {resetPasswordData && (
              <Paper
                sx={{
                  p: 2,
                  backgroundColor: '#fafafa',
                  border: '1px solid #ddd',
                  borderRadius: 1,
                  mb: 2
                }}
              >
                <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
                  <strong>To:</strong> {resetPasswordData.userEmail || 'No email configured for this user'}
                </Typography>
                <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
                  <strong>Subject:</strong> {resetPasswordData.mailSubject}
                </Typography>
                <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 2 }}>
                  <strong>From:</strong> TeamSight Mail Configuration
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: '12px', color: '#333' }}
                >
                  {resetPasswordData.emailDraft}
                </Typography>
              </Paper>
            )}

            {resetPasswordData && !resetPasswordData.userEmail && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                This user has no email address configured. Add email in Edit User to enable Send Email.
              </Alert>
            )}

            {/* Password Display */}
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1, fontWeight: 'bold' }}>
              New Password:
            </Typography>
            <Box
              sx={{
                backgroundColor: '#f5f5f5',
                border: '1px solid #ddd',
                borderRadius: 1,
                p: 2,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 1
              }}
            >
              <Typography
                variant="h6"
                sx={{
                  fontFamily: 'monospace',
                  fontWeight: 600,
                  flex: 1,
                  wordBreak: 'break-all'
                }}
              >
                {resetPasswordData?.password}
              </Typography>
              <Tooltip title={copyFeedback === 'password' ? 'Copied!' : 'Copy password'}>
                <Button
                  variant="outlined"
                  size="small"
                  onClick={handleCopyPassword}
                  startIcon={<ContentCopyIcon />}
                  sx={{ whiteSpace: 'nowrap' }}
                >
                  {copyFeedback === 'password' ? 'Copied' : 'Copy'}
                </Button>
              </Tooltip>
            </Box>
            <Alert severity="warning" sx={{ mt: 2 }}>
              WARNING: This password will not be displayed again. Save it securely or send to user immediately.
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button variant="contained" onClick={closeResetPasswordDialog} autoFocus>
            Close
          </Button>
          <Tooltip title={resetPasswordData?.userEmail ? 'Send credential email' : 'User email is missing'}>
            <span>
              <Button
                variant="outlined"
                color="inherit"
                onClick={handleSendEmail}
                disabled={sendingEmail || !resetPasswordData?.userEmail}
              >
                {sendingEmail ? 'Sending...' : 'Send Email'}
              </Button>
            </span>
          </Tooltip>
        </DialogActions>
      </Dialog>

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{editingUser ? 'Edit User' : 'Add User'}</DialogTitle>
        <DialogContent>
          <TextField
            margin="normal"
            fullWidth
            label="SAPID"
            value={form.sapid}
            disabled={!!editingUser}
            onChange={(event) => setForm((prev) => ({ ...prev, sapid: event.target.value }))}
          />
          <TextField
            margin="normal"
            fullWidth
            label="Name"
            value={form.name}
            onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
          />
          <TextField
            margin="normal"
            fullWidth
            label="Email"
            value={form.email}
            onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
          />
          <TextField
            margin="normal"
            fullWidth
            select
            label="Role"
            value={form.role}
            onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value }))}
          >
            {roles.map((roleName) => (
              <MenuItem key={roleName} value={roleName}>{roleName}</MenuItem>
            ))}
          </TextField>
          {!editingUser && (
            <TextField
              margin="normal"
              fullWidth
              label="Default Password"
              value={form.password}
              onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
              helperText="Use 8-character default password"
            />
          )}
          <TextField
            margin="normal"
            fullWidth
            label="Team IDs (comma separated)"
            value={form.team_ids}
            onChange={(event) => setForm((prev) => ({ ...prev, team_ids: event.target.value }))}
          />
          <TextField
            margin="normal"
            fullWidth
            select
            label="Status"
            value={form.is_active ? 'active' : 'inactive'}
            onChange={(event) => setForm((prev) => ({ ...prev, is_active: event.target.value === 'active' }))}
          >
            <MenuItem value="active">Active</MenuItem>
            <MenuItem value="inactive">Inactive</MenuItem>
          </TextField>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={!form.sapid.trim() || !form.name.trim() || !form.role.trim() || (!editingUser && !form.password.trim())}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  )
}
