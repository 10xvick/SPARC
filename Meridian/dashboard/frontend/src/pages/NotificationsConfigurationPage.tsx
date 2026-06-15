import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography
} from '@mui/material'
import { adminNotificationApi, MailConfig } from '../services/adminNotificationApi'

type MailConfigForm = MailConfig

const defaultForm: MailConfigForm = {
  enabled: true,
  smtp_host: '10.222.2.80',
  smtp_port: 25,
  use_tls: false,
  from_address: 'user@hcl-software.com.example',
  timeout_seconds: 20
}

interface TabPanelProps {
  children?: React.ReactNode
  index: number
  value: number
}

function TabPanel({ children, value, index, ...other }: TabPanelProps) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`notifications-tabpanel-${index}`}
      aria-labelledby={`notifications-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  )
}

export default function NotificationsConfigurationPage() {
  const [activeTab, setActiveTab] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [form, setForm] = useState<MailConfigForm>(defaultForm)

  const loadMailConfig = async () => {
    setLoading(true)
    setError(null)
    try {
      const config = await adminNotificationApi.getMailConfig()
      setForm(config)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to load mail configuration')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadMailConfig()
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const updated = await adminNotificationApi.updateMailConfig(form)
      setForm(updated)
      setSuccess('Mail configuration saved successfully')
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Failed to save mail configuration')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Box>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Notifications
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Configure mail relay settings used by RBAC user creation and password reset notifications.
        </Typography>
      </Box>

      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => setActiveTab(newValue)}
          aria-label="notifications configuration tabs"
        >
          <Tab label="Mail Configuration" id="notifications-tab-0" aria-controls="notifications-tabpanel-0" />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        <Paper sx={{ p: 3 }}>
          {loading && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Loading mail configuration...
            </Alert>
          )}
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

          <Stack spacing={2}>
            <FormControlLabel
              control={(
                <Switch
                  checked={form.enabled}
                  onChange={(event) => setForm((prev) => ({ ...prev, enabled: event.target.checked }))}
                />
              )}
              label="Enable RBAC credential emails"
            />

            <TextField
              label="SMTP Host"
              value={form.smtp_host}
              onChange={(event) => setForm((prev) => ({ ...prev, smtp_host: event.target.value }))}
              fullWidth
            />

            <TextField
              label="SMTP Port"
              type="number"
              value={form.smtp_port}
              onChange={(event) => setForm((prev) => ({ ...prev, smtp_port: Number(event.target.value) || 0 }))}
              fullWidth
            />

            <FormControlLabel
              control={(
                <Switch
                  checked={form.use_tls}
                  onChange={(event) => setForm((prev) => ({ ...prev, use_tls: event.target.checked }))}
                />
              )}
              label="Use STARTTLS"
            />

            <TextField
              label="From Address"
              value={form.from_address}
              onChange={(event) => setForm((prev) => ({ ...prev, from_address: event.target.value }))}
              helperText="Must be in @hcl-software.com domain"
              fullWidth
            />

            <TextField
              label="SMTP Timeout (seconds)"
              type="number"
              value={form.timeout_seconds}
              onChange={(event) => setForm((prev) => ({ ...prev, timeout_seconds: Number(event.target.value) || 0 }))}
              fullWidth
            />

            <Alert severity="info">
              Recipient addresses are validated to allow only @hcl.com and @hcl-software.com domains.
            </Alert>

            <Box>
              <Button variant="contained" onClick={handleSave} disabled={loading || saving}>
                {saving ? 'Saving...' : 'Save Mail Configuration'}
              </Button>
            </Box>
          </Stack>
        </Paper>
      </TabPanel>
    </Box>
  )
}
