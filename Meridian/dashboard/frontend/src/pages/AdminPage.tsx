import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Grid,
  Button,
  Chip,
  LinearProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Switch,
  FormControlLabel,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tabs,
  Tab,
  Checkbox,
  Collapse,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Refresh as RefreshIcon,
  Schedule as ScheduleIcon,
  Settings as SettingsIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  ExpandMore as ExpandMoreIcon,
  Stop as StopIcon,
  Memory as MemoryIcon,
  Storage as StorageIcon,
  Speed as CpuIcon,
  Delete as DeleteIcon,
  FolderOpen as FolderIcon,
  PauseCircleOutline as PauseIcon,
  PlayCircleOutline as ResumeIcon,
  Sync as SyncIcon,
  Edit as EditIcon,
  KeyboardArrowDown as ExpandRowIcon,
  KeyboardArrowUp as CollapseRowIcon,
  Lock as LockIcon,
} from '@mui/icons-material';
import axios from 'axios';
import CronBuilder from '../components/CronBuilder';
import ScoringConfigPanel from '../components/ScoringConfigPanel';
import ProjectOnboardingPage from './ProjectOnboardingPage';
import FileViewerTab from './FileViewerTab';
import { useAuth } from '../context/AuthContext';

const API_BASE_URL = '';

interface JobConfig {
  job_id: string;
  job_type: string;
  name: string;
  description: string;
  command: string;
  working_dir: string;
  timeout_minutes: number;
  enabled: boolean;
  schedule: JobSchedule | null;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_duration_seconds: number | null;
  last_run_exit_code: number | null;
  last_triggered_by: string | null;
}

interface JobSchedule {
  enabled: boolean;
  cron_expression: string | null;
  interval_minutes: number | null;
}

interface JobProgress {
  job_id: string;
  status: string;
  progress_percent: number;
  current_step: string;
  message: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  output_lines: string[];
}

interface JobExecution {
  execution_id: string;
  job_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  exit_code: number | null;
  triggered_by: string;
}

interface HealthCheckResult {
  service_name: string;
  status: string;
  message: string;
  response_time_ms: number | null;
  checked_at: string;
}

interface ServiceInfo {
  name: string;
  description: string;
  port: number;
  process_name: string;
  status: string;
  pid: number | null;
  health_url: string;
}

const DAYS_OF_WEEK_LABELS: Record<string, string> = {
  '0': 'Sun',
  '1': 'Mon',
  '2': 'Tue',
  '3': 'Wed',
  '4': 'Thu',
  '5': 'Fri',
  '6': 'Sat',
  '7': 'Sun',
};

const UTC_TIMEZONE_TOKENS = ['UTC', 'ETC/UTC'];
const ISO_TIMESTAMP_HAS_TIMEZONE = /([zZ]|[+\-]\d{2}:?\d{2})$/;

const MONTH_NAMES: Record<string, string> = {
  '01': 'January', '02': 'February', '03': 'March', '04': 'April',
  '05': 'May', '06': 'June', '07': 'July', '08': 'August',
  '09': 'September', '10': 'October', '11': 'November', '12': 'December',
};

interface RunAllStatus {
  running: boolean;
  current_job_id: string | null;
  completed: string[];
  skipped: string[];
  failed: string[];
  pending: string[];
  started_at: string | null;
  finished_at: string | null;
}

interface ProcessMetric {
  name: string;
  port: number | null;
  status: string;
  available: boolean;
  pid?: number | null;
  cpu_percent?: number;
  memory_rss_mb?: number;
  memory_vms_mb?: number;
  memory_percent?: number;
  uptime_seconds?: number;
  threads?: number;
}

interface MemoryCache {
  name: string;
  description: string;
  loaded: boolean;
  rows: number;
  size_mb: number;
  loaded_at: string | null;
}

interface DiskCache {
  name: string;
  description: string;
  exists: boolean;
  file_count: number;
  total_size_mb: number;
  coverage_pct: number | null;
}

interface ResourceUsage {
  process_metrics: ProcessMetric[];
  system_memory: {
    available: boolean;
    total_mb?: number;
    used_mb?: number;
    available_mb?: number;
    percent?: number;
  };
  memory_caches: MemoryCache[];
  disk_caches: DiskCache[];
  active_threads: number;
  psutil_available: boolean;
}

interface DashboardSnapshotGeneratorStatus {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  last_error: string | null;
  last_as_of_date: string | null;
}

interface ActiveDashboardSnapshotStatus {
  active: boolean;
  message?: string;
  snapshot_id?: string;
  as_of_date?: string;
  generated_at?: string;
  team_count?: number;
  scrum_count?: number;
  employee_count?: number;
  periods?: string[];
  source?: string;
}

interface DashboardSnapshotStatusResponse {
  generator: DashboardSnapshotGeneratorStatus;
  active_snapshot: ActiveDashboardSnapshotStatus;
}

interface BackupFolder {
  name: string;
  created_at: string | null;
  backup_type?: 'daily' | 'full' | 'full_catchup';
}

interface JiraFetchStatus {
  configuredProjects: string[];
  projectLastFetchTimestamp: Record<string, string>;
  forceFullFetch: string[];
  projectTokens: Record<string, boolean>;
}

interface DashboardMessage {
  id: string;
  text: string;
  severity: 'critical' | 'high' | 'low' | 'warning' | 'info' | 'compliance';
  scope: 'all' | 'team' | 'scrum' | 'employee';
  target_values: string[];
  require_any_red_kpi: boolean;
  kpi_red_ids: string[];
  empty_resource_fields: string[];
  empty_resource_field_sentinels: string[];
  validity_days: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  is_active: boolean;
}

interface PlaceholderCategory {
  id: string;
  label: string;
  description?: string;
  type?: 'placeholder' | 'resource_field';
  placeholders: string[];
}

interface DashboardMessageOptions {
  teams: string[];
  scrums: string[];
  employees: Array<{ sapid: string; name: string; team: string; scrum: string }>;
  resource_fields?: string[];
  placeholders?: string[];
  placeholder_categories?: PlaceholderCategory[];
}

interface AuditLogStats {
  total_events: number;
  audit_file: string;
}

const AdminPage: React.FC = () => {
  const { user } = useAuth();
  const isReadOnly = user?.role === 'Admin Viewer';
  const readOnlyMessage = 'Read-only access: Admin Viewer users cannot perform admin operations';
  
  const [jobs, setJobs] = useState<JobConfig[]>([]);
  const [jobProgress, setJobProgress] = useState<Record<string, JobProgress>>({});
  const [jobHistory, setJobHistory] = useState<JobExecution[]>([]);
  const [healthStatus, setHealthStatus] = useState<HealthCheckResult[]>([]);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [schedulerTimezone, setSchedulerTimezone] = useState<string>('UTC');
  const [scheduleDialog, setScheduleDialog] = useState<{
    open: boolean;
    jobId: string | null;
    schedule: JobSchedule;
  }>({
    open: false,
    jobId: null,
    schedule: { enabled: false, cron_expression: null, interval_minutes: null },
  });

  const [runAllStatus, setRunAllStatus] = useState<RunAllStatus | null>(null);
  const [runAllLoading, setRunAllLoading] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [bulkScheduleLoading, setBulkScheduleLoading] = useState(false);
  const [jobWarnings, setJobWarnings] = useState<Record<string, string>>({});
  const [resourceUsage, setResourceUsage] = useState<ResourceUsage | null>(null);
  const [resourceUsageError, setResourceUsageError] = useState<string | null>(null);
  const [snapshotStatus, setSnapshotStatus] = useState<DashboardSnapshotStatusResponse | null>(null);
  const [snapshotAsOfDate, setSnapshotAsOfDate] = useState<string>('');
  const [snapshotGenerating, setSnapshotGenerating] = useState(false);
  const [backups, setBackups] = useState<BackupFolder[]>([]);
  const [backupsLoading, setBackupsLoading] = useState(false);
  const [backupsError, setBackupsError] = useState<string | null>(null);
  const [selectedBackups, setSelectedBackups] = useState<string[]>([]);
  const [deletingBackups, setDeletingBackups] = useState(false);
  const [fullBackupLoading, setFullBackupLoading] = useState(false);
  const [cacheRefreshing, setCacheRefreshing] = useState(false);
  const [maintenanceSubTab, setMaintenanceSubTab] = useState(0);
  const [auditLogStats, setAuditLogStats] = useState<AuditLogStats | null>(null);
  const [auditLogLoading, setAuditLogLoading] = useState(false);
  const [auditTrimLoading, setAuditTrimLoading] = useState(false);
  const [auditTrimMode, setAuditTrimMode] = useState<'keep_latest' | 'before_date' | 'before_month' | 'before_year'>('keep_latest');
  const [auditTrimKeepLatest, setAuditTrimKeepLatest] = useState('5000');
  const [auditTrimDate, setAuditTrimDate] = useState('');
  const [auditTrimMonth, setAuditTrimMonth] = useState('');
  const [auditTrimYear, setAuditTrimYear] = useState('');
  const [auditLogError, setAuditLogError] = useState<string | null>(null);
  const [auditLogSuccess, setAuditLogSuccess] = useState<string | null>(null);

  // JIRA Fetch mode control
  const [jiraFetchStatus, setJiraFetchStatus] = useState<JiraFetchStatus | null>(null);
  const [fullFetchDialog, setFullFetchDialog] = useState(false);
  const [fullFetchSelection, setFullFetchSelection] = useState<string[]>([]);
  const [fullFetchSaving, setFullFetchSaving] = useState(false);

  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const [dashboardMessages, setDashboardMessages] = useState<DashboardMessage[]>([]);
  const [messageOptions, setMessageOptions] = useState<DashboardMessageOptions>({ teams: [], scrums: [], employees: [], placeholders: [] });
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messageSaving, setMessageSaving] = useState(false);
  const [copiedPlaceholder, setCopiedPlaceholder] = useState('');
  const [messageDraft, setMessageDraft] = useState({
    id: '',
    text: '',
    severity: 'info' as DashboardMessage['severity'],
    scope: 'all' as DashboardMessage['scope'],
    targetCsv: '',
    requireAnyRedKpi: false,
    kpiRedCsv: '',
    emptyResourceFieldsCsv: '',
    emptyResourceFieldSentinelsCsv: '',
    validity_days: 7,
    enabled: true,
  });

  // Polling interval for progress updates
  const [pollingEnabled, setPollingEnabled] = useState(true);

  // AbortController to cancel in-flight requests when navigating away from this page
  const abortRef = useRef<AbortController>(new AbortController());

  // Tab management
  const [activeTab, setActiveTab] = useState(0);
  const localTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Local Browser Time';
  const isUtcScheduler = UTC_TIMEZONE_TOKENS.includes(schedulerTimezone.toUpperCase());

  // Backup grouping helpers
  const groupedBackups = useMemo(() => {
    const groups: Record<string, Record<string, Record<string, BackupFolder[]>>> = {};
    for (const backup of backups) {
      const m = backup.name.match(/(?:daily|full)_backup(?:_catchup)?_(\d{4})(\d{2})(\d{2})_\d{6}/);
      if (!m) continue;
      const [, year, month, date] = m;
      if (!groups[year]) groups[year] = {};
      if (!groups[year][month]) groups[year][month] = {};
      if (!groups[year][month][date]) groups[year][month][date] = [];
      groups[year][month][date].push(backup);
    }
    return groups;
  }, [backups]);

  const getSelectionState = (names: string[]): 'all' | 'some' | 'none' => {
    const count = names.filter(n => selectedBackups.includes(n)).length;
    return count === 0 ? 'none' : count === names.length ? 'all' : 'some';
  };

  const toggleGroup = (names: string[]) => {
    if (getSelectionState(names) === 'all') {
      setSelectedBackups(prev => prev.filter(n => !names.includes(n)));
    } else {
      setSelectedBackups(prev => [...new Set([...prev, ...names])]);
    }
  };

  useEffect(() => {
    abortRef.current = new AbortController();
    loadInitialData();
    return () => {
      abortRef.current.abort();
    };
  }, []);

  const fetchAllJobProgress = async (jobList: JobConfig[]) => {
    const signal = abortRef.current.signal;
    // Fetch in batches of 4 to avoid exhausting the browser connection pool
    const BATCH_SIZE = 4;
    const allResults: Array<readonly [string, any]> = [];
    for (let i = 0; i < jobList.length; i += BATCH_SIZE) {
      if (signal.aborted) break;
      const batch = jobList.slice(i, i + BATCH_SIZE);
      const batchResults = await Promise.all(
        batch.map(async (job) => {
          try {
            const response = await axios.get(`${API_BASE_URL}/api/admin/jobs/${job.job_id}/progress`, { signal });
            return [job.job_id, response.data] as const;
          } catch {
            return [job.job_id, null] as const;
          }
        })
      );
      allResults.push(...batchResults);
    }
    const updates = allResults;

    setJobProgress((prev) => {
      const next = { ...prev };
      updates.forEach(([jobId, progress]) => {
        if (progress) {
          next[jobId] = progress;
        }
      });
      return next;
    });

    // Clear stale "already running" warnings once polling confirms the job is running
    setJobWarnings((prev) => {
      const stale = updates.filter(([, p]) => p?.status === 'running').map(([id]) => id);
      if (stale.length === 0) return prev;
      const next = { ...prev };
      stale.forEach((id) => { delete next[id]; });
      return next;
    });
  };

  const fetchRunAllStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/jobs/run-all/status`, { signal: abortRef.current.signal });
      setRunAllStatus(response.data);
    } catch {
      // silent — not critical
    }
  };

  const triggerRunAll = async () => {
    setRunAllLoading(true);
    try {
      await axios.post(`${API_BASE_URL}/api/admin/jobs/run-all`);
      await fetchRunAllStatus();
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setRunAllLoading(false);
    }
  };

  const pauseAllJobs = async () => {
    setBulkScheduleLoading(true);
    try {
      await axios.post(`${API_BASE_URL}/api/admin/scheduler/pause-all`);
      await fetchJobs();
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBulkScheduleLoading(false);
    }
  };

  const resumeAllJobs = async () => {
    setBulkScheduleLoading(true);
    try {
      await axios.post(`${API_BASE_URL}/api/admin/scheduler/resume-all`);
      await fetchJobs();
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBulkScheduleLoading(false);
    }
  };

  const toggleJobPause = async (job: JobConfig) => {
    const currentSchedule = job.schedule;
    if (!currentSchedule) return;
    const newEnabled = !currentSchedule.enabled;
    try {
      await axios.put(`${API_BASE_URL}/api/admin/jobs/${job.job_id}/schedule`, {
        enabled: newEnabled,
        cron_expression: currentSchedule.cron_expression,
        interval_minutes: currentSchedule.interval_minutes,
      });
      await fetchJobs();
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const loadInitialData = async () => {
    setLoading(true);
    try {
      // Critical path — only Tab 0 (Service Status) needs data on mount.
      // Jobs are only used in Tab 1, so fetchJobs() is deferred to when the
      // user opens that tab. This avoids blocking 28+ batched progress API calls.
      await fetchServices();
    } catch (err) {
      console.error('Error loading initial data:', err);
    } finally {
      setLoading(false);
    }
    // Fire lightweight tasks in the background.
    // fetchResourceUsage() is NOT called on load — caches are refreshed via
    // run-all-jobs or the on-demand Refresh Cache button.
    checkHealth();
    fetchSchedulerTimezone();
    loadJiraFetchStatus();
    fetchDashboardSnapshotStatus();
  };

  useEffect(() => {
    if (!pollingEnabled || jobs.length === 0) return;

    const interval = setInterval(() => {
      // Only poll progress for the currently expanded job (or any job known to be running).
      // This replaces the previous fetchAllJobProgress(all jobs) which fired 28+ calls per tick.
      const runningIds = Object.entries(jobProgress)
        .filter(([, p]) => p?.status === 'running')
        .map(([id]) => id);
      const toPoll = new Set([...runningIds, ...(expandedJobId ? [expandedJobId] : [])]);
      toPoll.forEach((id) => fetchJobProgress(id));

      // Keep history and run-all status current.
      fetchHistory();
      fetchRunAllStatus();
    }, 10000);

    return () => clearInterval(interval);
  }, [pollingEnabled, jobs, expandedJobId, jobProgress]);

  useEffect(() => {
    // Defensive fallback: if tab state is restored without a Tabs onChange event,
    // ensure required data still loads for the currently active tab.
    if (activeTab === 1 && jobs.length === 0 && !jobsLoading) {
      fetchJobs();
      fetchHistory();
      fetchRunAllStatus();
    }
  }, [activeTab, jobs.length, jobsLoading]);

  const fetchJobs = async () => {
    setJobsLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/jobs`, {
        signal: abortRef.current.signal,
        timeout: 20000,
      });
      setJobs(response.data);

      // Fetch progress snapshot in the background — do NOT await so that the
      // initial page render isn't blocked by 28+ batched progress API calls.
      fetchAllJobProgress(response.data);
    } catch (err: any) {
      if (axios.isCancel(err) || err?.code === 'ERR_CANCELED') return;
      setError(err.message);
    } finally {
      setJobsLoading(false);
    }
  };

  const fetchJobProgress = async (jobId: string) => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/jobs/${jobId}/progress`);
      if (response.data) {
        setJobProgress((prev) => ({ ...prev, [jobId]: response.data }));
      }
    } catch (err) {
      // Silent fail - job may not have progress yet
    }
  };

  const fetchHistory = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/history?limit=50`, { signal: abortRef.current.signal });
      setJobHistory(response.data);
    } catch {
      // silent
    }
  };

  const checkHealth = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/health/services`, { signal: abortRef.current.signal });
      setHealthStatus(response.data);
    } catch {
      // silent
    }
  };

  const fetchServices = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/services`, { signal: abortRef.current.signal });
      setServices(response.data);
    } catch {
      // silent
    }
  };

  const fetchResourceUsage = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/resource-usage`, {
        signal: abortRef.current.signal,
        timeout: 30000,
      });
      setResourceUsage(response.data);
      setResourceUsageError(null);
    } catch (err: any) {
      if (axios.isCancel(err) || err?.code === 'ERR_CANCELED') return;
      const msg = err.response?.data?.detail || err.message || String(err);
      setResourceUsageError(msg);
    }
  };

  const refreshCaches = async () => {
    setCacheRefreshing(true);
    try {
      await axios.post(`${API_BASE_URL}/api/admin/cache/refresh`, {}, { timeout: 60000 });
      // Reload resource-usage to reflect updated cache timestamps
      await fetchResourceUsage();
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || String(err));
    } finally {
      setCacheRefreshing(false);
    }
  };

  const fetchDashboardSnapshotStatus = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/dashboard-snapshots/status`, {
        signal: abortRef.current.signal,
      });
      setSnapshotStatus(response.data);
    } catch {
      // Silent fail to avoid noisy UI on older deployments
    }
  };

  const generateDashboardSnapshot = async () => {
    setSnapshotGenerating(true);
    try {
      await axios.post(`${API_BASE_URL}/api/admin/dashboard-snapshots/generate`, {
        as_of_date: snapshotAsOfDate || null,
        run_in_background: true,
      });
      setError(null);
      await fetchDashboardSnapshotStatus();
      // Poll briefly so users can see completion without manual refresh.
      window.setTimeout(fetchDashboardSnapshotStatus, 3000);
      window.setTimeout(fetchDashboardSnapshotStatus, 10000);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || String(err));
    } finally {
      setSnapshotGenerating(false);
    }
  };

  const triggerFullBackup = async () => {
    setFullBackupLoading(true);
    try {
      await axios.post(`${API_BASE_URL}/api/admin/backup/full-backup`);
      // Refresh job progress for backup job
      setTimeout(() => {
        fetchJobProgress('daily_backup_matrix');
        fetchHistory();
      }, 500);
      setError(null);
      setJobWarnings((prev) => { const next = { ...prev }; delete next['daily_backup_matrix']; return next; });
    } catch (err: any) {
      if (err.response?.status === 409) {
        setJobWarnings((prev) => ({ ...prev, 'daily_backup_matrix': err.response.data?.detail || 'Backup job is already running' }));
      } else {
        setError(err.response?.data?.detail || err.message);
      }
    } finally {
      setFullBackupLoading(false);
    }
  };

  const loadJiraFetchStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/api/admin/jira-fetch/status`, { signal: abortRef.current.signal });
      setJiraFetchStatus(res.data);
    } catch {
      // Silent fail — checkpoint may not exist on first run
    }
  };

  const fetchBackups = async () => {
    setBackupsLoading(true);
    setBackupsError(null);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/backups`);
      setBackups(response.data.backups);
      setSelectedBackups([]);
    } catch (err: any) {
      setBackupsError(err.response?.data?.detail || err.message || String(err));
    } finally {
      setBackupsLoading(false);
    }
  };

  const fetchAuditLogStats = async () => {
    setAuditLogLoading(true);
    setAuditLogError(null);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/audit-logs/stats`);
      setAuditLogStats(response.data);
    } catch (err: any) {
      setAuditLogError(err.response?.data?.detail || err.message || String(err));
    } finally {
      setAuditLogLoading(false);
    }
  };

  const trimAuditLogs = async () => {
    let payload: Record<string, string | number> = { trim_mode: auditTrimMode };
    let confirmMsg = 'Proceed with audit log trim?';

    if (auditTrimMode === 'keep_latest') {
      const keepLatest = Number(auditTrimKeepLatest);
      if (!Number.isFinite(keepLatest) || keepLatest < 0 || !Number.isInteger(keepLatest)) {
        setAuditLogError('Keep latest must be a non-negative integer');
        return;
      }
      payload = { trim_mode: 'keep_latest', keep_latest: keepLatest };

      const currentCount = auditLogStats?.total_events ?? 0;
      const removed = Math.max(0, currentCount - keepLatest);
      confirmMsg =
        removed > 0
          ? `Trim audit log by removing ${removed} event(s) and keeping latest ${keepLatest}?`
          : `No events will be removed. Keep latest ${keepLatest} anyway?`;
    }

    if (auditTrimMode === 'before_date') {
      const value = auditTrimDate.trim();
      if (!value) {
        setAuditLogError('Please select a date');
        return;
      }
      payload = { trim_mode: 'before_date', date: value };
      confirmMsg = `Trim audit log entries older than ${value}?`;
    }

    if (auditTrimMode === 'before_month') {
      const value = auditTrimMonth.trim();
      if (!value) {
        setAuditLogError('Please select a month');
        return;
      }
      payload = { trim_mode: 'before_month', month: value };
      confirmMsg = `Trim audit log entries older than month ${value}?`;
    }

    if (auditTrimMode === 'before_year') {
      const year = Number(auditTrimYear);
      if (!Number.isFinite(year) || !Number.isInteger(year) || year < 1970 || year > 3000) {
        setAuditLogError('Year must be an integer between 1970 and 3000');
        return;
      }
      payload = { trim_mode: 'before_year', year };
      confirmMsg = `Trim audit log entries older than year ${year}?`;
    }

    if (!window.confirm(confirmMsg)) return;

    setAuditTrimLoading(true);
    setAuditLogError(null);
    setAuditLogSuccess(null);
    try {
      const response = await axios.post(`${API_BASE_URL}/api/admin/audit-logs/trim`, payload);
      const data = response.data || {};
      setAuditLogSuccess(`Trim complete. Removed ${data.removed ?? 0} event(s); ${data.after_count ?? 0} remain.`);
      await fetchAuditLogStats();
    } catch (err: any) {
      setAuditLogError(err.response?.data?.detail || err.message || String(err));
    } finally {
      setAuditTrimLoading(false);
    }
  };

  const deleteSelectedBackups = async () => {
    if (selectedBackups.length === 0) return;
    setDeletingBackups(true);
    setBackupsError(null);
    try {
      const response = await axios.delete(`${API_BASE_URL}/api/admin/backups`, {
        data: { names: selectedBackups },
      });
      const { errors } = response.data;
      if (errors && errors.length > 0) {
        setBackupsError(`Errors: ${errors.join('; ')}`);
      }
      await fetchBackups();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
        ? detail.map((d: any) => d?.msg || JSON.stringify(d)).join('; ')
        : err.message || String(err);
      setBackupsError(msg);
    } finally {
      setDeletingBackups(false);
    }
  };

  const fetchSchedulerTimezone = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/scheduler/timezone`, { signal: abortRef.current.signal });
      const timezone = String(response?.data?.timezone || 'UTC');
      setSchedulerTimezone(timezone);
    } catch {
      setSchedulerTimezone('UTC');
    }
  };

  const controlService = async (serviceName: string, action: string) => {
    try {
      await axios.post(`${API_BASE_URL}/api/admin/services/${encodeURIComponent(serviceName)}/control?action=${action}`);
      
      // Refresh services after action
      setTimeout(() => {
        fetchServices();
        checkHealth();
      }, 2000);
      
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const cancelJob = async (jobId: string) => {
    try {
      await axios.post(`${API_BASE_URL}/api/admin/jobs/${jobId}/cancel`);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const openFullFetchDialog = () => {
    if (!jiraFetchStatus) return;
    const forced = jiraFetchStatus.forceFullFetch;
    if (forced.includes('__ALL__')) {
      setFullFetchSelection([...jiraFetchStatus.configuredProjects]);
    } else {
      setFullFetchSelection([...forced]);
    }
    setFullFetchDialog(true);
  };

  const saveFullFetch = async () => {
    setFullFetchSaving(true);
    try {
      const all = jiraFetchStatus?.configuredProjects ?? [];
      const selectionSet = new Set(fullFetchSelection);
      const allSelected = all.length > 0 && all.every((p) => selectionSet.has(p));
      await axios.post(`${API_BASE_URL}/api/admin/jira-fetch/force-full-fetch`, {
        projects: allSelected ? ['__ALL__'] : fullFetchSelection,
      });
      await loadJiraFetchStatus();
      setFullFetchDialog(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setFullFetchSaving(false);
    }
  };

  const parseCsvInput = (raw: string): string[] =>
    raw
      .split(',')
      .map((value) => value.trim())
      .filter((value) => Boolean(value));

  const copyTokenToClipboard = async (
    token: string,
    options?: { wrapInBraces?: boolean; copiedKey?: string }
  ) => {
    const wrappedToken = options?.wrapInBraces === false ? token : `{${token}}`;
    const copiedKey = options?.copiedKey || token;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(wrappedToken);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = wrappedToken;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      setCopiedPlaceholder(copiedKey);
      setTimeout(() => {
        setCopiedPlaceholder((current) => (current === copiedKey ? '' : current));
      }, 1500);
    } catch {
      setError('Unable to copy token to clipboard');
    }
  };

  const resetMessageDraft = () => {
    setCopiedPlaceholder('');
    setMessageDraft({
      id: '',
      text: '',
      severity: 'info',
      scope: 'all',
      targetCsv: '',
      requireAnyRedKpi: false,
      kpiRedCsv: '',
      emptyResourceFieldsCsv: '',
      emptyResourceFieldSentinelsCsv: '',
      validity_days: 7,
      enabled: true,
    });
  };

  const fetchDashboardMessages = async () => {
    setMessagesLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/dashboard-messages`);
      setDashboardMessages(response.data.messages || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setMessagesLoading(false);
    }
  };

  const fetchDashboardMessageOptions = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/admin/dashboard-messages/options`);
      setMessageOptions({
        teams: response.data.teams || [],
        scrums: response.data.scrums || [],
        employees: response.data.employees || [],
        resource_fields: response.data.resource_fields || [],
        placeholders: response.data.placeholders || [],
        placeholder_categories: response.data.placeholder_categories || [],
      });
    } catch {
      setMessageOptions({ teams: [], scrums: [], employees: [], resource_fields: [], placeholders: [], placeholder_categories: [] });
    }
  };

  const saveDashboardMessage = async () => {
    setMessageSaving(true);
    try {
      const payload = {
        text: messageDraft.text,
        severity: messageDraft.severity,
        scope: messageDraft.scope,
        target_values: messageDraft.scope === 'all' ? [] : parseCsvInput(messageDraft.targetCsv),
        require_any_red_kpi: messageDraft.requireAnyRedKpi,
        kpi_red_ids: parseCsvInput(messageDraft.kpiRedCsv),
        empty_resource_fields: parseCsvInput(messageDraft.emptyResourceFieldsCsv),
        empty_resource_field_sentinels: parseCsvInput(messageDraft.emptyResourceFieldSentinelsCsv),
        validity_days: Number(messageDraft.validity_days) || 0,
        enabled: messageDraft.enabled,
      };

      if (messageDraft.id) {
        await axios.put(`${API_BASE_URL}/api/admin/dashboard-messages/${encodeURIComponent(messageDraft.id)}`, payload);
      } else {
        await axios.post(`${API_BASE_URL}/api/admin/dashboard-messages`, payload);
      }

      await fetchDashboardMessages();
      resetMessageDraft();
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setMessageSaving(false);
    }
  };

  const editDashboardMessage = (message: DashboardMessage) => {
    setMessageDraft({
      id: message.id,
      text: message.text,
      severity: message.severity,
      scope: message.scope,
      targetCsv: (message.target_values || []).join(', '),
      requireAnyRedKpi: Boolean(message.require_any_red_kpi),
      kpiRedCsv: (message.kpi_red_ids || []).join(', '),
      emptyResourceFieldsCsv: (message.empty_resource_fields || []).join(', '),
      emptyResourceFieldSentinelsCsv: (message.empty_resource_field_sentinels || []).join(', '),
      validity_days: message.validity_days,
      enabled: message.enabled,
    });
  };

  const deleteDashboardMessage = async (messageId: string) => {
    try {
      await axios.delete(`${API_BASE_URL}/api/admin/dashboard-messages/${encodeURIComponent(messageId)}`);
      await fetchDashboardMessages();
      if (messageDraft.id === messageId) {
        resetMessageDraft();
      }
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const placeholderCategories = useMemo<PlaceholderCategory[]>(() => {
    if (messageOptions.placeholder_categories && messageOptions.placeholder_categories.length > 0) {
      return messageOptions.placeholder_categories;
    }
    return [
      {
        id: 'all_placeholders',
        label: 'All Placeholders',
        type: 'placeholder',
        placeholders: messageOptions.placeholders || [],
      },
    ];
  }, [messageOptions.placeholder_categories, messageOptions.placeholders]);

  const selectedEmptyResourceFields = useMemo(
    () => parseCsvInput(messageDraft.emptyResourceFieldsCsv),
    [messageDraft.emptyResourceFieldsCsv]
  );

  const triggerJob = async (jobId: string) => {
    try {
      await axios.post(`${API_BASE_URL}/api/admin/jobs/${jobId}/trigger`);

      // Optimistic progress so the card immediately reflects running state
      setJobProgress((prev) => ({
        ...prev,
        [jobId]: {
          job_id: jobId,
          status: 'running',
          progress_percent: 0,
          current_step: '',
          message: 'Starting job...',
          started_at: new Date().toISOString(),
          completed_at: null,
          error_message: null,
          output_lines: [],
        },
      }));
      
      // Immediately fetch progress
      setTimeout(() => {
        fetchJobProgress(jobId);
        fetchHistory();
      }, 500);
      
      setError(null);
      setJobWarnings((prev) => { const next = { ...prev }; delete next[jobId]; return next; });
    } catch (err: any) {
      if (err.response?.status === 409) {
        // Job already running — show inline per-job warning, not a global error
        setJobWarnings((prev) => ({ ...prev, [jobId]: err.response.data?.detail || 'Job is already running' }));
      } else {
        setError(err.response?.data?.detail || err.message);
      }
    }
  };

  const shiftDayOfWeekField = (field: string, dayShift: number): string | null => {
    if (field === '*' || field === '?') return field;

    const values = field.split(',').map((value) => value.trim());
    const shiftedValues: string[] = [];

    for (const value of values) {
      const day = Number(value);
      if (!Number.isInteger(day)) return null;
      shiftedValues.push(String((day + dayShift + 7) % 7));
    }

    return shiftedValues.join(',');
  };

  const shiftDayOfMonthField = (field: string, dayShift: number): string | null => {
    if (field === '*' || field === '?') return field;

    const day = Number(field);
    if (!Number.isInteger(day)) return null;

    let shifted = day + dayShift;
    if (shifted < 1) shifted = 31;
    if (shifted > 31) shifted = 1;
    return String(shifted);
  };

  const getLocalToUtcDayShift = (localDate: Date): number => {
    const localDayStart = new Date(localDate.getFullYear(), localDate.getMonth(), localDate.getDate()).getTime();
    const utcDayStart = Date.UTC(localDate.getUTCFullYear(), localDate.getUTCMonth(), localDate.getUTCDate());
    return Math.round((utcDayStart - localDayStart) / 86400000);
  };

  const getUtcToLocalDayShift = (utcDate: Date): number => {
    const utcDayStart = Date.UTC(utcDate.getUTCFullYear(), utcDate.getUTCMonth(), utcDate.getUTCDate());
    const localDayStart = new Date(utcDate.getFullYear(), utcDate.getMonth(), utcDate.getDate()).getTime();
    return Math.round((localDayStart - utcDayStart) / 86400000);
  };

  const convertSchedulerCronToLocal = (cronExpression: string): string => {
    const expression = (cronExpression || '').trim();
    if (!isUtcScheduler || !expression) return expression;

    const parts = expression.split(/\s+/);
    if (parts.length !== 5) return expression;

    const [minuteField, hourField, dayOfMonthField, monthField, dayOfWeekField] = parts;
    const minute = Number(minuteField);
    const hour = Number(hourField);

    if (!Number.isInteger(minute) || !Number.isInteger(hour)) return expression;

    const utcDate = new Date();
    utcDate.setUTCHours(hour, minute, 0, 0);

    const dayShift = getUtcToLocalDayShift(utcDate);
    let convertedDayOfMonth = dayOfMonthField;
    let convertedDayOfWeek = dayOfWeekField;

    if (dayShift !== 0) {
      const shiftedDayOfMonth = shiftDayOfMonthField(dayOfMonthField, dayShift);
      const shiftedDayOfWeek = shiftDayOfWeekField(dayOfWeekField, dayShift);
      if (!shiftedDayOfMonth || !shiftedDayOfWeek) return expression;
      convertedDayOfMonth = shiftedDayOfMonth;
      convertedDayOfWeek = shiftedDayOfWeek;
    }

    return `${utcDate.getMinutes()} ${utcDate.getHours()} ${convertedDayOfMonth} ${monthField} ${convertedDayOfWeek}`;
  };

  const convertLocalCronToScheduler = (cronExpression: string): string => {
    const expression = (cronExpression || '').trim();
    if (!isUtcScheduler || !expression) return expression;

    const parts = expression.split(/\s+/);
    if (parts.length !== 5) return expression;

    const [minuteField, hourField, dayOfMonthField, monthField, dayOfWeekField] = parts;
    const minute = Number(minuteField);
    const hour = Number(hourField);

    if (!Number.isInteger(minute) || !Number.isInteger(hour)) return expression;

    const localDate = new Date();
    localDate.setHours(hour, minute, 0, 0);

    const dayShift = getLocalToUtcDayShift(localDate);
    let convertedDayOfMonth = dayOfMonthField;
    let convertedDayOfWeek = dayOfWeekField;

    if (dayShift !== 0) {
      const shiftedDayOfMonth = shiftDayOfMonthField(dayOfMonthField, dayShift);
      const shiftedDayOfWeek = shiftDayOfWeekField(dayOfWeekField, dayShift);
      if (!shiftedDayOfMonth || !shiftedDayOfWeek) return expression;
      convertedDayOfMonth = shiftedDayOfMonth;
      convertedDayOfWeek = shiftedDayOfWeek;
    }

    return `${localDate.getUTCMinutes()} ${localDate.getUTCHours()} ${convertedDayOfMonth} ${monthField} ${convertedDayOfWeek}`;
  };

  const openScheduleDialog = (job: JobConfig) => {
    const currentSchedule = job.schedule || { enabled: false, cron_expression: null, interval_minutes: null };
    const localCronExpression = currentSchedule.cron_expression
      ? convertSchedulerCronToLocal(currentSchedule.cron_expression)
      : null;

    setScheduleDialog({
      open: true,
      jobId: job.job_id,
      schedule: {
        ...currentSchedule,
        cron_expression: localCronExpression,
      },
    });
  };

  const closeScheduleDialog = () => {
    setScheduleDialog({ open: false, jobId: null, schedule: { enabled: false, cron_expression: null, interval_minutes: null } });
  };

  const saveSchedule = async () => {
    if (!scheduleDialog.jobId) return;

    const schedulePayload: JobSchedule = {
      ...scheduleDialog.schedule,
      cron_expression: scheduleDialog.schedule.cron_expression
        ? convertLocalCronToScheduler(scheduleDialog.schedule.cron_expression)
        : null,
    };

    try {
      await axios.put(
        `${API_BASE_URL}/api/admin/jobs/${scheduleDialog.jobId}/schedule`,
        schedulePayload
      );
      closeScheduleDialog();
      fetchJobs();
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
      case 'healthy':
        return 'success';
      case 'running':
        return 'info';
      case 'failed':
      case 'unhealthy':
        return 'error';
      case 'pending':
        return 'warning';
      default:
        return 'default';
    }
  };

  const getScheduleLabel = (job: JobConfig) => {
    if (!job.schedule?.enabled) return 'Not Scheduled';
    if (job.schedule.cron_expression) {
      const localCronExpression = convertSchedulerCronToLocal(job.schedule.cron_expression);
      return formatCronExpressionAsLocal(localCronExpression);
    }
    if (job.schedule.interval_minutes) return `Every ${job.schedule.interval_minutes}m`;
    return 'Scheduled';
  };

  const formatTimeLocal = (hour: number, minute: number) => {
    const date = new Date();
    date.setHours(hour, minute, 0, 0);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatCronExpressionAsLocal = (cronExpression: string) => {
    const expression = (cronExpression || '').trim();
    const parts = expression.split(/\s+/);

    if (parts.length !== 5) {
      return `Cron: ${expression}`;
    }

    const [minuteField, hourField, dayOfMonthField, monthField, dayOfWeekField] = parts;
    const minute = Number(minuteField);
    const hour = Number(hourField);

    if (
      Number.isFinite(minute) &&
      Number.isFinite(hour) &&
      minute >= 0 && minute <= 59 &&
      hour >= 0 && hour <= 23
    ) {
      const localTime = formatTimeLocal(hour, minute);

      if (dayOfWeekField !== '*' && dayOfMonthField === '*' && monthField === '*') {
        const dayLabels = dayOfWeekField
          .split(',')
          .map((dayValue) => DAYS_OF_WEEK_LABELS[dayValue.trim()] || dayValue.trim())
          .join(', ');
        return `Weekly: ${dayLabels} at ${localTime} (${localTimeZone})`;
      }

      if (dayOfMonthField !== '*' && monthField === '*' && dayOfWeekField === '*') {
        return `Monthly: day ${dayOfMonthField} at ${localTime} (${localTimeZone})`;
      }

      if (dayOfMonthField === '*' && monthField === '*' && dayOfWeekField === '*') {
        return `Daily: ${localTime} (${localTimeZone})`;
      }
    }

    if (minuteField.startsWith('*/') && hourField === '*' && dayOfMonthField === '*' && monthField === '*' && dayOfWeekField === '*') {
      return `Every ${minuteField.substring(2)} minutes`;
    }

    if (hourField.startsWith('*/') && dayOfMonthField === '*' && monthField === '*' && dayOfWeekField === '*') {
      return `Every ${hourField.substring(2)} hours at minute ${minuteField}`;
    }

    return `Cron: ${expression}`;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
      case 'healthy':
        return <CheckCircleIcon />;
      case 'running':
        return <CircularProgress size={20} />;
      case 'failed':
      case 'unhealthy':
        return <ErrorIcon />;
      case 'pending':
        return <WarningIcon />;
      default:
        return null;
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (seconds === null) return 'N/A';
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}m ${secs}s`;
  };

  const normalizeTimestampForDisplay = (timestamp: string): string => {
    const rawTimestamp = (timestamp || '').trim();
    if (!rawTimestamp) {
      return rawTimestamp;
    }

    if (ISO_TIMESTAMP_HAS_TIMEZONE.test(rawTimestamp)) {
      return rawTimestamp;
    }

    if (isUtcScheduler) {
      return `${rawTimestamp}Z`;
    }

    return rawTimestamp;
  };

  const formatTimestamp = (timestamp: string | null) => {
    if (!timestamp) return 'N/A';

    const normalizedTimestamp = normalizeTimestampForDisplay(timestamp);
    const parsedTimestamp = new Date(normalizedTimestamp);

    if (Number.isNaN(parsedTimestamp.getTime())) {
      return timestamp;
    }

    return parsedTimestamp.toLocaleString();
  };

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" gutterBottom>
            System Administration
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Manage services, scheduled jobs, configurations, and project setup
          </Typography>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {isReadOnly && (
        <Alert severity="info" icon={<LockIcon />} sx={{ mb: 3 }}>
          <strong>Read-Only Access:</strong> You are viewing this page with Admin Viewer role. Administration operations are disabled.
        </Alert>
      )}

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs
          value={activeTab}
          onChange={(_, newValue) => {
            setActiveTab(newValue);
            if (newValue === 0) {
              fetchServices();
              checkHealth();
              fetchDashboardSnapshotStatus();
            }
            if (newValue === 1) {
              // Jobs and history are only needed on this tab — load lazily.
              fetchJobs();
              fetchHistory();
              fetchRunAllStatus();
            }
            if (newValue === 4) {
              setMaintenanceSubTab(0);
              fetchBackups();
              fetchAuditLogStats();
            }
            if (newValue === 6) {
              fetchDashboardMessages();
              fetchDashboardMessageOptions();
            }
          }}
          aria-label="admin tabs"
        >
          <Tab label="Service Status" />
          <Tab label="Job Scheduling & Recent Executions" />
          <Tab label="Scoring & Thresholds" />
          <Tab label="Project Onboarding" />
          <Tab label="Maintenance" />
          <Tab label="File Viewer" />
          <Tab label="Dashboard Messages" />
        </Tabs>
      </Box>

      {/* TAB 0: Service Status */}
      {activeTab === 0 && (
        <>
        <Card>
          <CardContent>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">Services</Typography>
              <Box display="flex" gap={1}>
                <Button startIcon={<RefreshIcon />} onClick={() => { fetchServices(); checkHealth(); }} size="small">
                  Refresh
                </Button>
              </Box>
            </Box>
            <Grid container spacing={2}>
              {services.map((service) => {
                const health = healthStatus.find(h => h.service_name === service.name);
                const isHealthy = health?.status === 'healthy';
                
                return (
                  <Grid item xs={12} sm={6} key={service.name}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2}>
                          <Box flex={1}>
                            <Box display="flex" alignItems="center" gap={1} mb={1}>
                              {service.status === 'running' && isHealthy ? (
                                <CheckCircleIcon color="success" />
                              ) : service.status === 'running' ? (
                                <WarningIcon color="warning" />
                              ) : (
                                <ErrorIcon color="disabled" />
                              )}
                              <Typography variant="h6">{service.name}</Typography>
                            </Box>
                            <Typography variant="body2" color="text.secondary" gutterBottom>
                              {service.description}
                            </Typography>
                            <Box display="flex" gap={1} flexWrap="wrap" mt={1}>
                              <Chip
                                label={service.status.toUpperCase()}
                                color={service.status === 'running' ? (isHealthy ? 'success' : 'warning') : 'default'}
                                size="small"
                              />
                              <Chip label={`Port: ${service.port}`} size="small" variant="outlined" />
                              {service.pid && (
                                <Chip label={`PID: ${service.pid}`} size="small" variant="outlined" />
                              )}
                              {health?.response_time_ms !== null && service.status === 'running' && (
                                <Chip 
                                  label={`${health?.response_time_ms?.toFixed(0)}ms`} 
                                  size="small" 
                                  variant="outlined"
                                  color={(health?.response_time_ms ?? 1000) < 100 ? 'success' : 'default'}
                                />
                              )}
                            </Box>
                          </Box>
                        </Box>
                        <Box display="flex" gap={1} justifyContent="flex-end">
                          <Tooltip title={isReadOnly ? readOnlyMessage : "Start Service"}>
                            <span>
                              <Button
                                size="small"
                                variant="outlined"
                                color="success"
                                startIcon={<PlayIcon />}
                                onClick={() => controlService(service.name, 'start')}
                                disabled={service.status === 'running' || isReadOnly}
                              >
                                Start
                              </Button>
                            </span>
                          </Tooltip>
                          <Tooltip title={isReadOnly ? readOnlyMessage : "Stop Service"}>
                            <span>
                              <Button
                                size="small"
                                variant="outlined"
                                color="error"
                                startIcon={<StopIcon />}
                                onClick={() => controlService(service.name, 'stop')}
                                disabled={service.status !== 'running' || isReadOnly}
                              >
                                Stop
                              </Button>
                            </span>
                          </Tooltip>
                          <Tooltip title={isReadOnly ? readOnlyMessage : "Restart Service"}>
                            <span>
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<RefreshIcon />}
                                onClick={() => controlService(service.name, 'restart')}
                                disabled={isReadOnly}
                              >
                                Restart
                              </Button>
                            </span>
                          </Tooltip>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                );
              })}
            </Grid>
          </CardContent>
        </Card>

        {/* Resource Usage Section */}
        <Box mt={3}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6">Resource Usage & Cache Status</Typography>
            <Box display="flex" gap={1} alignItems="center">
              {!resourceUsage && !cacheRefreshing && (
                <Typography variant="caption" color="text.secondary">Click Refresh Cache to load</Typography>
              )}
              <Button
                startIcon={cacheRefreshing ? <CircularProgress size={16} /> : <SyncIcon />}
                onClick={refreshCaches}
                size="small"
                variant="outlined"
                disabled={cacheRefreshing || isReadOnly}
                title={isReadOnly ? readOnlyMessage : ''}
              >
                {cacheRefreshing ? 'Refreshing…' : 'Refresh Cache'}
              </Button>
            </Box>
          </Box>
          {resourceUsage ? (
            <>
            {/* Process Metrics */}
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CpuIcon fontSize="small" /> Process Metrics
            </Typography>
            <Grid container spacing={2} mb={3}>
              {resourceUsage.process_metrics.map((proc) => (
                <Grid item xs={12} sm={6} key={proc.name}>
                  <Card variant="outlined">
                    <CardContent>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                        <Typography variant="subtitle1" fontWeight="bold">{proc.name}</Typography>
                        <Chip
                          label={proc.status.toUpperCase()}
                          size="small"
                          color={proc.status === 'running' ? 'success' : 'default'}
                        />
                      </Box>
                      {proc.available ? (
                        <>
                          <Box display="flex" gap={1} flexWrap="wrap" mb={1}>
                            {proc.pid && <Chip label={`PID: ${proc.pid}`} size="small" variant="outlined" />}
                            {proc.port && <Chip label={`Port: ${proc.port}`} size="small" variant="outlined" />}
                            {proc.threads !== undefined && <Chip label={`Threads: ${proc.threads}`} size="small" variant="outlined" />}
                            {proc.uptime_seconds !== undefined && (
                              <Chip
                                label={`Up: ${proc.uptime_seconds >= 3600
                                  ? `${Math.floor(proc.uptime_seconds / 3600)}h ${Math.floor((proc.uptime_seconds % 3600) / 60)}m`
                                  : `${Math.floor(proc.uptime_seconds / 60)}m`}`}
                                size="small"
                                variant="outlined"
                              />
                            )}
                          </Box>
                          <Box mb={0.5}>
                            <Box display="flex" justifyContent="space-between">
                              <Typography variant="caption" color="text.secondary">CPU</Typography>
                              <Typography variant="caption">{proc.cpu_percent?.toFixed(1)}%</Typography>
                            </Box>
                            <LinearProgress
                              variant="determinate"
                              value={Math.min(proc.cpu_percent ?? 0, 100)}
                              color={(proc.cpu_percent ?? 0) > 80 ? 'error' : (proc.cpu_percent ?? 0) > 50 ? 'warning' : 'primary'}
                              sx={{ height: 6, borderRadius: 1 }}
                            />
                          </Box>
                          <Box>
                            <Box display="flex" justifyContent="space-between">
                              <Typography variant="caption" color="text.secondary">Memory (RSS)</Typography>
                              <Typography variant="caption">{proc.memory_rss_mb?.toFixed(1)} MB ({proc.memory_percent?.toFixed(1)}%)</Typography>
                            </Box>
                            <LinearProgress
                              variant="determinate"
                              value={Math.min(proc.memory_percent ?? 0, 100)}
                              color={(proc.memory_percent ?? 0) > 80 ? 'error' : (proc.memory_percent ?? 0) > 50 ? 'warning' : 'success'}
                              sx={{ height: 6, borderRadius: 1 }}
                            />
                          </Box>
                        </>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          {proc.status === 'running' ? 'Metrics unavailable (psutil not installed)' : 'Service not running'}
                        </Typography>
                      )}
                    </CardContent>
                  </Card>
                </Grid>
              ))}

              {/* System memory summary */}
              {resourceUsage.system_memory.available && (
                <Grid item xs={12} sm={6}>
                  <Card variant="outlined">
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight="bold" mb={1}>System Memory</Typography>
                      <Box display="flex" gap={1} flexWrap="wrap" mb={1}>
                        <Chip label={`Total: ${resourceUsage.system_memory.total_mb?.toFixed(0)} MB`} size="small" variant="outlined" />
                        <Chip label={`Used: ${resourceUsage.system_memory.used_mb?.toFixed(0)} MB`} size="small" variant="outlined" />
                        <Chip label={`Free: ${resourceUsage.system_memory.available_mb?.toFixed(0)} MB`} size="small" variant="outlined" color="success" />
                        <Chip label={`Active threads: ${resourceUsage.active_threads}`} size="small" variant="outlined" />
                      </Box>
                      <Box display="flex" justifyContent="space-between">
                        <Typography variant="caption" color="text.secondary">System Memory Used</Typography>
                        <Typography variant="caption">{resourceUsage.system_memory.percent?.toFixed(1)}%</Typography>
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={resourceUsage.system_memory.percent ?? 0}
                        color={(resourceUsage.system_memory.percent ?? 0) > 90 ? 'error' : (resourceUsage.system_memory.percent ?? 0) > 75 ? 'warning' : 'primary'}
                        sx={{ height: 6, borderRadius: 1 }}
                      />
                    </CardContent>
                  </Card>
                </Grid>
              )}
            </Grid>

            {/* In-Memory Caches */}
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <MemoryIcon fontSize="small" /> In-Memory Caches
            </Typography>
            <Card variant="outlined" sx={{ mb: 3 }}>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Cache</TableCell>
                      <TableCell>Description</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Rows</TableCell>
                      <TableCell align="right">Size (MB)</TableCell>
                      <TableCell>Last Loaded</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {resourceUsage.memory_caches.map((cache) => (
                      <TableRow key={cache.name}>
                        <TableCell><Typography variant="body2" fontWeight="bold">{cache.name}</Typography></TableCell>
                        <TableCell><Typography variant="caption" color="text.secondary">{cache.description}</Typography></TableCell>
                        <TableCell>
                          <Chip
                            label={cache.loaded ? 'Loaded' : 'Not Loaded'}
                            size="small"
                            color={cache.loaded ? 'success' : 'warning'}
                          />
                        </TableCell>
                        <TableCell align="right">{cache.loaded ? cache.rows.toLocaleString() : '—'}</TableCell>
                        <TableCell align="right">{cache.loaded ? cache.size_mb.toFixed(2) : '—'}</TableCell>
                        <TableCell>
                          <Typography variant="caption">
                            {cache.loaded_at ? new Date(cache.loaded_at).toLocaleString() : '—'}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Card>

            {/* On-Disk Caches */}
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <StorageIcon fontSize="small" /> On-Disk Caches
            </Typography>
            <Card variant="outlined">
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Cache</TableCell>
                      <TableCell>Description</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Files</TableCell>
                      <TableCell align="right">Size (MB)</TableCell>
                      <TableCell align="right">Coverage</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {resourceUsage.disk_caches.map((cache) => (
                      <TableRow key={cache.name}>
                        <TableCell><Typography variant="body2" fontWeight="bold">{cache.name}</Typography></TableCell>
                        <TableCell><Typography variant="caption" color="text.secondary">{cache.description}</Typography></TableCell>
                        <TableCell>
                          <Chip
                            label={cache.exists ? 'Present' : 'Missing'}
                            size="small"
                            color={cache.exists && cache.file_count > 0 ? 'success' : 'warning'}
                          />
                        </TableCell>
                        <TableCell align="right">{cache.file_count.toLocaleString()}</TableCell>
                        <TableCell align="right">{cache.total_size_mb.toFixed(2)}</TableCell>
                        <TableCell align="right">
                          {cache.coverage_pct !== null ? (
                            <Chip
                              label={`${cache.coverage_pct}%`}
                              size="small"
                              color={cache.coverage_pct >= 95 ? 'success' : cache.coverage_pct >= 50 ? 'warning' : 'error'}
                            />
                          ) : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Card>
            </>
          ) : (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="body2" color={resourceUsageError ? 'error' : 'text.secondary'}>
                  {resourceUsageError
                    ? `Failed to load: ${resourceUsageError}`
                    : cacheRefreshing
                    ? 'Refreshing caches…'
                    : 'Click "Refresh Cache" to load resource usage and cache status.'}
                </Typography>
              </CardContent>
            </Card>
          )}
        </Box>

        <Box mt={3}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Dashboard Snapshots (Team/Scrum/Employee)</Typography>
                <Box display="flex" gap={1}>
                  <Button size="small" variant="outlined" startIcon={<RefreshIcon />} onClick={fetchDashboardSnapshotStatus}>
                    Refresh Status
                  </Button>
                </Box>
              </Box>

              <Grid container spacing={2} alignItems="center">
                <Grid item xs={12} md={4}>
                  <TextField
                    fullWidth
                    size="small"
                    type="date"
                    label="As of Date"
                    value={snapshotAsOfDate}
                    onChange={(e) => setSnapshotAsOfDate(e.target.value)}
                    InputLabelProps={{ shrink: true }}
                    helperText="Optional. Leave blank to use latest available date."
                  />
                </Grid>
                <Grid item xs={12} md={8}>
                  <Box display="flex" gap={1} alignItems="center" flexWrap="wrap">
                    <Button
                      size="small"
                      variant="contained"
                      startIcon={snapshotGenerating ? <CircularProgress size={16} /> : <PlayIcon />}
                      disabled={snapshotGenerating || snapshotStatus?.generator?.running || isReadOnly}
                      onClick={generateDashboardSnapshot}
                      title={isReadOnly ? readOnlyMessage : ''}
                    >
                      {snapshotGenerating ? 'Submitting…' : 'Generate Snapshot'}
                    </Button>
                    {snapshotStatus?.generator?.running && (
                      <Chip label="Generation running" color="info" size="small" />
                    )}
                    {snapshotStatus?.generator?.last_error && (
                      <Chip label="Last run failed" color="error" size="small" />
                    )}
                  </Box>
                </Grid>
              </Grid>

              <Box mt={2}>
                <Typography variant="subtitle2" gutterBottom>Active Snapshot</Typography>
                {snapshotStatus?.active_snapshot?.active ? (
                  <Box display="flex" gap={1} flexWrap="wrap">
                    <Chip label={`ID: ${snapshotStatus.active_snapshot.snapshot_id}`} size="small" variant="outlined" />
                    <Chip label={`As of: ${snapshotStatus.active_snapshot.as_of_date}`} size="small" variant="outlined" />
                    <Chip label={`Generated: ${formatTimestamp(snapshotStatus.active_snapshot.generated_at || null)}`} size="small" variant="outlined" />
                    <Chip label={`Teams: ${snapshotStatus.active_snapshot.team_count ?? 0}`} size="small" variant="outlined" />
                    <Chip label={`Scrums: ${snapshotStatus.active_snapshot.scrum_count ?? 0}`} size="small" variant="outlined" />
                    <Chip label={`Employees: ${snapshotStatus.active_snapshot.employee_count ?? 0}`} size="small" variant="outlined" />
                    <Chip label={`Source: ${snapshotStatus.active_snapshot.source || 'unknown'}`} size="small" variant="outlined" />
                  </Box>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    {snapshotStatus?.active_snapshot?.message || 'No active snapshot yet.'}
                  </Typography>
                )}
              </Box>
            </CardContent>
          </Card>
        </Box>
        </>
      )}

      {/* TAB 1: Job Scheduling & Recent Executions */}
      {activeTab === 1 && (
        <Box>
          {/* Jobs Management */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Scheduled Jobs</Typography>
                <Box display="flex" gap={2} alignItems="center">
                  <Tooltip title={isReadOnly ? readOnlyMessage : runAllStatus?.running ? 'Sequential run already in progress' : 'Run all jobs in sequence, one after another'}>
                    <span>
                      <Button
                        variant="contained"
                        size="small"
                        color="secondary"
                        startIcon={runAllLoading || runAllStatus?.running ? <CircularProgress size={16} color="inherit" /> : <PlayIcon />}
                        onClick={triggerRunAll}
                        disabled={runAllLoading || !!runAllStatus?.running || isReadOnly}
                      >
                        {runAllStatus?.running ? 'Running All…' : 'Run All Jobs'}
                      </Button>
                    </span>
                  </Tooltip>
                  <Tooltip title="Configure schedule for Run All Jobs">
                    <span>
                      <IconButton
                        size="small"
                        color="default"
                        onClick={() => {
                          const runAllJob = jobs.find(j => j.job_id === 'run_all_chain');
                          if (runAllJob) openScheduleDialog(runAllJob);
                        }}
                        disabled={!jobs.find(j => j.job_id === 'run_all_chain') || isReadOnly}
                      >
                        <SettingsIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title="Pause all scheduled jobs — cron expressions are preserved so you can resume later">
                    <span>
                      <Button
                        variant="outlined"
                        size="small"
                        color="warning"
                        startIcon={bulkScheduleLoading ? <CircularProgress size={16} color="inherit" /> : <PauseIcon />}
                        onClick={pauseAllJobs}
                        disabled={bulkScheduleLoading || isReadOnly}
                      >
                        Pause All
                      </Button>
                    </span>
                  </Tooltip>
                  <Tooltip title="Re-enable all scheduled jobs">
                    <span>
                      <Button
                        variant="outlined"
                        size="small"
                        color="success"
                        startIcon={bulkScheduleLoading ? <CircularProgress size={16} color="inherit" /> : <ResumeIcon />}
                        onClick={resumeAllJobs}
                        disabled={bulkScheduleLoading || isReadOnly}
                      >
                        Resume All
                      </Button>
                    </span>
                  </Tooltip>
                  <FormControlLabel
                    control={
                      <Switch checked={pollingEnabled} onChange={(e) => setPollingEnabled(e.target.checked)} disabled={isReadOnly} />
                    }
                    label="Auto-refresh"
                  />
                </Box>
              </Box>

              {/* Run-All status panel */}
              {runAllStatus && (runAllStatus.running || runAllStatus.completed.length > 0 || runAllStatus.failed.length > 0) && (
                <Box sx={{ mb: 2, p: 1.5, border: '1px solid', borderColor: runAllStatus.running ? 'info.main' : runAllStatus.failed.length > 0 ? 'error.light' : 'success.light', borderRadius: 1, bgcolor: runAllStatus.running ? 'info.50' : 'background.paper' }}>
                  <Box display="flex" alignItems="center" gap={1} mb={1}>
                    {runAllStatus.running ? <CircularProgress size={16} /> : runAllStatus.failed.length > 0 ? <ErrorIcon fontSize="small" color="error" /> : <CheckCircleIcon fontSize="small" color="success" />}
                    <Typography variant="subtitle2">
                      {runAllStatus.running
                        ? `Running all jobs — current: ${jobs.find(j => j.job_id === runAllStatus.current_job_id)?.name ?? runAllStatus.current_job_id ?? '…'}`
                        : `Run all finished${runAllStatus.failed.length > 0 ? ` (${runAllStatus.failed.length} failed)` : ' — all done'}`}
                    </Typography>
                    {runAllStatus.started_at && (
                      <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                        Started: {formatTimestamp(runAllStatus.started_at)}
                      </Typography>
                    )}
                  </Box>
                  <Box display="flex" gap={0.5} flexWrap="wrap">
                    {runAllStatus.completed.map(jid => (
                      <Chip key={jid} label={jobs.find(j => j.job_id === jid)?.name ?? jid} size="small" color="success" variant="outlined" icon={<CheckCircleIcon />} />
                    ))}
                    {runAllStatus.running && runAllStatus.current_job_id && (
                      <Chip key={runAllStatus.current_job_id} label={jobs.find(j => j.job_id === runAllStatus.current_job_id)?.name ?? runAllStatus.current_job_id} size="small" color="info" icon={<CircularProgress size={12} />} />
                    )}
                    {runAllStatus.failed.map(jid => (
                      <Chip key={jid} label={jobs.find(j => j.job_id === jid)?.name ?? jid} size="small" color="error" variant="outlined" icon={<ErrorIcon />} />
                    ))}
                    {runAllStatus.skipped.map(jid => (
                      <Chip key={jid} label={(jobs.find(j => j.job_id === jid)?.name ?? jid) + ' (skipped)'} size="small" color="warning" variant="outlined" />
                    ))}
                    {runAllStatus.pending.map(jid => (
                      <Chip key={jid} label={jobs.find(j => j.job_id === jid)?.name ?? jid} size="small" variant="outlined" />
                    ))}
                  </Box>
                </Box>
              )}

              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                Schedule input/output is shown in local browser time ({localTimeZone}). Scheduler timezone: {schedulerTimezone}.
                {' '}Click a row to view progress and output.
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell padding="checkbox" />
                      <TableCell>Job</TableCell>
                      <TableCell>Schedule</TableCell>
                      <TableCell>Last Run</TableCell>
                      <TableCell>Last Status</TableCell>
                      <TableCell>Duration</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {jobsLoading && jobs.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} align="center">
                          <Typography variant="body2" color="text.secondary">Loading jobs…</Typography>
                        </TableCell>
                      </TableRow>
                    )}
                    {!jobsLoading && jobs.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={7} align="center">
                          <Typography variant="body2" color="text.secondary">No jobs available.</Typography>
                        </TableCell>
                      </TableRow>
                    )}
                    {jobs.map((job) => {
                      const progress = jobProgress[job.job_id];
                      const isRunning = progress?.status === 'running';
                      const isExpanded = expandedJobId === job.job_id;

                      return (
                        <React.Fragment key={job.job_id}>
                          <TableRow
                            hover
                            sx={{ cursor: 'pointer', ...(isRunning ? { bgcolor: 'action.hover' } : {}) }}
                            onClick={() => {
                              if (isExpanded) {
                                setExpandedJobId(null);
                              } else {
                                setExpandedJobId(job.job_id);
                                fetchJobProgress(job.job_id);
                              }
                            }}
                          >
                            <TableCell padding="checkbox">
                              <IconButton size="small">
                                {isExpanded ? <CollapseRowIcon /> : <ExpandRowIcon />}
                              </IconButton>
                            </TableCell>
                            <TableCell>
                              <Box>
                                <Typography variant="body2" fontWeight="medium">{job.name}</Typography>
                                <Typography variant="caption" color="text.secondary">{job.description}</Typography>
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Box display="flex" gap={0.5} flexWrap="wrap">
                                <Chip
                                  icon={<ScheduleIcon />}
                                  label={getScheduleLabel(job)}
                                  size="small"
                                  color={job.schedule?.enabled ? 'primary' : 'default'}
                                  variant={job.schedule?.enabled ? 'filled' : 'outlined'}
                                />
                                {job.schedule && !job.schedule.enabled && (job.schedule.cron_expression || job.schedule.interval_minutes) && (
                                  <Chip icon={<PauseIcon />} label="Paused" size="small" color="warning" />
                                )}
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Typography variant="caption">
                                {job.last_run_at ? formatTimestamp(job.last_run_at) : 'Never'}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              {job.last_run_status ? (
                                <Chip
                                  label={job.last_run_status.toUpperCase()}
                                  color={getStatusColor(job.last_run_status)}
                                  size="small"
                                />
                              ) : (
                                <Typography variant="caption" color="text.secondary">—</Typography>
                              )}
                              {isRunning && (
                                <Chip label="RUNNING" color="info" size="small" sx={{ ml: 0.5 }}
                                  icon={<CircularProgress size={10} color="inherit" />} />
                              )}
                            </TableCell>
                            <TableCell>
                              <Typography variant="caption">
                                {job.last_run_duration_seconds !== null ? formatDuration(job.last_run_duration_seconds) : '—'}
                              </Typography>
                            </TableCell>
                            <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                              <Box display="flex" gap={0.5} justifyContent="flex-end">
                                <Tooltip title={isReadOnly ? readOnlyMessage : "Run Now"}>
                                  <span>
                                    <IconButton size="small" color="primary"
                                      onClick={() => triggerJob(job.job_id)}
                                      disabled={isRunning || !job.enabled || isReadOnly}>
                                      <PlayIcon fontSize="small" />
                                    </IconButton>
                                  </span>
                                </Tooltip>
                                {isRunning && (
                                  <Tooltip title={isReadOnly ? readOnlyMessage : "Stop Job"}>
                                    <IconButton size="small" color="error" onClick={() => cancelJob(job.job_id)} disabled={isReadOnly}>
                                      <StopIcon fontSize="small" />
                                    </IconButton>
                                  </Tooltip>
                                )}
                                {job.schedule && (job.schedule.cron_expression || job.schedule.interval_minutes) && (
                                  <Tooltip title={isReadOnly ? readOnlyMessage : job.schedule.enabled ? "Pause schedule" : "Resume schedule"}>
                                    <IconButton size="small"
                                      color={job.schedule.enabled ? 'warning' : 'success'}
                                      onClick={() => toggleJobPause(job)}
                                      disabled={isRunning || isReadOnly}>
                                      {job.schedule.enabled ? <PauseIcon fontSize="small" /> : <ResumeIcon fontSize="small" />}
                                    </IconButton>
                                  </Tooltip>
                                )}
                                {job.job_id === 'jira_fetch' && (
                                  <Tooltip title="Configure fetch mode">
                                    <span>
                                      <IconButton size="small"
                                        color={(jiraFetchStatus?.forceFullFetch.length ?? 0) > 0 ? 'warning' : 'default'}
                                        onClick={openFullFetchDialog}
                                        disabled={isRunning}>
                                        <SyncIcon fontSize="small" />
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                )}
                                {job.job_id === 'daily_backup_matrix' && (
                                  <Tooltip title="Trigger full backup">
                                    <span>
                                      <IconButton size="small" color="secondary"
                                        onClick={triggerFullBackup}
                                        disabled={isRunning || fullBackupLoading}>
                                        {fullBackupLoading ? <CircularProgress size={14} /> : <StorageIcon fontSize="small" />}
                                      </IconButton>
                                    </span>
                                  </Tooltip>
                                )}
                                <Tooltip title="Configure Schedule">
                                  <IconButton size="small" color="default" onClick={() => openScheduleDialog(job)} disabled={isReadOnly}>
                                    <SettingsIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              </Box>
                            </TableCell>
                          </TableRow>

                          {/* Expandable detail row — progress, output, errors */}
                          <TableRow>
                            <TableCell colSpan={7} sx={{ py: 0, border: isExpanded ? undefined : 'none' }}>
                              <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                                <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1, my: 1 }}>
                                  <Typography variant="subtitle2" gutterBottom>{job.name} — Detail</Typography>
                                  <Typography variant="caption" color="text.secondary" display="block" mb={1}>{job.description}</Typography>

                                  {/* Exit code + last run info */}
                                  <Box display="flex" gap={1} flexWrap="wrap" mb={1}>
                                    {job.last_run_exit_code !== null && (
                                      <Chip
                                        label={`Exit code: ${job.last_run_exit_code}`}
                                        size="small" variant="outlined"
                                        color={job.last_run_exit_code === 0 ? 'success' : 'error'}
                                      />
                                    )}
                                    {job.job_id === 'jira_fetch' && jiraFetchStatus && (() => {
                                      const forced = jiraFetchStatus.forceFullFetch;
                                      const allForced = forced.includes('__ALL__');
                                      const someForced = forced.length > 0;
                                      const mode = allForced ? 'Full Fetch (All)'
                                        : someForced ? `Full Fetch (${forced.length} project${forced.length > 1 ? 's' : ''})` : 'Delta Mode';
                                      return (
                                        <Chip icon={<SyncIcon />} label={`Next Run: ${mode}`} size="small"
                                          color={someForced || allForced ? 'warning' : 'success'} variant="outlined" />
                                      );
                                    })()}
                                  </Box>

                                  {/* Warning */}
                                  {jobWarnings[job.job_id] && (
                                    <Alert severity="warning" sx={{ mb: 1, py: 0.5 }}
                                      onClose={() => setJobWarnings((prev) => { const next = { ...prev }; delete next[job.job_id]; return next; })}>
                                      {jobWarnings[job.job_id]}
                                    </Alert>
                                  )}

                                  {/* Progress */}
                                  {!progress ? (
                                    <Typography variant="caption" color="text.secondary">No progress data — run the job to see live output.</Typography>
                                  ) : (
                                    <Box>
                                      <Box display="flex" alignItems="center" gap={1} mb={1}>
                                        {getStatusIcon(progress.status)}
                                        <Chip label={progress.status.toUpperCase()} color={getStatusColor(progress.status)} size="small" />
                                        {progress.message && (
                                          <Typography variant="body2" color="text.secondary">{progress.message}</Typography>
                                        )}
                                      </Box>
                                      {isRunning && (
                                        <LinearProgress
                                          variant={progress.progress_percent > 0 ? 'determinate' : 'indeterminate'}
                                          value={progress.progress_percent}
                                          sx={{ mb: 1 }}
                                        />
                                      )}
                                      {progress.output_lines.length > 0 && (
                                        <Box sx={{
                                          maxHeight: 200, overflow: 'auto',
                                          bgcolor: 'grey.200', p: 1, borderRadius: 1,
                                          fontFamily: 'monospace', fontSize: '0.72rem',
                                        }}>
                                          {progress.output_lines.map((line, idx) => (
                                            <div key={idx}>{line}</div>
                                          ))}
                                        </Box>
                                      )}
                                      {progress.error_message && (
                                        <Alert severity="error" sx={{ mt: 1 }}>{progress.error_message}</Alert>
                                      )}
                                    </Box>
                                  )}
                                </Box>
                              </Collapse>
                            </TableCell>
                          </TableRow>
                        </React.Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>

          {/* Execution History */}
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Recent Executions</Typography>
                <Button startIcon={<RefreshIcon />} onClick={fetchHistory} size="small">
                  Refresh
                </Button>
              </Box>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Job</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Started</TableCell>
                      <TableCell>Duration</TableCell>
                      <TableCell>Triggered By</TableCell>
                      <TableCell>Exit Code</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {jobHistory.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} align="center">
                          No executions yet
                        </TableCell>
                      </TableRow>
                    ) : (
                      jobHistory.map((execution) => (
                        <TableRow key={execution.execution_id}>
                          <TableCell>
                            {jobs.find((j) => j.job_id === execution.job_id)?.name || execution.job_id}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={execution.status}
                              color={getStatusColor(execution.status)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell>{formatTimestamp(execution.started_at)}</TableCell>
                          <TableCell>{formatDuration(execution.duration_seconds)}</TableCell>
                          <TableCell>{execution.triggered_by}</TableCell>
                          <TableCell>
                            {execution.exit_code !== null ? execution.exit_code : 'N/A'}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* TAB 2: Scoring & Thresholds */}
      {activeTab === 2 && (
        <Box>
          <ScoringConfigPanel />
        </Box>
      )}

      {/* TAB 3: Project Onboarding */}
      {activeTab === 3 && (
        <Box>
          <ProjectOnboardingPage />
        </Box>
      )}

      {/* TAB 4: Maintenance */}
      {activeTab === 4 && (
        <Box>
          <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
            <Tabs
              value={maintenanceSubTab}
              onChange={(_, newValue) => {
                setMaintenanceSubTab(newValue);
                if (newValue === 0) fetchBackups();
                if (newValue === 1) fetchAuditLogStats();
              }}
              aria-label="maintenance subtabs"
            >
              <Tab label="Backup Maintenance" />
              <Tab label="Audit Log Maintenance" />
            </Tabs>
          </Box>

          {maintenanceSubTab === 0 && (
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Backup Management</Typography>
                <Box display="flex" gap={1}>
                  <Button startIcon={<RefreshIcon />} onClick={fetchBackups} size="small" disabled={backupsLoading}>
                    Refresh
                  </Button>
                  <Button
                    startIcon={deletingBackups ? <CircularProgress size={16} /> : <DeleteIcon />}
                    onClick={deleteSelectedBackups}
                    size="small"
                    variant="contained"
                    color="error"
                    disabled={selectedBackups.length === 0 || deletingBackups || isReadOnly}
                    title={isReadOnly ? readOnlyMessage : ''}
                  >
                    Delete Selected ({selectedBackups.length})
                  </Button>
                  <Button
                    startIcon={fullBackupLoading ? <CircularProgress size={16} /> : <StorageIcon />}
                    onClick={triggerFullBackup}
                    size="small"
                    variant="outlined"
                    color="secondary"
                    disabled={fullBackupLoading || isReadOnly}
                    title={isReadOnly ? readOnlyMessage : ''}
                  >
                    Full Backup Now
                  </Button>
                </Box>
              </Box>

              <Typography variant="body2" color="text.secondary" mb={2}>
                Backup snapshots created by the Daily Backup Matrix job. <strong>Daily backups</strong> contain key CSV files and config. <strong>Full backups</strong> (every Sunday, or manual) also copy the entire output/ directory. Backups older than 31 days are auto-deleted.
              </Typography>

              {backupsError && <Alert severity="error" sx={{ mb: 2 }}>{backupsError}</Alert>}

              {backupsLoading ? (
                <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
              ) : backups.length === 0 ? (
                <Typography color="text.secondary" align="center" py={4}>No backup folders found.</Typography>
              ) : (
                <Box>
                  {Object.entries(groupedBackups)
                    .sort(([a], [b]) => b.localeCompare(a))
                    .map(([year, months]) => {
                      const yearBackups = Object.values(months).flatMap(dates => Object.values(dates).flat());
                      const yearNames = yearBackups.map(b => b.name);
                      const yearState = getSelectionState(yearNames);
                      return (
                        <Accordion key={year} defaultExpanded disableGutters sx={{ mb: 1 }}>
                          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                            <Checkbox
                              checked={yearState === 'all'}
                              indeterminate={yearState === 'some'}
                              onClick={(e) => { e.stopPropagation(); toggleGroup(yearNames); }}
                              sx={{ mr: 1 }}
                              size="small"
                            />
                            <Typography variant="subtitle1" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              {year}
                              <Typography component="span" variant="body2" color="text.secondary">
                                {yearBackups.length} backup{yearBackups.length !== 1 ? 's' : ''}
                              </Typography>
                            </Typography>
                          </AccordionSummary>
                          <AccordionDetails sx={{ pt: 0, pl: 2 }}>
                            {Object.entries(months)
                              .sort(([a], [b]) => b.localeCompare(a))
                              .map(([month, dates]) => {
                                const monthBackups = Object.values(dates).flat();
                                const monthNames = monthBackups.map(b => b.name);
                                const monthState = getSelectionState(monthNames);
                                return (
                                  <Accordion key={month} defaultExpanded disableGutters variant="outlined" sx={{ mb: 1 }}>
                                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                      <Checkbox
                                        checked={monthState === 'all'}
                                        indeterminate={monthState === 'some'}
                                        onClick={(e) => { e.stopPropagation(); toggleGroup(monthNames); }}
                                        sx={{ mr: 1 }}
                                        size="small"
                                      />
                                      <Typography variant="subtitle2" fontWeight="medium" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                        {MONTH_NAMES[month] || month} {year}
                                        <Typography component="span" variant="body2" color="text.secondary">
                                          {monthBackups.length} backup{monthBackups.length !== 1 ? 's' : ''}
                                        </Typography>
                                      </Typography>
                                    </AccordionSummary>
                                    <AccordionDetails sx={{ pt: 0, px: 1 }}>
                                      <TableContainer component={Paper} variant="outlined">
                                        <Table size="small">
                                          <TableBody>
                                            {Object.entries(dates)
                                              .sort(([a], [b]) => b.localeCompare(a))
                                              .map(([date, dayBackups]) => {
                                                const dayNames = dayBackups.map(b => b.name);
                                                const dayState = getSelectionState(dayNames);
                                                return (
                                                  <React.Fragment key={date}>
                                                    <TableRow sx={{ bgcolor: 'action.hover' }}>
                                                      <TableCell padding="checkbox">
                                                        <Checkbox
                                                          checked={dayState === 'all'}
                                                          indeterminate={dayState === 'some'}
                                                          onChange={() => toggleGroup(dayNames)}
                                                          size="small"
                                                        />
                                                      </TableCell>
                                                      <TableCell colSpan={4}>
                                                        <Typography variant="body2" fontWeight="bold">
                                                          {MONTH_NAMES[month] || month} {parseInt(date, 10)}, {year}
                                                        </Typography>
                                                      </TableCell>
                                                    </TableRow>
                                                    {dayBackups.map((backup) => {
                                                      const typeLabel = backup.backup_type === 'full' ? 'Full' : backup.backup_type === 'full_catchup' ? 'Full (catch-up)' : 'Daily';
                                                      const typeColor: 'primary' | 'secondary' | 'default' = backup.backup_type === 'full' ? 'primary' : backup.backup_type === 'full_catchup' ? 'secondary' : 'default';
                                                      
                                                      // Format the created_at timestamp (server local time) for display
                                                      let timeDisplayStr = '—';
                                                      if (backup.created_at) {
                                                        try {
                                                          // Expected format: "YYYY-MM-DD HH:MM:SS" (server local time)
                                                          // Create a date object and format it in user's local timezone
                                                          const dateObj = new Date(backup.created_at + 'Z'); // Treat as UTC for parsing
                                                          if (!isNaN(dateObj.getTime())) {
                                                            const timeOnly = dateObj.toLocaleTimeString(undefined, { 
                                                              hour: '2-digit', 
                                                              minute: '2-digit', 
                                                              second: '2-digit',
                                                              hour12: false 
                                                            });
                                                            timeDisplayStr = timeOnly;
                                                          }
                                                        } catch (e) {
                                                          // If parsing fails, extract from string directly
                                                          const parts = backup.created_at.split(' ');
                                                          timeDisplayStr = parts.length > 1 ? parts[1] : '—';
                                                        }
                                                      }
                                                      
                                                      return (
                                                        <TableRow key={backup.name} hover selected={selectedBackups.includes(backup.name)}>
                                                          <TableCell padding="checkbox">
                                                            <Checkbox
                                                              checked={selectedBackups.includes(backup.name)}
                                                              onChange={(e) => {
                                                                if (e.target.checked) {
                                                                  setSelectedBackups(prev => [...prev, backup.name]);
                                                                } else {
                                                                  setSelectedBackups(prev => prev.filter(n => n !== backup.name));
                                                                }
                                                              }}
                                                              size="small"
                                                            />
                                                          </TableCell>
                                                          <TableCell sx={{ pl: 3 }}>
                                                            <Box display="flex" alignItems="center" gap={1}>
                                                              <FolderIcon fontSize="small" color="action" />
                                                              <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{backup.name}</Typography>
                                                            </Box>
                                                          </TableCell>
                                                          <TableCell>
                                                            <Box display="flex" gap={0.5} alignItems="center">
                                                              <Chip label={typeLabel} size="small" color={typeColor} variant="outlined" />
                                                              <Typography variant="body2" color="text.secondary">
                                                                {timeDisplayStr !== '—' ? `at ${timeDisplayStr}` : '—'}
                                                              </Typography>
                                                            </Box>
                                                          </TableCell>

                                                        </TableRow>
                                                      );
                                                    })}
                                                  </React.Fragment>
                                                );
                                              })}
                                          </TableBody>
                                        </Table>
                                      </TableContainer>
                                    </AccordionDetails>
                                  </Accordion>
                                );
                              })}
                          </AccordionDetails>
                        </Accordion>
                      );
                    })}
                </Box>
              )}
            </CardContent>
          </Card>
          )}

          {maintenanceSubTab === 1 && (
            <Card>
              <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6">Audit Log Maintenance</Typography>
                  <Button startIcon={<RefreshIcon />} onClick={fetchAuditLogStats} size="small" disabled={auditLogLoading}>
                    Refresh
                  </Button>
                </Box>

                <Typography variant="body2" color="text.secondary" mb={2}>
                  Trim persisted audit events to reduce file growth. This action keeps only the latest N events in the audit log file.
                </Typography>

                {auditLogError && <Alert severity="error" sx={{ mb: 2 }}>{auditLogError}</Alert>}
                {auditLogSuccess && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setAuditLogSuccess(null)}>{auditLogSuccess}</Alert>}

                {auditLogLoading ? (
                  <Box display="flex" justifyContent="center" py={3}><CircularProgress /></Box>
                ) : (
                  <Box>
                    <Grid container spacing={2} sx={{ mb: 2 }}>
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          label="Current total events"
                          value={auditLogStats?.total_events ?? 0}
                          InputProps={{ readOnly: true }}
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          select
                          label="Trim mode"
                          value={auditTrimMode}
                          onChange={(e) => setAuditTrimMode(e.target.value as 'keep_latest' | 'before_date' | 'before_month' | 'before_year')}
                        >
                          <MenuItem value="keep_latest">Keep latest N events</MenuItem>
                          <MenuItem value="before_date">Trim older than date</MenuItem>
                          <MenuItem value="before_month">Trim older than month</MenuItem>
                          <MenuItem value="before_year">Trim older than year</MenuItem>
                        </TextField>
                      </Grid>

                      {auditTrimMode === 'keep_latest' && (
                        <Grid item xs={12} md={6}>
                          <TextField
                            fullWidth
                            label="Keep latest events"
                            type="number"
                            inputProps={{ min: 0, step: 1 }}
                            value={auditTrimKeepLatest}
                            onChange={(e) => setAuditTrimKeepLatest(e.target.value)}
                          />
                        </Grid>
                      )}

                      {auditTrimMode === 'before_date' && (
                        <Grid item xs={12} md={6}>
                          <TextField
                            fullWidth
                            label="Cutoff date"
                            type="date"
                            value={auditTrimDate}
                            onChange={(e) => setAuditTrimDate(e.target.value)}
                            InputLabelProps={{ shrink: true }}
                          />
                        </Grid>
                      )}

                      {auditTrimMode === 'before_month' && (
                        <Grid item xs={12} md={6}>
                          <TextField
                            fullWidth
                            label="Cutoff month"
                            type="month"
                            value={auditTrimMonth}
                            onChange={(e) => setAuditTrimMonth(e.target.value)}
                            InputLabelProps={{ shrink: true }}
                          />
                        </Grid>
                      )}

                      {auditTrimMode === 'before_year' && (
                        <Grid item xs={12} md={6}>
                          <TextField
                            fullWidth
                            label="Cutoff year"
                            type="number"
                            inputProps={{ min: 1970, max: 3000, step: 1 }}
                            value={auditTrimYear}
                            onChange={(e) => setAuditTrimYear(e.target.value)}
                          />
                        </Grid>
                      )}
                    </Grid>

                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                      Audit file: {auditLogStats?.audit_file || 'Unknown'}
                    </Typography>

                    <Button
                      variant="contained"
                      color="warning"
                      startIcon={auditTrimLoading ? <CircularProgress size={16} /> : <DeleteIcon />}
                      onClick={trimAuditLogs}
                      disabled={auditTrimLoading || isReadOnly}
                      title={isReadOnly ? readOnlyMessage : ''}
                    >
                      Trim Audit Log
                    </Button>
                  </Box>
                )}
              </CardContent>
            </Card>
          )}
        </Box>
      )}

      {activeTab === 5 && <FileViewerTab />}

      {activeTab === 6 && (
        <Box>
          <Grid container spacing={2}>
            <Grid item xs={12} md={5}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>Compose Dashboard Message</Typography>
                  <TextField
                    fullWidth
                    multiline
                    minRows={3}
                    label="Message"
                    value={messageDraft.text}
                    onChange={(e) => setMessageDraft((prev) => ({ ...prev, text: e.target.value }))}
                    helperText="Use quick-copy placeholders below. You can use {placeholder} or {{placeholder}} syntax."
                    sx={{ mb: 2 }}
                  />
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="caption" color="text.secondary">
                      Quick copy tokens (grouped)
                    </Typography>
                    <Box sx={{ mt: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
                      {placeholderCategories.map((category) => {
                        const categoryType = category.type || 'placeholder';
                        const wrapInBraces = categoryType === 'placeholder';
                        return (
                          <Accordion key={category.id} disableGutters variant="outlined" defaultExpanded={category.id === 'employee'}>
                            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {category.label} ({category.placeholders.length})
                              </Typography>
                            </AccordionSummary>
                            <AccordionDetails>
                              {category.description && (
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                                  {category.description}
                                </Typography>
                              )}
                              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                                {category.placeholders.map((placeholder) => {
                                  const copiedKey = `${category.id}:${placeholder}`;
                                  return (
                                    <Chip
                                      key={copiedKey}
                                      size="small"
                                      label={wrapInBraces ? `{${placeholder}}` : placeholder}
                                      clickable
                                      color={copiedPlaceholder === copiedKey ? 'success' : 'default'}
                                      variant={copiedPlaceholder === copiedKey ? 'filled' : 'outlined'}
                                      onClick={() =>
                                        copyTokenToClipboard(placeholder, {
                                          wrapInBraces,
                                          copiedKey,
                                        })
                                      }
                                    />
                                  );
                                })}
                              </Box>
                            </AccordionDetails>
                          </Accordion>
                        );
                      })}
                    </Box>
                    {copiedPlaceholder && (
                      <Typography variant="caption" color="success.main" sx={{ display: 'block', mt: 1 }}>
                        Copied to clipboard
                      </Typography>
                    )}
                  </Box>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        select
                        fullWidth
                        label="Severity"
                        value={messageDraft.severity}
                        onChange={(e) => setMessageDraft((prev) => ({ ...prev, severity: e.target.value as DashboardMessage['severity'] }))}
                      >
                        <MenuItem value="critical">Critical</MenuItem>
                        <MenuItem value="high">High</MenuItem>
                        <MenuItem value="warning">Warning</MenuItem>
                        <MenuItem value="compliance">Compliance</MenuItem>
                        <MenuItem value="info">Info</MenuItem>
                        <MenuItem value="low">Low</MenuItem>
                      </TextField>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        select
                        fullWidth
                        label="Target Scope"
                        value={messageDraft.scope}
                        onChange={(e) => setMessageDraft((prev) => ({ ...prev, scope: e.target.value as DashboardMessage['scope'] }))}
                      >
                        <MenuItem value="all">All Employees</MenuItem>
                        <MenuItem value="team">Specific Team(s)</MenuItem>
                        <MenuItem value="scrum">Specific Scrum(s)</MenuItem>
                        <MenuItem value="employee">Specific Employee(s)</MenuItem>
                      </TextField>
                    </Grid>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        disabled={messageDraft.scope === 'all'}
                        label="Targets (comma-separated)"
                        placeholder={messageDraft.scope === 'team' ? 'AION, OOSM' : messageDraft.scope === 'scrum' ? 'Scrum Alpha, Scrum Beta' : '12345678, Jane Doe'}
                        value={messageDraft.targetCsv}
                        onChange={(e) => setMessageDraft((prev) => ({ ...prev, targetCsv: e.target.value }))}
                        helperText={
                          messageDraft.scope === 'team'
                            ? `Teams available: ${messageOptions.teams.slice(0, 8).join(', ')}${messageOptions.teams.length > 8 ? '...' : ''}`
                            : messageDraft.scope === 'scrum'
                            ? `Scrums available: ${messageOptions.scrums.slice(0, 8).join(', ')}${messageOptions.scrums.length > 8 ? '...' : ''}`
                            : messageDraft.scope === 'employee'
                            ? 'Use SAPID(s) or employee name(s)'
                            : 'Not required for All scope'
                        }
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="KPI Red Condition (optional)"
                        placeholder="k1, k57"
                        value={messageDraft.kpiRedCsv}
                        onChange={(e) => setMessageDraft((prev) => ({ ...prev, kpiRedCsv: e.target.value }))}
                        disabled={messageDraft.requireAnyRedKpi}
                        helperText={messageDraft.requireAnyRedKpi ? 'Ignored while Any Red KPI is enabled' : 'Message appears only when any listed KPI is red'}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={messageDraft.requireAnyRedKpi}
                            onChange={(e) => setMessageDraft((prev) => ({ ...prev, requireAnyRedKpi: e.target.checked }))}
                          />
                        }
                        label="Any Red KPI"
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        Show this message when the employee has at least one red KPI.
                      </Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                        <TextField
                          select
                          fullWidth
                          label="Empty Resource Fields (optional)"
                          value={selectedEmptyResourceFields}
                          SelectProps={{
                            multiple: true,
                            renderValue: (selected) => {
                              const values = Array.isArray(selected) ? selected : [String(selected)];
                              return values.join(', ');
                            },
                          }}
                          onChange={(e) => {
                            const rawValue = e.target.value;
                            const selectedValues = Array.isArray(rawValue) ? rawValue : [String(rawValue)];
                            setMessageDraft((prev) => ({
                              ...prev,
                              emptyResourceFieldsCsv: selectedValues.join(', '),
                            }));
                          }}
                          helperText="Message appears when any selected Resources.csv field is empty"
                        >
                          {(messageOptions.resource_fields || []).map((fieldName) => (
                            <MenuItem key={fieldName} value={fieldName}>
                              <Checkbox checked={selectedEmptyResourceFields.includes(fieldName)} size="small" />
                              {fieldName}
                            </MenuItem>
                          ))}
                        </TextField>
                        <Button
                          variant="outlined"
                          size="small"
                          sx={{ mt: 1 }}
                          disabled={selectedEmptyResourceFields.length === 0}
                          onClick={() => setMessageDraft((prev) => ({ ...prev, emptyResourceFieldsCsv: '' }))}
                        >
                          Clear
                        </Button>
                      </Box>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Match as empty — extra values (optional)"
                        placeholder="e.g. pending, tbd"
                        value={messageDraft.emptyResourceFieldSentinelsCsv}
                        onChange={(e) => setMessageDraft((prev) => ({ ...prev, emptyResourceFieldSentinelsCsv: e.target.value }))}
                        helperText={'Built-in: blank, not_mapped, -NA-, nan, none, null, na, n/a. Add more custom values here (comma-separated).'}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        type="number"
                        label="Validity (days)"
                        value={messageDraft.validity_days}
                        onChange={(e) => setMessageDraft((prev) => ({ ...prev, validity_days: parseInt(e.target.value || '0', 10) }))}
                        helperText="Use 0 for indefinite validity"
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={messageDraft.enabled}
                            onChange={(e) => setMessageDraft((prev) => ({ ...prev, enabled: e.target.checked }))}
                          />
                        }
                        label="Enabled"
                      />
                    </Grid>
                  </Grid>
                  <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
                    <Button 
                      variant="contained" 
                      onClick={saveDashboardMessage} 
                      disabled={messageSaving || isReadOnly}
                      title={isReadOnly ? readOnlyMessage : ''}
                    >
                      {messageDraft.id ? 'Update Message' : 'Create Message'}
                    </Button>
                    <Button variant="outlined" onClick={resetMessageDraft} disabled={messageSaving}>Reset</Button>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={7}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="h6">Configured Messages</Typography>
                    <Button size="small" startIcon={<RefreshIcon />} onClick={fetchDashboardMessages}>Refresh</Button>
                  </Box>
                  {messagesLoading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
                  ) : dashboardMessages.length === 0 ? (
                    <Typography color="text.secondary">No messages configured.</Typography>
                  ) : (
                    <TableContainer component={Paper} variant="outlined">
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Message</TableCell>
                            <TableCell>Severity</TableCell>
                            <TableCell>Scope</TableCell>
                            <TableCell>Conditions</TableCell>
                            <TableCell>Validity</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell align="right">Actions</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {dashboardMessages.map((msg) => (
                            <TableRow key={msg.id} hover>
                              <TableCell sx={{ maxWidth: 260 }}>
                                <Typography variant="body2">{msg.text}</Typography>
                              </TableCell>
                              <TableCell>
                                <Chip label={msg.severity.toUpperCase()} size="small" />
                              </TableCell>
                              <TableCell>
                                <Typography variant="caption">
                                  {msg.scope}
                                  {msg.target_values?.length ? `: ${msg.target_values.join(', ')}` : ''}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <Typography variant="caption">
                                  {msg.require_any_red_kpi
                                    ? 'KPI Red: Any red KPI'
                                    : msg.kpi_red_ids?.length
                                    ? `KPI Red: ${msg.kpi_red_ids.join(', ')}`
                                    : 'KPI Red: None'}
                                  <br />
                                  {msg.empty_resource_fields?.length
                                    ? `Empty Fields: ${msg.empty_resource_fields.join(', ')}${msg.empty_resource_field_sentinels?.length ? ` (custom sentinels: ${msg.empty_resource_field_sentinels.join(', ')})` : ''}`
                                    : 'Empty Fields: None'}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <Typography variant="caption">{msg.validity_days === 0 ? 'Indefinite' : `${msg.validity_days} day(s)`}</Typography>
                              </TableCell>
                              <TableCell>
                                <Chip
                                  label={msg.is_active ? 'Active' : 'Inactive'}
                                  size="small"
                                  color={msg.is_active ? 'success' : 'default'}
                                  variant={msg.is_active ? 'filled' : 'outlined'}
                                />
                              </TableCell>
                              <TableCell align="right">
                                <IconButton size="small" onClick={() => editDashboardMessage(msg)} disabled={isReadOnly}>
                                  <EditIcon fontSize="small" />
                                </IconButton>
                                <IconButton size="small" color="error" onClick={() => deleteDashboardMessage(msg.id)} disabled={isReadOnly}>
                                  <DeleteIcon fontSize="small" />
                                </IconButton>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Schedule Configuration Dialog */}
      <Dialog open={scheduleDialog.open} onClose={closeScheduleDialog} maxWidth="md" fullWidth>
        <DialogTitle>Configure Job Schedule</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <FormControlLabel
              control={
                <Switch
                  checked={scheduleDialog.schedule.enabled}
                  onChange={(e) =>
                    setScheduleDialog((prev) => ({
                      ...prev,
                      schedule: { ...prev.schedule, enabled: e.target.checked },
                    }))
                  }
                />
              }
              label="Enable Scheduled Execution"
            />

            {scheduleDialog.schedule.enabled && (
              <Box mt={3}>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Enter schedule in local browser time ({localTimeZone}). It will be stored for scheduler timezone {schedulerTimezone}.
                </Alert>
                <CronBuilder
                  value={scheduleDialog.schedule.cron_expression || ''}
                  timezoneLabel={localTimeZone}
                  onChange={(cronExpression) =>
                    setScheduleDialog((prev) => ({
                      ...prev,
                      schedule: { 
                        ...prev.schedule, 
                        cron_expression: cronExpression || null,
                        interval_minutes: null // Clear interval when using cron
                      },
                    }))
                  }
                />

                <Typography variant="body2" align="center" sx={{ my: 2 }} color="text.secondary">
                  OR use simple interval
                </Typography>

                <TextField
                  fullWidth
                  type="number"
                  label="Interval (minutes)"
                  placeholder="60"
                  value={scheduleDialog.schedule.interval_minutes || ''}
                  onChange={(e) =>
                    setScheduleDialog((prev) => ({
                      ...prev,
                      schedule: {
                        ...prev.schedule,
                        interval_minutes: e.target.value ? parseInt(e.target.value) : null,
                        cron_expression: null // Clear cron when using interval
                      },
                    }))
                  }
                  helperText="Run every N minutes (simpler alternative to cron expression)"
                />
              </Box>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeScheduleDialog}>Cancel</Button>
          <Button onClick={saveSchedule} variant="contained" color="primary">
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* JIRA Fetch Mode Dialog */}
      <Dialog open={fullFetchDialog} onClose={() => setFullFetchDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Configure Next JIRA Fetch Run</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2, mt: 1 }}>
            Select projects to force a <strong>full re-fetch</strong> on the next run.
            Unselected projects with a prior run recorded will use <strong>delta mode</strong> — only issues changed since the last run.
          </Typography>
          {jiraFetchStatus && (
            <>
              <Box display="flex" gap={1} mb={1}>
                <Button size="small" onClick={() => setFullFetchSelection([...jiraFetchStatus.configuredProjects])}>
                  Select All
                </Button>
                <Button size="small" onClick={() => setFullFetchSelection([])}>
                  Clear All
                </Button>
              </Box>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell padding="checkbox" />
                      <TableCell>Project</TableCell>
                      <TableCell>Next Run Mode</TableCell>
                      <TableCell>Last Fetched</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {jiraFetchStatus.configuredProjects.map((proj) => {
                      const isSelected = fullFetchSelection.includes(proj);
                      const hasTimestamp = Boolean(jiraFetchStatus.projectLastFetchTimestamp[proj]);
                      const mode = isSelected ? 'Full Fetch' : hasTimestamp ? 'Delta' : 'Full Fetch (no history)';
                      const modeColor: 'warning' | 'success' | 'default' = isSelected ? 'warning' : hasTimestamp ? 'success' : 'default';
                      const lastFetched = jiraFetchStatus.projectLastFetchTimestamp[proj];
                      return (
                        <TableRow
                          key={proj}
                          hover
                          onClick={() =>
                            setFullFetchSelection((prev) =>
                              prev.includes(proj) ? prev.filter((p) => p !== proj) : [...prev, proj]
                            )
                          }
                          sx={{ cursor: 'pointer' }}
                        >
                          <TableCell padding="checkbox">
                            <Checkbox checked={isSelected} size="small" />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" fontWeight="medium">{proj}</Typography>
                          </TableCell>
                          <TableCell>
                            <Chip label={mode} size="small" color={modeColor} variant="outlined" />
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption" color="text.secondary">
                              {lastFetched ? formatTimestamp(lastFetched) : 'Never'}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFullFetchDialog(false)}>Cancel</Button>
          <Button
            onClick={saveFullFetch}
            variant="contained"
            color="primary"
            disabled={fullFetchSaving}
            startIcon={fullFetchSaving ? <CircularProgress size={16} /> : <SyncIcon />}
          >
            Apply
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default AdminPage;
