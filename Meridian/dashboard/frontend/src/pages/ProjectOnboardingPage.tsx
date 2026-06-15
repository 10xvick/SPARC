import React, { useState, useEffect } from 'react';
import {
  Typography,
  Box,
  Card,
  CardContent,
  Grid,
  Button,
  TextField,
  Alert,
  Snackbar,
  Chip,
  IconButton,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  FormControl,
  InputLabel,
  OutlinedInput,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  CircularProgress,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Select,
  MenuItem,
  Tooltip,
} from '@mui/material';
import { SelectChangeEvent } from '@mui/material/Select';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Edit as EditIcon,
  ExpandMore as ExpandMoreIcon,
  GitHub as GitHubIcon,
  Assignment as JiraIcon,
  Settings as SettingsIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  Save as SaveIcon,
  Refresh as RefreshIcon,
  Security as SecurityIcon,
  HelpOutline as HelpOutlineIcon,
  Lock as LockIcon,
} from '@mui/icons-material';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

const API_BASE_URL = '';

interface GitHubDefaults {
  githubToken: string;
  githubApiBaseUrl: string;
  checkpointOverlapDays: number;
}

interface JIRADefaults {
  jiraServer: string;
  userId: string;
  apiToken: string;
  maxResults: number;
  cutoffDate: string;
}

interface GitLabDefaults {
  gitlabToken: string;
  gitlabApiBaseUrl: string;
  checkpointOverlapDays: number;
}

interface ConfigData {
  github_defaults: GitHubDefaults;
  gitlab_defaults: GitLabDefaults;
  jira_defaults: JIRADefaults;
  github_repositories: string[];
  gitlab_repositories: string[];
  gitlab_repo_team_mapping: Record<string, string>;
  jira_projects: string[];
  jira_prefix_team_mapping: Record<string, string>;
}

// --- Security Scan types ---
const SCAN_REPORT_TYPES = ['sast', 'sca', 'dast', 'mend'] as const;
type ScanReportType = typeof SCAN_REPORT_TYPES[number];

interface ScanReportEntry {
  type: ScanReportType;
  url: string;
  filename: string;
}

interface ScanProjectConfig {
  id: string;
  name: string;
  teams: string[];
  reports: ScanReportEntry[];
}

interface ScanConfig {
  credentials: { username: string; password: string };
  nexus_domains: Record<string, string>;
  projects: ScanProjectConfig[];
}

interface CopilotDBConfig {
  server: string;
  port: number;
  database: string;
  user: string;
  password: string;
  authentication: string;
  encrypt: boolean;
  trustServerCertificate: boolean;
  hostNameInCertificate?: string;
  loginTimeout: number;
}

const ProjectOnboardingPage: React.FC = () => {
  const { user } = useAuth();
  const isReadOnly = user?.role === 'Admin Viewer';
  const readOnlyMessage = 'Read-only access: Admin Viewer users cannot modify project onboarding configuration';
  const [loading, setLoading] = useState(false);
  const [configData, setConfigData] = useState<ConfigData | null>(null);
  const [githubRepos, setGithubRepos] = useState<string[]>([]);
  const [gitlabRepos, setGitlabRepos] = useState<string[]>([]);
  const [jiraProjects, setJiraProjects] = useState<string[]>([]);
  const [gitlabRepoTeamMapping, setGitlabRepoTeamMapping] = useState<Record<string, string>>({});
  const [existingGitlabRepos, setExistingGitlabRepos] = useState<string[]>([]);
  const [jiraPrefixTeamMapping, setJiraPrefixTeamMapping] = useState<Record<string, string>>({});
  const [newRepo, setNewRepo] = useState('');
  const [newGitLabRepo, setNewGitLabRepo] = useState('');
  const [newGitLabRepoTeam, setNewGitLabRepoTeam] = useState('');
  const [newProject, setNewProject] = useState('');
  const [newProjectTeam, setNewProjectTeam] = useState('');
  
  // Custom configuration state
  const [useCustomGitHub, setUseCustomGitHub] = useState(false);
  const [useCustomGitLab, setUseCustomGitLab] = useState(false);
  const [useCustomJIRA, setUseCustomJIRA] = useState(false);
  const [customGitHub, setCustomGitHub] = useState<GitHubDefaults>({
    githubToken: '',
    githubApiBaseUrl: '',
    checkpointOverlapDays: 15,
  });
  const [customGitLab, setCustomGitLab] = useState<GitLabDefaults>({
    gitlabToken: '',
    gitlabApiBaseUrl: '',
    checkpointOverlapDays: 15,
  });
  const [customJIRA, setCustomJIRA] = useState<JIRADefaults>({
    jiraServer: '',
    userId: '',
    apiToken: '',
    maxResults: 50,
    cutoffDate: '2025-03-31',
  });

  // UI state
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' as 'success' | 'error' | 'info' });
  const [showGitHubToken, setShowGitHubToken] = useState(false);
  const [showGitLabToken, setShowGitLabToken] = useState(false);
  const [showJIRAToken, setShowJIRAToken] = useState(false);
  const [editingGitHubCustom, setEditingGitHubCustom] = useState(false);
  const [editingGitLabCustom, setEditingGitLabCustom] = useState(false);
  const [editingJIRACustom, setEditingJIRACustom] = useState(false);
  const [githubOverlapDays, setGithubOverlapDays] = useState<number>(15);
  const [overlapDays, setOverlapDays] = useState<number>(15);
  const [newGitHubToken, setNewGitHubToken] = useState('');
  const [newGitLabToken, setNewGitLabToken] = useState('');
  const [newJIRAToken, setNewJIRAToken] = useState('');
  const [configDialog, setConfigDialog] = useState<'github' | 'gitlab' | 'jira' | 'scan' | null>(null);

  // Scan state
  const [scanConfig, setScanConfig] = useState<ScanConfig | null>(null);
  const [availableTeams, setAvailableTeams] = useState<string[]>([]);
  const [editingScanProject, setEditingScanProject] = useState<string | null>(null);
  const [newScanId, setNewScanId] = useState('');
  const [newScanName, setNewScanName] = useState('');
  const [newScanTeams, setNewScanTeams] = useState<string[]>([]);
  const [newScanUrls, setNewScanUrls] = useState<Record<ScanReportType, string>>({ sast: '', sca: '', dast: '', mend: '' });
  const [scanLoading, setScanLoading] = useState(false);

  // Copilot Metrics state
  const [copilotConfig, setCopilotConfig] = useState<CopilotDBConfig | null>(null);
  const [copilotEditing, setCopilotEditing] = useState(false);
  const [copilotEditValues, setCopilotEditValues] = useState<CopilotDBConfig | null>(null);
  const [copilotLoading, setCopilotLoading] = useState(false);
  const [showCopilotPassword, setShowCopilotPassword] = useState(false);
  const [copilotTestResult, setCopilotTestResult] = useState<{ success: boolean; status: string; message: string; output?: string } | null>(null);
  const [copilotTestOpen, setCopilotTestOpen] = useState(false);
  const [copilotProjectOptions, setCopilotProjectOptions] = useState<string[]>([]);
  const [copilotSelectedProjects, setCopilotSelectedProjects] = useState<string[]>([]);
  const [copilotProjectsLoading, setCopilotProjectsLoading] = useState(false);

  // UDE Config state
  const [udeVersions, setUdeVersions] = useState<{ version: string; release_date: string }[]>([]);
  const [udeVersionTeamMapping, setUdeVersionTeamMapping] = useState<Record<string, string[]>>({});
  const [udeConfigLoading, setUdeConfigLoading] = useState(false);

  useEffect(() => {
    fetchDefaultConfig();
    fetchScanConfig();
    fetchCopilotConfig();
    fetchCopilotProjectOptions();
    fetchCopilotProjects();
    fetchTeams();
    fetchUdeConfig();
  }, []);

  const fetchDefaultConfig = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/project-config/defaults`);
      setConfigData(response.data);
      setExistingGitlabRepos(response.data.gitlab_repositories || []);
      setGitlabRepos([]);
      setGitlabRepoTeamMapping({});
      // Set custom config to defaults initially
      const githubDefaults = response.data.github_defaults;
      setCustomGitHub({
        ...githubDefaults,
        checkpointOverlapDays: githubDefaults.checkpointOverlapDays ?? 15,
      });
      setGithubOverlapDays(githubDefaults.checkpointOverlapDays ?? 15);
      const gitlabDefaults = response.data.gitlab_defaults;
      setCustomGitLab({
        ...gitlabDefaults,
        checkpointOverlapDays: gitlabDefaults.checkpointOverlapDays ?? 15,
      });
      setOverlapDays(gitlabDefaults.checkpointOverlapDays ?? 15);
      setCustomJIRA(response.data.jira_defaults);
    } catch (error) {
      console.error('Error fetching default config:', error);
      showSnackbar('Failed to fetch default configuration', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveOverlapDays = async () => {
    try {
      await axios.put(`${API_BASE_URL}/api/project-config/gitlab/checkpoint-overlap`, {
        checkpointOverlapDays: overlapDays,
      });
      showSnackbar('GitLab fetch settings saved', 'success');
      setConfigData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          gitlab_defaults: {
            ...prev.gitlab_defaults,
            checkpointOverlapDays: overlapDays,
          },
        };
      });
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Failed to save GitLab fetch settings', 'error');
    }
  };

  const handleSaveGithubOverlapDays = async () => {
    try {
      await axios.put(`${API_BASE_URL}/api/project-config/github/checkpoint-overlap`, {
        checkpointOverlapDays: githubOverlapDays,
      });
      showSnackbar('GitHub fetch settings saved', 'success');
      setConfigData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          github_defaults: {
            ...prev.github_defaults,
            checkpointOverlapDays: githubOverlapDays,
          },
        };
      });
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Failed to save GitHub fetch settings', 'error');
    }
  };

  const fetchScanConfig = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/project-config/scan-config`);
      setScanConfig(response.data);
    } catch (error) {
      console.error('Error fetching scan config:', error);
    }
  };

  const fetchTeams = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/project-config/teams`);
      setAvailableTeams(response.data.teams || []);
    } catch (error) {
      console.error('Error fetching teams:', error);
    }
  };

  const fetchCopilotConfig = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/project-config/copilot-config`);
      const normalizedConfig = {
        ...response.data.database,
        authentication: response.data.database?.authentication || 'ActiveDirectoryPassword',
      } as CopilotDBConfig;
      setCopilotConfig(normalizedConfig);
      setCopilotEditValues(normalizedConfig);
    } catch (error) {
      console.error('Error fetching Copilot config:', error);
      showSnackbar('Failed to fetch Copilot metrics configuration', 'error');
    }
  };

  const fetchCopilotProjectOptions = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/project-config/copilot-project-options`);
      setCopilotProjectOptions(response.data.projects || []);
    } catch (error) {
      console.error('Error fetching Copilot project options:', error);
      showSnackbar('Failed to fetch Copilot project options', 'error');
    }
  };

  const fetchCopilotProjects = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/project-config/copilot-projects`);
      setCopilotSelectedProjects(response.data.projects || []);
    } catch (error) {
      console.error('Error fetching selected Copilot projects:', error);
      showSnackbar('Failed to fetch selected Copilot projects', 'error');
    }
  };

  const handleCopilotProjectsChange = (event: SelectChangeEvent<string[]>) => {
    const value = event.target.value;
    setCopilotSelectedProjects(typeof value === 'string' ? value.split(',') : value);
  };

  const handleCopilotProjectsSave = async () => {
    setCopilotProjectsLoading(true);
    try {
      const response = await axios.put(
        `${API_BASE_URL}/api/project-config/copilot-projects`,
        { projects: copilotSelectedProjects }
      );
      setCopilotSelectedProjects(response.data.projects || []);
      showSnackbar('Copilot projects updated successfully', 'success');
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Failed to update Copilot projects', 'error');
    } finally {
      setCopilotProjectsLoading(false);
    }
  };

  const handleCopilotEdit = () => {
    setCopilotEditing(true);
    if (copilotConfig) {
      setCopilotEditValues({ ...copilotConfig });
    }
  };

  const handleCopilotCancel = () => {
    setCopilotEditing(false);
    if (copilotConfig) {
      setCopilotEditValues({ ...copilotConfig });
    }
  };

  const handleCopilotSave = async () => {
    if (!copilotEditValues) return;

    setCopilotLoading(true);
    try {
      const response = await axios.put(
        `${API_BASE_URL}/api/project-config/copilot-config`,
        copilotEditValues
      );
      setCopilotConfig(response.data.database);
      setCopilotEditing(false);
      showSnackbar('Copilot metrics configuration updated successfully', 'success');
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Failed to update Copilot configuration', 'error');
    } finally {
      setCopilotLoading(false);
    }
  };

  const handleCopilotTest = async () => {
    if (!copilotEditValues) return;

    setCopilotLoading(true);
    try {
      const response = await axios.post(
        `${API_BASE_URL}/api/project-config/copilot-test`,
        copilotEditValues
      );
      setCopilotTestResult(response.data);
      setCopilotTestOpen(true);
    } catch (error: any) {
      const errorData = error.response?.data || { success: false, status: 'error', message: 'Failed to test connection' };
      setCopilotTestResult(errorData);
      setCopilotTestOpen(true);
    } finally {
      setCopilotLoading(false);
    }
  };

  const handleAddScanProject = async () => {
    const id = newScanId.trim().toLowerCase().replace(/\s+/g, '_');
    const name = newScanName.trim();
    if (!id || !name) {
      showSnackbar('Please enter a Project ID and Display Name', 'error');
      return;
    }
    const reports: ScanReportEntry[] = SCAN_REPORT_TYPES
      .filter(t => newScanUrls[t].trim())
      .map(t => ({
        type: t,
        url: newScanUrls[t].trim(),
        filename: `${id}_${t}${t === 'mend' ? '.pdf' : '.html'}`,
      }));
    if (reports.length === 0) {
      showSnackbar('Please provide at least one report URL', 'error');
      return;
    }
    setScanLoading(true);
    try {
      await axios.post(`${API_BASE_URL}/api/project-config/scan-projects`, { id, name, teams: newScanTeams, reports });
      showSnackbar(`Scan project '${name}' ${editingScanProject ? 'updated' : 'saved'}`, 'success');
      handleCancelEditScan();
      fetchScanConfig();
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Failed to save scan project', 'error');
    } finally {
      setScanLoading(false);
    }
  };

  const handleRemoveScanProject = async (projectId: string) => {
    setScanLoading(true);
    try {
      await axios.delete(`${API_BASE_URL}/api/project-config/scan-projects/${projectId}`);
      showSnackbar(`Scan project '${projectId}' removed`, 'success');
      if (editingScanProject === projectId) handleCancelEditScan();
      fetchScanConfig();
    } catch (error: any) {
      showSnackbar(error.response?.data?.detail || 'Failed to remove scan project', 'error');
    } finally {
      setScanLoading(false);
    }
  };

  const handleEditScanProject = (p: ScanProjectConfig) => {
    setEditingScanProject(p.id);
    setNewScanId(p.id);
    setNewScanName(p.name);
    setNewScanTeams(p.teams ?? []);
    const urls: Record<ScanReportType, string> = { sast: '', sca: '', dast: '', mend: '' };
    p.reports.forEach(r => { if (r.type in urls) urls[r.type as ScanReportType] = r.url; });
    setNewScanUrls(urls);
  };

  const handleCancelEditScan = () => {
    setEditingScanProject(null);
    setNewScanId('');
    setNewScanName('');
    setNewScanTeams([]);
    setNewScanUrls({ sast: '', sca: '', dast: '', mend: '' });
  };

  const showSnackbar = (message: string, severity: 'success' | 'error' | 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  const handleAddRepo = () => {
    const repoPattern = /^[\w-]+\/[\w-]+$/;
    if (!newRepo.trim()) {
      showSnackbar('Please enter a repository name', 'error');
      return;
    }
    if (!repoPattern.test(newRepo)) {
      showSnackbar('Invalid format. Use: owner/repo', 'error');
      return;
    }
    if (githubRepos.includes(newRepo)) {
      showSnackbar('Repository already added', 'error');
      return;
    }
    setGithubRepos([...githubRepos, newRepo]);
    setNewRepo('');
  };

  const handleRemoveRepo = (repo: string) => {
    setGithubRepos(githubRepos.filter(r => r !== repo));
  };

  const handleAddGitLabRepo = () => {
    const repoPattern = /^[\w.-]+(?:\/[\w.-]+)+$/;
    const repo = newGitLabRepo.trim();
    const team = newGitLabRepoTeam.trim();

    if (!repo) {
      showSnackbar('Please enter a GitLab repository name', 'error');
      return;
    }
    if (!team) {
      showSnackbar('Please enter team mapping for the GitLab repository', 'error');
      return;
    }
    if (!repoPattern.test(repo)) {
      showSnackbar('Invalid format. Use: group/repo or group/subgroup/repo', 'error');
      return;
    }
    if (gitlabRepos.includes(repo)) {
      showSnackbar('GitLab repository already added', 'error');
      return;
    }
    if (existingGitlabRepos.includes(repo)) {
      showSnackbar('GitLab repository is already configured', 'error');
      return;
    }

    setGitlabRepos([...gitlabRepos, repo]);
    setGitlabRepoTeamMapping((prev) => ({
      ...prev,
      [repo]: team,
    }));
    setNewGitLabRepo('');
    setNewGitLabRepoTeam('');
  };

  const handleRemoveGitLabRepo = (repo: string) => {
    setGitlabRepos(gitlabRepos.filter((r) => r !== repo));
    setGitlabRepoTeamMapping((prev) => {
      const next = { ...prev };
      delete next[repo];
      return next;
    });
  };

  const handleAddProject = () => {
    const projectPattern = /^[A-Z][A-Z0-9]*$/;
    if (!newProject.trim()) {
      showSnackbar('Please enter a JIRA project key', 'error');
      return;
    }
    if (!newProjectTeam.trim()) {
      showSnackbar('Please enter team mapping for the JIRA project key', 'error');
      return;
    }
    if (!projectPattern.test(newProject)) {
      showSnackbar('Invalid format. JIRA keys must start with uppercase letter', 'error');
      return;
    }
    if (jiraProjects.includes(newProject)) {
      showSnackbar('Project already added', 'error');
      return;
    }
    setJiraProjects([...jiraProjects, newProject]);
    setJiraPrefixTeamMapping((prev) => ({
      ...prev,
      [newProject]: newProjectTeam.trim(),
    }));
    setNewProject('');
    setNewProjectTeam('');
  };

  const handleRemoveProject = (project: string) => {
    setJiraProjects(jiraProjects.filter(p => p !== project));
    setJiraPrefixTeamMapping((prev) => {
      const next = { ...prev };
      delete next[project];
      return next;
    });
  };

  const handleOnboardProject = async () => {
    if (githubRepos.length === 0 && gitlabRepos.length === 0 && jiraProjects.length === 0) {
      showSnackbar('Please add at least one GitHub repository, GitLab repository, or JIRA project', 'error');
      return;
    }

    setLoading(true);
    try {
      const payload: any = {
        github_repos: githubRepos,
        gitlab_repos: gitlabRepos,
        gitlab_repo_team_mapping: gitlabRepoTeamMapping,
        jira_projects: jiraProjects,
        jira_prefix_team_mapping: jiraPrefixTeamMapping,
      };

      if (useCustomGitHub) {
        payload.github_custom_config = {
          ...customGitHub,
          githubToken: newGitHubToken.trim() ? newGitHubToken : customGitHub.githubToken,
        };
      }

      if (useCustomGitLab) {
        payload.gitlab_custom_config = {
          ...customGitLab,
          gitlabToken: newGitLabToken.trim() ? newGitLabToken : customGitLab.gitlabToken,
        };
      }

      if (useCustomJIRA) {
        payload.jira_custom_config = {
          ...customJIRA,
          apiToken: newJIRAToken.trim() ? newJIRAToken : customJIRA.apiToken,
        };
      }

      const response = await axios.post(`${API_BASE_URL}/api/project-config/onboard`, payload);
      
      showSnackbar(
        `Configuration updated! GitHub: ${response.data.github.added.length} added, GitLab: ${response.data.gitlab.added.length} added, JIRA: ${response.data.jira.added.length} added`,
        'success'
      );

      // Reset form
      setGithubRepos([]);
      setGitlabRepos([]);
      setJiraProjects([]);
      setGitlabRepoTeamMapping({});
      setJiraPrefixTeamMapping({});
      setUseCustomGitHub(false);
      setUseCustomGitLab(false);
      setUseCustomJIRA(false);
      setEditingGitHubCustom(false);
      setEditingGitLabCustom(false);
      setEditingJIRACustom(false);
      setNewGitHubToken('');
      setNewGitLabToken('');
      setNewJIRAToken('');

      // Refresh config data
      fetchDefaultConfig();
    } catch (error: any) {
      console.error('Error onboarding project:', error);
      const errorMsg = error.response?.data?.detail || 'Failed to onboard project';
      showSnackbar(errorMsg, 'error');
    } finally {
      setLoading(false);
    }
  };


  const fetchUdeConfig = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/project-config/ude-config`);
      setUdeVersions(response.data.available_versions || []);
      setUdeVersionTeamMapping(response.data.version_team_mapping || {});
    } catch (error) {
      console.error('Error fetching UDE config:', error);
    }
  };

  const handleUdeTeamChange = (version: string, teams: string[]) => {
    setUdeVersionTeamMapping(prev => ({ ...prev, [version]: teams }));
  };

  const handleSaveUdeConfig = async () => {
    setUdeConfigLoading(true);
    try {
      await axios.put(`${API_BASE_URL}/api/project-config/ude-config`, {
        version_team_mapping: udeVersionTeamMapping,
      });
      showSnackbar('UDE configuration saved successfully', 'success');
    } catch (error: any) {
      const msg = error.response?.data?.detail || 'Failed to save UDE configuration';
      showSnackbar(msg, 'error');
    } finally {
      setUdeConfigLoading(false);
    }
  };

  if (loading && !configData) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%' }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom>
          <SettingsIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          Project Onboarding & Configuration
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Configure GitHub repositories, GitLab repositories, and JIRA projects for your organization
        </Typography>
      </Box>

      {isReadOnly && (
        <Alert severity="info" icon={<LockIcon />} sx={{ mb: 2 }}>
          <strong>Read-Only Access:</strong> You can view project onboarding, Copilot, UDE, and scan configuration. Edit actions are disabled.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Current Configuration Overview */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">Current Configuration</Typography>
                <Button
                  startIcon={<RefreshIcon />}
                  onClick={fetchDefaultConfig}
                  disabled={loading}
                  size="small"
                >
                  Refresh
                </Button>
              </Box>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={3}>
                  <Box display="flex" alignItems="center" mb={1}>
                    <GitHubIcon sx={{ mr: 1 }} />
                    <Typography variant="subtitle2">
                      GitHub Repositories: {configData?.github_repositories.length || 0}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    onClick={() => setConfigDialog('github')}
                    startIcon={<VisibilityIcon />}
                  >
                    View All
                  </Button>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box display="flex" alignItems="center" mb={1}>
                    <GitHubIcon sx={{ mr: 1 }} />
                    <Typography variant="subtitle2">
                      GitLab Repositories: {configData?.gitlab_repositories.length || 0}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    onClick={() => setConfigDialog('gitlab')}
                    startIcon={<VisibilityIcon />}
                  >
                    View All
                  </Button>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box display="flex" alignItems="center" mb={1}>
                    <JiraIcon sx={{ mr: 1 }} />
                    <Typography variant="subtitle2">
                      JIRA Projects: {configData?.jira_projects.length || 0}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    onClick={() => setConfigDialog('jira')}
                    startIcon={<VisibilityIcon />}
                  >
                    View All
                  </Button>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box display="flex" alignItems="center" mb={1}>
                    <SecurityIcon sx={{ mr: 1 }} />
                    <Typography variant="subtitle2">
                      Scan Projects: {scanConfig?.projects.length || 0}
                    </Typography>
                  </Box>
                  <Button
                    size="small"
                    onClick={() => setConfigDialog('scan')}
                    startIcon={<VisibilityIcon />}
                  >
                    View All
                  </Button>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Onboard New Project */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Onboard New Project
              </Typography>

              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle1" gutterBottom>
                  SCM Fetch Settings
                </Typography>
                <Box display="flex" flexDirection="column" gap={2}>
                  <Box display="flex" alignItems="flex-start" gap={2} flexWrap="wrap">
                    <TextField
                      size="small"
                      label="GitHub Checkpoint Overlap Days"
                      type="number"
                      value={githubOverlapDays}
                      onChange={(e) => setGithubOverlapDays(Math.max(0, parseInt(e.target.value) || 0))}
                      helperText="GitHub fetch lookback window for late-pushed commits"
                      inputProps={{ min: 0, max: 90 }}
                      sx={{ width: 280 }}
                    />
                    <Button
                      size="small"
                      variant="contained"
                      onClick={handleSaveGithubOverlapDays}
                      disabled={isReadOnly}
                      title={isReadOnly ? readOnlyMessage : ''}
                      sx={{ mt: 1 }}
                    >
                      Save GitHub
                    </Button>
                  </Box>

                  <Box display="flex" alignItems="flex-start" gap={2} flexWrap="wrap">
                    <TextField
                      size="small"
                      label="GitLab Checkpoint Overlap Days"
                      type="number"
                      value={overlapDays}
                      onChange={(e) => setOverlapDays(Math.max(0, parseInt(e.target.value) || 0))}
                      helperText="GitLab fetch lookback window for late-pushed commits"
                      inputProps={{ min: 0, max: 90 }}
                      sx={{ width: 280 }}
                    />
                    <Button
                      size="small"
                      variant="contained"
                      onClick={handleSaveOverlapDays}
                      disabled={isReadOnly}
                      title={isReadOnly ? readOnlyMessage : ''}
                      sx={{ mt: 1 }}
                    >
                      Save GitLab
                    </Button>
                  </Box>
                </Box>
              </Box>

              {/* GitHub Repositories Section */}
              <Accordion defaultExpanded>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box display="flex" alignItems="center">
                    <GitHubIcon sx={{ mr: 1 }} />
                    <Typography>GitHub Repositories</Typography>
                    <Chip label={githubRepos.length} size="small" sx={{ ml: 2 }} />
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  <Box>
                    <Box display="flex" gap={1} mb={2}>
                      <TextField
                        fullWidth
                        size="small"
                        label="Repository (owner/repo)"
                        value={newRepo}
                        onChange={(e) => setNewRepo(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleAddRepo()}
                        placeholder="e.g., SPARC-Development-Lab/aion-core"
                      />
                      <Button
                        variant="contained"
                        onClick={handleAddRepo}
                        startIcon={<AddIcon />}
                        disabled={isReadOnly}
                        title={isReadOnly ? readOnlyMessage : ''}
                      >
                        Add
                      </Button>
                    </Box>
                    
                    {githubRepos.length > 0 && (
                      <List dense>
                        {githubRepos.map((repo) => (
                          <ListItem key={repo}>
                            <ListItemText primary={repo} />
                            <ListItemSecondaryAction>
                              <IconButton
                                edge="end"
                                onClick={() => handleRemoveRepo(repo)}
                                size="small"
                                disabled={isReadOnly}
                              >
                                <DeleteIcon />
                              </IconButton>
                            </ListItemSecondaryAction>
                          </ListItem>
                        ))}
                      </List>
                    )}

                    <Divider sx={{ my: 2 }} />

                    {/* GitHub Custom Configuration */}
                    <Box>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                        <Typography variant="subtitle2" color="text.secondary">
                          Custom GitHub Configuration (Optional)
                        </Typography>
                        <Box display="flex" gap={1}>
                          {useCustomGitHub && !editingGitHubCustom && (
                            <Button
                              size="small"
                              startIcon={<EditIcon />}
                              onClick={() => {
                                setEditingGitHubCustom(true);
                                setNewGitHubToken('');
                                setShowGitHubToken(false);
                              }}
                              disabled={isReadOnly}
                              title={isReadOnly ? readOnlyMessage : ''}
                            >
                              Edit
                            </Button>
                          )}
                          <Button
                            size="small"
                            variant={useCustomGitHub ? 'outlined' : 'text'}
                            onClick={() => {
                              setUseCustomGitHub(!useCustomGitHub);
                              setEditingGitHubCustom(false);
                              setShowGitHubToken(false);
                              setNewGitHubToken('');
                              if (!useCustomGitHub && configData) {
                                setCustomGitHub(configData.github_defaults);
                              }
                            }}
                            disabled={isReadOnly}
                            title={isReadOnly ? readOnlyMessage : ''}
                          >
                            {useCustomGitHub ? 'Use Default' : 'Customize'}
                          </Button>
                        </Box>
                      </Box>
                      
                      {useCustomGitHub && !editingGitHubCustom ? (
                        <Box sx={{ backgroundColor: '#f5f5f5', p: 2, borderRadius: 1, mb: 2 }}>
                          <TextField
                            fullWidth
                            size="small"
                            label="API Base URL"
                            value={customGitHub.githubApiBaseUrl}
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="GitHub Token"
                            value="[REDACTED]"
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            type="password"
                          />
                          <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary' }}>
                            Token is hidden for security. Click Edit to view or modify.
                          </Typography>
                        </Box>
                      ) : useCustomGitHub && editingGitHubCustom ? (
                        <Box>
                          <TextField
                            fullWidth
                            size="small"
                            label="API Base URL"
                            value={customGitHub.githubApiBaseUrl}
                            onChange={(e) => setCustomGitHub({ ...customGitHub, githubApiBaseUrl: e.target.value })}
                            sx={{ mb: 2 }}
                          />
                          <FormControl fullWidth size="small" variant="outlined">
                            <InputLabel>New GitHub Token (optional)</InputLabel>
                            <OutlinedInput
                              type={showGitHubToken ? 'text' : 'password'}
                              value={newGitHubToken}
                              onChange={(e) => setNewGitHubToken(e.target.value)}
                              placeholder="Enter new token to replace existing"
                              endAdornment={
                                <InputAdornment position="end">
                                  <IconButton
                                    onClick={() => setShowGitHubToken(!showGitHubToken)}
                                    edge="end"
                                  >
                                    {showGitHubToken ? <VisibilityOffIcon /> : <VisibilityIcon />}
                                  </IconButton>
                                </InputAdornment>
                              }
                              label="New GitHub Token (optional)"
                            />
                          </FormControl>
                          <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary' }}>
                            Existing token is hidden and cannot be viewed. Enter a new token only if you want to replace it.
                          </Typography>
                          <Box display="flex" justifyContent="flex-end" gap={1} mt={2}>
                            <Button
                              size="small"
                              variant="text"
                              onClick={() => {
                                setEditingGitHubCustom(false);
                                setShowGitHubToken(false);
                                setNewGitHubToken('');
                              }}
                            >
                              Done
                            </Button>
                          </Box>
                        </Box>
                      ) : (
                        <Alert severity="info" sx={{ fontSize: '0.875rem' }}>
                          Using default GitHub configuration
                        </Alert>
                      )}
                    </Box>
                  </Box>
                </AccordionDetails>
              </Accordion>

              {/* GitLab Repositories Section */}
              <Accordion defaultExpanded sx={{ mt: 2 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box display="flex" alignItems="center">
                    <GitHubIcon sx={{ mr: 1 }} />
                    <Typography>GitLab Repositories to Add</Typography>
                    <Chip label={gitlabRepos.length} size="small" sx={{ ml: 2 }} />
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  <Box>
                    <Box display="flex" gap={1} mb={2}>
                      <TextField
                        sx={{ flex: 1 }}
                        size="small"
                        label="Repository (group/repo or group/subgroup/repo)"
                        value={newGitLabRepo}
                        onChange={(e) => setNewGitLabRepo(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleAddGitLabRepo()}
                        placeholder="e.g., Xhaul/RTL/F2B_topcom"
                      />
                      <TextField
                        sx={{ flex: 1 }}
                        size="small"
                        label="Mapped Team"
                        value={newGitLabRepoTeam}
                        onChange={(e) => setNewGitLabRepoTeam(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleAddGitLabRepo()}
                        placeholder="e.g., XHAUL"
                      />
                      <Button
                        variant="contained"
                        onClick={handleAddGitLabRepo}
                        startIcon={<AddIcon />}
                        disabled={isReadOnly}
                        title={isReadOnly ? readOnlyMessage : ''}
                      >
                        Add
                      </Button>
                    </Box>

                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                      Already configured GitLab repos are not shown here. Currently configured: {existingGitlabRepos.length}
                    </Typography>

                    {gitlabRepos.length > 0 && (
                      <List dense>
                        {gitlabRepos.map((repo) => (
                          <ListItem key={repo}>
                            <ListItemText
                              primary={repo}
                              secondary={`Team: ${gitlabRepoTeamMapping[repo] || '-'}`}
                            />
                            <ListItemSecondaryAction>
                              <IconButton
                                edge="end"
                                onClick={() => handleRemoveGitLabRepo(repo)}
                                size="small"
                                disabled={isReadOnly}
                              >
                                <DeleteIcon />
                              </IconButton>
                            </ListItemSecondaryAction>
                          </ListItem>
                        ))}
                      </List>
                    )}

                    <Divider sx={{ my: 2 }} />

                    <Box>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                        <Typography variant="subtitle2" color="text.secondary">
                          Custom GitLab Configuration (Optional)
                        </Typography>
                        <Box display="flex" gap={1}>
                          {useCustomGitLab && !editingGitLabCustom && (
                            <Button
                              size="small"
                              startIcon={<EditIcon />}
                              onClick={() => {
                                setEditingGitLabCustom(true);
                                setNewGitLabToken('');
                                setShowGitLabToken(false);
                              }}
                              disabled={isReadOnly}
                              title={isReadOnly ? readOnlyMessage : ''}
                            >
                              Edit
                            </Button>
                          )}
                          <Button
                            size="small"
                            variant={useCustomGitLab ? 'outlined' : 'text'}
                            onClick={() => {
                              setUseCustomGitLab(!useCustomGitLab);
                              setEditingGitLabCustom(false);
                              setShowGitLabToken(false);
                              setNewGitLabToken('');
                              if (!useCustomGitLab && configData) {
                                setCustomGitLab({
                                  ...configData.gitlab_defaults,
                                  checkpointOverlapDays: configData.gitlab_defaults.checkpointOverlapDays ?? 15,
                                });
                              }
                            }}
                            disabled={isReadOnly}
                            title={isReadOnly ? readOnlyMessage : ''}
                          >
                            {useCustomGitLab ? 'Use Default' : 'Customize'}
                          </Button>
                        </Box>
                      </Box>

                      {useCustomGitLab && !editingGitLabCustom ? (
                        <Box sx={{ backgroundColor: '#f5f5f5', p: 2, borderRadius: 1, mb: 2 }}>
                          <TextField
                            fullWidth
                            size="small"
                            label="API Base URL"
                            value={customGitLab.gitlabApiBaseUrl}
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="GitLab Token"
                            value="[REDACTED]"
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            type="password"
                          />
                          <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary' }}>
                            Token is hidden for security. Click Edit to view or modify.
                          </Typography>
                        </Box>
                      ) : useCustomGitLab && editingGitLabCustom ? (
                        <Box>
                          <TextField
                            fullWidth
                            size="small"
                            label="API Base URL"
                            value={customGitLab.gitlabApiBaseUrl}
                            onChange={(e) => setCustomGitLab({ ...customGitLab, gitlabApiBaseUrl: e.target.value })}
                            sx={{ mb: 2 }}
                          />
                          <FormControl fullWidth size="small" variant="outlined">
                            <InputLabel>New GitLab Token (optional)</InputLabel>
                            <OutlinedInput
                              type={showGitLabToken ? 'text' : 'password'}
                              value={newGitLabToken}
                              onChange={(e) => setNewGitLabToken(e.target.value)}
                              placeholder="Enter new token to replace existing"
                              endAdornment={
                                <InputAdornment position="end">
                                  <IconButton
                                    onClick={() => setShowGitLabToken(!showGitLabToken)}
                                    edge="end"
                                  >
                                    {showGitLabToken ? <VisibilityOffIcon /> : <VisibilityIcon />}
                                  </IconButton>
                                </InputAdornment>
                              }
                              label="New GitLab Token (optional)"
                            />
                          </FormControl>
                          <Typography variant="caption" sx={{ mt: 1, display: 'block', color: 'text.secondary' }}>
                            Existing token is hidden and cannot be viewed. Enter a new token only if you want to replace it.
                          </Typography>
                          <Box display="flex" justifyContent="flex-end" gap={1} mt={2}>
                            <Button
                              size="small"
                              variant="text"
                              onClick={() => {
                                setEditingGitLabCustom(false);
                                setShowGitLabToken(false);
                                setNewGitLabToken('');
                              }}
                            >
                              Done
                            </Button>
                          </Box>
                        </Box>
                      ) : (
                        <Alert severity="info" sx={{ fontSize: '0.875rem' }}>
                          Using default GitLab configuration
                        </Alert>
                      )}
                    </Box>
                  </Box>
                </AccordionDetails>
              </Accordion>

              {/* JIRA Projects Section */}
              <Accordion defaultExpanded sx={{ mt: 2 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box display="flex" alignItems="center">
                    <JiraIcon sx={{ mr: 1 }} />
                    <Typography>JIRA Projects</Typography>
                    <Chip label={jiraProjects.length} size="small" sx={{ ml: 2 }} />
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  <Box>
                    <Box display="flex" gap={1} mb={2}>
                      <TextField
                        sx={{ flex: 1 }}
                        size="small"
                        label="Project Key"
                        value={newProject}
                        onChange={(e) => setNewProject(e.target.value.toUpperCase())}
                        onKeyPress={(e) => e.key === 'Enter' && handleAddProject()}
                        placeholder="e.g., AS, PCS, DES"
                      />
                      <TextField
                        sx={{ flex: 1 }}
                        size="small"
                        label="Mapped Team"
                        value={newProjectTeam}
                        onChange={(e) => setNewProjectTeam(e.target.value)}
                        onKeyPress={(e) => e.key === 'Enter' && handleAddProject()}
                        placeholder="e.g., HCL AION, FSO, OOSM"
                      />
                      <Button
                        variant="contained"
                        onClick={handleAddProject}
                        startIcon={<AddIcon />}
                        disabled={isReadOnly}
                        title={isReadOnly ? readOnlyMessage : ''}
                      >
                        Add
                      </Button>
                    </Box>
                    
                    {jiraProjects.length > 0 && (
                      <List dense>
                        {jiraProjects.map((project) => (
                          <ListItem key={project}>
                            <ListItemText
                              primary={project}
                              secondary={`Team: ${jiraPrefixTeamMapping[project] || '-'}`}
                            />
                            <ListItemSecondaryAction>
                              <IconButton
                                edge="end"
                                onClick={() => handleRemoveProject(project)}
                                size="small"
                                disabled={isReadOnly}
                              >
                                <DeleteIcon />
                              </IconButton>
                            </ListItemSecondaryAction>
                          </ListItem>
                        ))}
                      </List>
                    )}

                    <Box sx={{ borderTop: 1, borderColor: 'divider', my: 2 }} />

                    {/* JIRA Custom Configuration */}
                    <Box>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                        <Typography variant="subtitle2" color="text.secondary">
                          Custom JIRA Configuration (Optional)
                        </Typography>
                        <Box display="flex" gap={1}>
                          {useCustomJIRA && !editingJIRACustom && (
                            <Button
                              size="small"
                              startIcon={<EditIcon />}
                              onClick={() => {
                                setEditingJIRACustom(true);
                                setNewJIRAToken('');
                                setShowJIRAToken(false);
                              }}
                              disabled={isReadOnly}
                              title={isReadOnly ? readOnlyMessage : ''}
                            >
                              Edit
                            </Button>
                          )}
                          <Button
                            size="small"
                            variant={useCustomJIRA ? 'outlined' : 'text'}
                            onClick={() => {
                              setUseCustomJIRA(!useCustomJIRA);
                              setEditingJIRACustom(false);
                              setShowJIRAToken(false);
                              setNewJIRAToken('');
                              if (!useCustomJIRA && configData) {
                                setCustomJIRA(configData.jira_defaults);
                              }
                            }}
                            disabled={isReadOnly}
                            title={isReadOnly ? readOnlyMessage : ''}
                          >
                            {useCustomJIRA ? 'Use Default' : 'Customize'}
                          </Button>
                        </Box>
                      </Box>
                      
                      {useCustomJIRA && !editingJIRACustom ? (
                        <Box sx={{ backgroundColor: '#f5f5f5', p: 2, borderRadius: 1, mb: 2 }}>
                          <TextField
                            fullWidth
                            size="small"
                            label="JIRA Server"
                            value={customJIRA.jiraServer}
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="User ID (Email)"
                            value={customJIRA.userId}
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="API Token"
                            value="[REDACTED]"
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            type="password"
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="Max Results"
                            value={customJIRA.maxResults}
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="Cutoff Date"
                            value={customJIRA.cutoffDate}
                            InputProps={{ readOnly: true }}
                            variant="outlined"
                          />
                          <Typography variant="caption" sx={{ mt: 2, display: 'block', color: 'text.secondary' }}>
                            API Token is hidden for security. Click Edit to view or modify.
                          </Typography>
                        </Box>
                      ) : useCustomJIRA && editingJIRACustom ? (
                        <Box>
                          <TextField
                            fullWidth
                            size="small"
                            label="JIRA Server"
                            value={customJIRA.jiraServer}
                            onChange={(e) => setCustomJIRA({ ...customJIRA, jiraServer: e.target.value })}
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="User ID (Email)"
                            value={customJIRA.userId}
                            onChange={(e) => setCustomJIRA({ ...customJIRA, userId: e.target.value })}
                            sx={{ mb: 2 }}
                          />
                          <FormControl fullWidth size="small" variant="outlined" sx={{ mb: 2 }}>
                            <InputLabel>New API Token (optional)</InputLabel>
                            <OutlinedInput
                              type={showJIRAToken ? 'text' : 'password'}
                              value={newJIRAToken}
                              onChange={(e) => setNewJIRAToken(e.target.value)}
                              placeholder="Enter new token to replace existing"
                              endAdornment={
                                <InputAdornment position="end">
                                  <IconButton
                                    onClick={() => setShowJIRAToken(!showJIRAToken)}
                                    edge="end"
                                  >
                                    {showJIRAToken ? <VisibilityOffIcon /> : <VisibilityIcon />}
                                  </IconButton>
                                </InputAdornment>
                              }
                              label="New API Token (optional)"
                            />
                          </FormControl>
                          <Typography variant="caption" sx={{ mt: -1, mb: 2, display: 'block', color: 'text.secondary' }}>
                            Existing API token is hidden and cannot be viewed. Enter a new token only if you want to replace it.
                          </Typography>
                          <TextField
                            fullWidth
                            size="small"
                            type="number"
                            label="Max Results"
                            value={customJIRA.maxResults}
                            onChange={(e) => setCustomJIRA({ ...customJIRA, maxResults: parseInt(e.target.value) || 50 })}
                            sx={{ mb: 2 }}
                          />
                          <TextField
                            fullWidth
                            size="small"
                            label="Cutoff Date"
                            value={customJIRA.cutoffDate}
                            onChange={(e) => setCustomJIRA({ ...customJIRA, cutoffDate: e.target.value })}
                            sx={{ mb: 2 }}
                          />
                          <Box display="flex" justifyContent="flex-end" gap={1}>
                            <Button
                              size="small"
                              variant="text"
                              onClick={() => {
                                setEditingJIRACustom(false);
                                setShowJIRAToken(false);
                                setNewJIRAToken('');
                              }}
                            >
                              Done
                            </Button>
                          </Box>
                        </Box>
                      ) : (
                        <Alert severity="info" sx={{ fontSize: '0.875rem' }}>
                          Using default JIRA configuration
                        </Alert>
                      )}
                    </Box>
                  </Box>
                </AccordionDetails>
              </Accordion>

              {/* Security Scan Reports Section */}
              <Accordion sx={{ mt: 2 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box display="flex" alignItems="center">
                    <SecurityIcon sx={{ mr: 1 }} />
                    <Typography>Security Scan Reports (Nexus)</Typography>
                    <Chip label={scanConfig?.projects.length || 0} size="small" sx={{ ml: 2 }} />
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  <Box>
                    {/* Existing scan projects */}
                    {(scanConfig?.projects.length ?? 0) > 0 && (
                      <Box mb={2}>
                        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                          Configured projects
                        </Typography>
                        <List dense disablePadding>
                          {scanConfig!.projects.map((p) => (
                            <ListItem key={p.id} disableGutters>
                              <ListItemText
                                primary={
                                  <Box display="flex" alignItems="center" gap={1}>
                                    <span>{p.name}</span>
                                    {(p.teams ?? []).map(t => (
                                      <Chip key={t} label={t} size="small" color="info" variant="outlined" />
                                    ))}
                                  </Box>
                                }
                                secondary={
                                  <Box component="span" display="flex" flexWrap="wrap" gap={0.5} mt={0.25}>
                                    {p.reports.map(r => (
                                      <Chip
                                        key={r.type}
                                        label={r.type.toUpperCase()}
                                        size="small"
                                        variant="outlined"
                                        color={
                                          r.type === 'sast' ? 'primary' :
                                          r.type === 'sca'  ? 'success' :
                                          r.type === 'dast' ? 'warning' : 'secondary'
                                        }
                                      />
                                    ))}
                                  </Box>
                                }
                              />
                            <ListItemSecondaryAction>
                                <IconButton
                                  size="small"
                                  disabled={scanLoading || isReadOnly}
                                  onClick={() => handleEditScanProject(p)}
                                  sx={{ mr: 0.5 }}
                                >
                                  <EditIcon fontSize="small" />
                                </IconButton>
                                <IconButton
                                  edge="end"
                                  size="small"
                                  disabled={scanLoading || isReadOnly}
                                  onClick={() => handleRemoveScanProject(p.id)}
                                >
                                  <DeleteIcon fontSize="small" />
                                </IconButton>
                              </ListItemSecondaryAction>
                            </ListItem>
                          ))}
                        </List>
                        <Divider sx={{ my: 2 }} />
                      </Box>
                    )}

                    {/* Add / Edit scan project form */}
                    <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                      {editingScanProject ? `Editing: ${editingScanProject}` : 'Add project'}
                    </Typography>
                    <Box display="flex" gap={1} mb={1}>
                      <TextField
                        size="small"
                        label="Project ID"
                        placeholder="e.g. myapp"
                        value={newScanId}
                        onChange={(e) => !editingScanProject && setNewScanId(e.target.value.toLowerCase().replace(/\s+/g, '_'))}
                        disabled={!!editingScanProject}
                        sx={{ flex: 1 }}
                        helperText={editingScanProject ? 'ID cannot be changed' : 'Short id used for filenames'}
                      />
                      <TextField
                        size="small"
                        label="Display Name"
                        placeholder="e.g. My App"
                        value={newScanName}
                        onChange={(e) => setNewScanName(e.target.value)}
                        sx={{ flex: 1 }}
                      />
                      <FormControl size="small" sx={{ flex: 1 }}>
                        <InputLabel>Teams</InputLabel>
                        <Select
                          multiple
                          value={newScanTeams}
                          label="Teams"
                          onChange={(e) => setNewScanTeams(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value as string[])}
                          renderValue={(selected) => (
                            <Box display="flex" flexWrap="wrap" gap={0.5}>
                              {(selected as string[]).map(t => <Chip key={t} label={t} size="small" />)}
                            </Box>
                          )}
                        >
                          {availableTeams.map(t => (
                            <MenuItem key={t} value={t}>{t}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Box>
                    {SCAN_REPORT_TYPES.map(rt => (
                      <TextField
                        key={rt}
                        fullWidth
                        size="small"
                        label={`${rt.toUpperCase()} URL`}
                        placeholder={`https://nexus.example.com/repository/…/${rt === 'mend' ? 'report.pdf' : `${rt}.html`}`}
                        value={newScanUrls[rt]}
                        onChange={(e) => setNewScanUrls(prev => ({ ...prev, [rt]: e.target.value }))}
                        sx={{ mb: 1 }}
                      />
                    ))}
                    <Box display="flex" justifyContent="flex-end" gap={1} mt={1}>
                      {editingScanProject && (
                        <Button variant="text" onClick={handleCancelEditScan} disabled={scanLoading}>
                          Cancel
                        </Button>
                      )}
                      <Button
                        variant="outlined"
                        onClick={handleAddScanProject}
                        disabled={scanLoading || isReadOnly}
                        title={isReadOnly ? readOnlyMessage : ''}
                        startIcon={scanLoading ? <CircularProgress size={16} /> : editingScanProject ? <SaveIcon /> : <AddIcon />}
                      >
                        {editingScanProject ? 'Update Scan Project' : 'Add Scan Project'}
                      </Button>
                    </Box>
                  </Box>
                </AccordionDetails>
              </Accordion>

              <Box mt={3} display="flex" justifyContent="flex-end">
                <Button
                  variant="contained"
                  size="large"
                  onClick={handleOnboardProject}
                  disabled={isReadOnly || loading || (githubRepos.length === 0 && gitlabRepos.length === 0 && jiraProjects.length === 0)}
                  title={isReadOnly ? readOnlyMessage : ''}
                  startIcon={loading ? <CircularProgress size={20} /> : <SaveIcon />}
                >
                  {loading ? 'Onboarding...' : 'Onboard Project'}
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Copilot Metrics Configuration */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">
                  <SecurityIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                  Copilot Usage Metrics - Database Configuration
                </Typography>
                {!copilotEditing && (
                  <Button
                    startIcon={<EditIcon />}
                    onClick={handleCopilotEdit}
                    size="small"
                    disabled={copilotLoading || isReadOnly}
                    title={isReadOnly ? readOnlyMessage : ''}
                  >
                    Edit
                  </Button>
                )}
              </Box>

              {copilotConfig && !copilotEditing && (
                <Box>
                  <Box display="grid" gridTemplateColumns="repeat(auto-fit, minmax(250px, 1fr))" gap={2} mb={2}>
                    <TextField
                      label="Server"
                      value={copilotConfig.server}
                      InputProps={{ readOnly: true }}
                      size="small"
                      variant="outlined"
                    />
                    <TextField
                      label="Port"
                      value={copilotConfig.port}
                      InputProps={{ readOnly: true }}
                      size="small"
                      variant="outlined"
                    />
                    <TextField
                      label="Database"
                      value={copilotConfig.database}
                      InputProps={{ readOnly: true }}
                      size="small"
                      variant="outlined"
                    />
                    <TextField
                      label="User"
                      value={copilotConfig.user}
                      InputProps={{ readOnly: true }}
                      size="small"
                      variant="outlined"
                    />
                    <TextField
                      label="Authentication"
                      value={copilotConfig.authentication || 'ActiveDirectoryPassword'}
                      InputProps={{ readOnly: true }}
                      size="small"
                      variant="outlined"
                    />
                    <TextField
                      label="Encryption"
                      value={copilotConfig.encrypt ? 'Enabled' : 'Disabled'}
                      InputProps={{ readOnly: true }}
                      size="small"
                      variant="outlined"
                    />
                    <TextField
                      label="Login Timeout"
                      value={`${copilotConfig.loginTimeout}s`}
                      InputProps={{ readOnly: true }}
                      size="small"
                      variant="outlined"
                    />
                  </Box>
                  <Box display="flex" gap={1}>
                    <Button
                      variant="contained"
                      onClick={handleCopilotTest}
                      disabled={copilotLoading || isReadOnly}
                      title={isReadOnly ? readOnlyMessage : ''}
                      startIcon={copilotLoading ? <CircularProgress size={18} /> : <RefreshIcon />}
                    >
                      Test Connection
                    </Button>
                  </Box>
                </Box>
              )}

              {copilotEditValues && copilotEditing && (
                <Box>
                  <Box display="grid" gridTemplateColumns="repeat(auto-fit, minmax(250px, 1fr))" gap={2} mb={2}>
                    <TextField
                      label="Server"
                      value={copilotEditValues.server}
                      onChange={(e) => setCopilotEditValues({ ...copilotEditValues, server: e.target.value })}
                      size="small"
                      variant="outlined"
                      fullWidth
                    />
                    <TextField
                      label="Port"
                      type="number"
                      value={copilotEditValues.port}
                      onChange={(e) => setCopilotEditValues({ ...copilotEditValues, port: parseInt(e.target.value) || 1433 })}
                      size="small"
                      variant="outlined"
                      fullWidth
                    />
                    <TextField
                      label="Database"
                      value={copilotEditValues.database}
                      onChange={(e) => setCopilotEditValues({ ...copilotEditValues, database: e.target.value })}
                      size="small"
                      variant="outlined"
                      fullWidth
                    />
                    <TextField
                      label="User"
                      value={copilotEditValues.user}
                      onChange={(e) => setCopilotEditValues({ ...copilotEditValues, user: e.target.value })}
                      size="small"
                      variant="outlined"
                      fullWidth
                    />
                    <FormControl size="small" variant="outlined" fullWidth>
                      <InputLabel>
                        Authentication
                      </InputLabel>
                      <Select
                        value={copilotEditValues.authentication || 'ActiveDirectoryPassword'}
                        onChange={(e) => setCopilotEditValues({ ...copilotEditValues, authentication: e.target.value })}
                        label="Authentication"
                      >
                        <MenuItem value="ActiveDirectoryPassword">ActiveDirectoryPassword</MenuItem>
                        <MenuItem value="SqlPassword">SqlPassword</MenuItem>
                      </Select>
                    </FormControl>
                    <FormControl size="small" variant="outlined" fullWidth>
                      <InputLabel>Password</InputLabel>
                      <OutlinedInput
                        label="Password"
                        type={showCopilotPassword ? 'text' : 'password'}
                        value={copilotEditValues.password}
                        onChange={(e) => setCopilotEditValues({ ...copilotEditValues, password: e.target.value })}
                        endAdornment={
                          <InputAdornment position="end">
                            <IconButton
                              onClick={() => setShowCopilotPassword(!showCopilotPassword)}
                              edge="end"
                              size="small"
                            >
                              {showCopilotPassword ? <VisibilityOffIcon fontSize="small" /> : <VisibilityIcon fontSize="small" />}
                            </IconButton>
                          </InputAdornment>
                        }
                      />
                    </FormControl>
                    <TextField
                      label="Login Timeout (seconds)"
                      type="number"
                      value={copilotEditValues.loginTimeout}
                      onChange={(e) => setCopilotEditValues({ ...copilotEditValues, loginTimeout: parseInt(e.target.value) || 30 })}
                      size="small"
                      variant="outlined"
                      fullWidth
                    />
                  </Box>
                  <Box display="flex" gap={1} alignItems="center" mb={2}>
                    <Tooltip
                      title="Choose ActiveDirectoryPassword for Azure AD user IDs (user@tenant). Use SqlPassword only for SQL-auth logins created in SQL Server."
                      arrow
                    >
                      <Box display="flex" alignItems="center" sx={{ color: 'text.secondary', mr: 0.5 }}>
                        <HelpOutlineIcon fontSize="small" />
                      </Box>
                    </Tooltip>
                    <FormControl size="small" variant="outlined" fullWidth>
                      <InputLabel>SSL/TLS Encryption</InputLabel>
                      <Select
                        value={copilotEditValues.encrypt ? 'enabled' : 'disabled'}
                        onChange={(e) => setCopilotEditValues({ ...copilotEditValues, encrypt: e.target.value === 'enabled' })}
                        label="SSL/TLS Encryption"
                      >
                        <MenuItem value="enabled">Enabled</MenuItem>
                        <MenuItem value="disabled">Disabled</MenuItem>
                      </Select>
                    </FormControl>
                    <FormControl size="small" variant="outlined" fullWidth>
                      <InputLabel>Trust Server Certificate</InputLabel>
                      <Select
                        value={copilotEditValues.trustServerCertificate ? 'yes' : 'no'}
                        onChange={(e) => setCopilotEditValues({ ...copilotEditValues, trustServerCertificate: e.target.value === 'yes' })}
                        label="Trust Server Certificate"
                      >
                        <MenuItem value="no">No</MenuItem>
                        <MenuItem value="yes">Yes</MenuItem>
                      </Select>
                    </FormControl>
                    <TextField
                      label="Host Name in Certificate"
                      value={copilotEditValues.hostNameInCertificate || ''}
                      onChange={(e) => setCopilotEditValues({ ...copilotEditValues, hostNameInCertificate: e.target.value })}
                      size="small"
                      variant="outlined"
                      fullWidth
                    />
                  </Box>
                  <Box display="flex" justifyContent="flex-end" gap={1}>
                    <Button
                      variant="text"
                      onClick={handleCopilotCancel}
                      disabled={copilotLoading}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="contained"
                      onClick={handleCopilotTest}
                      disabled={copilotLoading || isReadOnly}
                      title={isReadOnly ? readOnlyMessage : ''}
                      startIcon={copilotLoading ? <CircularProgress size={18} /> : <RefreshIcon />}
                    >
                      Test Connection
                    </Button>
                    <Button
                      variant="contained"
                      onClick={handleCopilotSave}
                      disabled={copilotLoading || isReadOnly}
                      title={isReadOnly ? readOnlyMessage : ''}
                      startIcon={copilotLoading ? <CircularProgress size={18} /> : <SaveIcon />}
                    >
                      Save Configuration
                    </Button>
                  </Box>
                </Box>
              )}

              <Divider sx={{ my: 3 }} />

              <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                <Typography variant="h6">
                  <SettingsIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                  Copilot Metrics - Projects
                </Typography>
                <Button
                  startIcon={<RefreshIcon />}
                  onClick={() => {
                    fetchCopilotProjectOptions();
                    fetchCopilotProjects();
                  }}
                  size="small"
                  disabled={copilotProjectsLoading}
                >
                  Refresh
                </Button>
              </Box>

              <Box>
                <FormControl fullWidth size="small" variant="outlined" sx={{ mb: 2 }}>
                  <InputLabel id="copilot-projects-label">Select Projects (team_name)</InputLabel>
                  <Select
                    labelId="copilot-projects-label"
                    multiple
                    value={copilotSelectedProjects}
                    onChange={handleCopilotProjectsChange}
                    disabled={isReadOnly}
                    input={<OutlinedInput label="Select Projects (team_name)" />}
                    renderValue={(selected) => (selected as string[]).join(', ')}
                  >
                    {copilotProjectOptions.map((project) => (
                      <MenuItem key={project} value={project}>
                        {project}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <Box display="flex" justifyContent="space-between" alignItems="center" gap={1}>
                  <Typography variant="body2" color="text.secondary">
                    Selected: {copilotSelectedProjects.length}
                  </Typography>
                  <Button
                    variant="contained"
                    onClick={handleCopilotProjectsSave}
                    disabled={copilotProjectsLoading || isReadOnly}
                    title={isReadOnly ? readOnlyMessage : ''}
                    startIcon={copilotProjectsLoading ? <CircularProgress size={18} /> : <SaveIcon />}
                  >
                    Save Projects
                  </Button>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* UDE Version Applicability Configuration */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="h6">
                <SettingsIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                UDE Version Applicability Configuration
              </Typography>
              <Button
                startIcon={<RefreshIcon />}
                onClick={fetchUdeConfig}
                size="small"
                disabled={udeConfigLoading}
              >
                Refresh
              </Button>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Configure which UDE versions apply to which teams. Select specific teams to indicate
              a version is team-specific — once marked, all subsequent versions (by release order)
              also become specific to those teams. Leave the selection empty to mark a version as
              available to <strong>ALL</strong> employees. Only applicable versions are shown in
              employee UDE details and delay calculations.
            </Typography>

            {udeVersions.length === 0 ? (
              <Alert severity="info">
                No UDE versions found in the installation data. Run a UDE ingestion job first.
              </Alert>
            ) : (
              <>
                <TableContainer component={Paper} variant="outlined">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ width: 120 }}><strong>Version</strong></TableCell>
                        <TableCell sx={{ width: 140 }}><strong>Release Date</strong></TableCell>
                        <TableCell><strong>Applicable To (empty = ALL)</strong></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {udeVersions.map(({ version, release_date }) => {
                        const selectedTeams = udeVersionTeamMapping[version] || [];
                        return (
                          <TableRow key={version}>
                            <TableCell>
                              <Chip
                                label={version}
                                size="small"
                                color={selectedTeams.length > 0 ? 'primary' : 'default'}
                                variant={selectedTeams.length > 0 ? 'filled' : 'outlined'}
                              />
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">{release_date}</Typography>
                            </TableCell>
                            <TableCell>
                              <FormControl fullWidth size="small" variant="outlined">
                                <Select
                                  multiple
                                  displayEmpty
                                  value={selectedTeams}
                                  disabled={isReadOnly}
                                  onChange={(e: SelectChangeEvent<string[]>) => {
                                    const val = typeof e.target.value === 'string'
                                      ? e.target.value.split(',')
                                      : e.target.value;
                                    handleUdeTeamChange(version, val);
                                  }}
                                  renderValue={(selected) =>
                                    selected.length === 0
                                      ? <em style={{ color: '#777' }}>ALL (default)</em>
                                      : (selected as string[]).join(', ')
                                  }
                                >
                                  {availableTeams.map((team) => (
                                    <MenuItem key={team} value={team}>
                                      {team}
                                    </MenuItem>
                                  ))}
                                </Select>
                              </FormControl>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TableContainer>
                <Box display="flex" justifyContent="flex-end" mt={2}>
                  <Button
                    variant="contained"
                    onClick={handleSaveUdeConfig}
                    disabled={udeConfigLoading || isReadOnly}
                    title={isReadOnly ? readOnlyMessage : ''}
                    startIcon={udeConfigLoading ? <CircularProgress size={18} /> : <SaveIcon />}
                  >
                    Save UDE Configuration
                  </Button>
                </Box>
              </>
            )}
          </CardContent>
        </Card>
      </Grid>

      {/* Configuration Details Dialog */}
      <Dialog open={configDialog !== null} onClose={() => setConfigDialog(null)} maxWidth="md" fullWidth>
        <DialogTitle>
          {
            configDialog === 'github'
              ? 'GitHub Repositories'
              : configDialog === 'gitlab'
                ? 'GitLab Repositories'
              : configDialog === 'jira'
                ? 'JIRA Projects'
                : configDialog === 'scan'
                  ? 'Security Scan Projects'
                  : 'Configuration Details'
          }
        </DialogTitle>
        <DialogContent>
          {(configDialog === 'github' || configDialog === null) && (
            <Box sx={{ mb: configDialog === null ? 3 : 0 }}>
              <Typography variant="h6" gutterBottom>
                <GitHubIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                GitHub Repositories ({configData?.github_repositories.length || 0})
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>#</TableCell>
                      <TableCell>Repository</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {configData?.github_repositories.map((repo, idx) => (
                      <TableRow key={repo}>
                        <TableCell>{idx + 1}</TableCell>
                        <TableCell>{repo}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {(configDialog === 'gitlab' || configDialog === null) && (
            <Box sx={{ mt: configDialog === null ? 3 : 0, mb: configDialog === null ? 3 : 0 }}>
              <Typography variant="h6" gutterBottom>
                <GitHubIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                GitLab Repositories ({configData?.gitlab_repositories.length || 0})
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>#</TableCell>
                      <TableCell>Repository</TableCell>
                      <TableCell>Mapped Team</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {configData?.gitlab_repositories.map((repo, idx) => (
                      <TableRow key={repo}>
                        <TableCell>{idx + 1}</TableCell>
                        <TableCell>{repo}</TableCell>
                        <TableCell>{configData?.gitlab_repo_team_mapping?.[repo] || '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {(configDialog === 'jira' || configDialog === null) && (
            <Box>
              <Typography variant="h6" gutterBottom>
                <JiraIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                JIRA Projects ({configData?.jira_projects.length || 0})
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>#</TableCell>
                      <TableCell>Project Key</TableCell>
                      <TableCell>Mapped Team</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {configData?.jira_projects.map((project, idx) => (
                      <TableRow key={project}>
                        <TableCell>{idx + 1}</TableCell>
                        <TableCell>{project}</TableCell>
                        <TableCell>{configData?.jira_prefix_team_mapping?.[project] || '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}

          {(configDialog === 'scan' || configDialog === null) && (
            <Box sx={{ mt: configDialog === null ? 3 : 0 }}>
              <Typography variant="h6" gutterBottom>
                <SecurityIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
                Security Scan Projects ({scanConfig?.projects.length || 0})
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>#</TableCell>
                      <TableCell>Project ID</TableCell>
                      <TableCell>Project Name</TableCell>
                      <TableCell>Mapped Team</TableCell>
                      <TableCell align="center">SAST</TableCell>
                      <TableCell align="center">SCA</TableCell>
                      <TableCell align="center">DAST</TableCell>
                      <TableCell align="center">MEND</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(scanConfig?.projects ?? []).flatMap((project, index) => {
                      const reportTypes = new Set(project.reports.map((report) => report.type));
                      const mappedTeams = (project.teams?.length ?? 0) > 0 ? project.teams : ['-'];
                      return mappedTeams.map((teamName, teamIndex) => (
                        <TableRow key={`${project.id}-${teamName}-${teamIndex}`}>
                          <TableCell>{teamIndex === 0 ? index + 1 : ''}</TableCell>
                          <TableCell>{teamIndex === 0 ? project.id : ''}</TableCell>
                          <TableCell>{teamIndex === 0 ? project.name : ''}</TableCell>
                          <TableCell>{teamName}</TableCell>
                          <TableCell align="center">
                            <Chip
                              label={reportTypes.has('sast') ? 'Enabled' : 'Disabled'}
                              size="small"
                              color={reportTypes.has('sast') ? 'success' : 'default'}
                              variant={reportTypes.has('sast') ? 'filled' : 'outlined'}
                            />
                          </TableCell>
                          <TableCell align="center">
                            <Chip
                              label={reportTypes.has('sca') ? 'Enabled' : 'Disabled'}
                              size="small"
                              color={reportTypes.has('sca') ? 'success' : 'default'}
                              variant={reportTypes.has('sca') ? 'filled' : 'outlined'}
                            />
                          </TableCell>
                          <TableCell align="center">
                            <Chip
                              label={reportTypes.has('dast') ? 'Enabled' : 'Disabled'}
                              size="small"
                              color={reportTypes.has('dast') ? 'success' : 'default'}
                              variant={reportTypes.has('dast') ? 'filled' : 'outlined'}
                            />
                          </TableCell>
                          <TableCell align="center">
                            <Chip
                              label={reportTypes.has('mend') ? 'Enabled' : 'Disabled'}
                              size="small"
                              color={reportTypes.has('mend') ? 'success' : 'default'}
                              variant={reportTypes.has('mend') ? 'filled' : 'outlined'}
                            />
                          </TableCell>
                        </TableRow>
                      ));
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfigDialog(null)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Copilot Test Connection Result Dialog */}
      <Dialog open={copilotTestOpen} onClose={() => setCopilotTestOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Database Connection Test
        </DialogTitle>
        <DialogContent>
          {copilotTestResult && (
            <Box>
              <Box display="flex" alignItems="center" gap={1} mb={2}>
                <Chip
                  label={copilotTestResult.success ? 'Connected' : 'Failed'}
                  color={copilotTestResult.success ? 'success' : 'error'}
                  icon={copilotTestResult.success ? <SaveIcon /> : <DeleteIcon />}
                />
              </Box>
              <Box mb={2}>
                <Typography variant="subtitle2" color="text.secondary">
                  Status: {copilotTestResult.status}
                </Typography>
                <Typography variant="body2">
                  {copilotTestResult.message}
                </Typography>
              </Box>
              {copilotTestResult.output && (
                <Box
                  sx={{
                    backgroundColor: '#f5f5f5',
                    border: '1px solid #ddd',
                    borderRadius: 1,
                    p: 1.5,
                    fontFamily: 'monospace',
                    fontSize: '0.85rem',
                    maxHeight: '300px',
                    overflow: 'auto',
                    mb: 2
                  }}
                >
                  <Typography variant="caption" component="pre" sx={{ whiteSpace: 'pre-wrap', wordWrap: 'break-word' }}>
                    {copilotTestResult.output}
                  </Typography>
                </Box>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCopilotTestOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert
          onClose={() => setSnackbar({ ...snackbar, open: false })}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default ProjectOnboardingPage;
