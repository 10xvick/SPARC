import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Paper,
  Typography,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Grid,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Alert,
  TextField,
  MenuItem,
  FormControl,
  InputLabel,
  Select,
  SelectChangeEvent,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  IconButton,
  Link,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import DownloadIcon from '@mui/icons-material/Download';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import {
  getReplanSummary,
  getReplanIssues,
  getHighReplanIssues,
  getReplanStatistics,
  getIssueReplanDetails,
  exportReplanIssuesCsv,
  ReplanSummary,
  ReplanStatistics,
  IssuesResponse,
  HighReplansResponse,
  IssueFilters,
  IssueReplanDetails,
} from '../services/replanTrackerApi';



interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

// Helper component for table headers with tooltips
const HeaderWithTooltip: React.FC<{ title: string; tooltip: string }> = ({ title, tooltip }) => (
  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
    {title}
    <Tooltip title={tooltip} arrow placement="top">
      <InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary', cursor: 'help' }} />
    </Tooltip>
  </Box>
);

const ReplanTrackerPage: React.FC = () => {
  const navigate = useNavigate();
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // State for data
  const [summary, setSummary] = useState<ReplanSummary | null>(null);
  const [statistics, setStatistics] = useState<ReplanStatistics | null>(null);
  const [issuesData, setIssuesData] = useState<IssuesResponse | null>(null);
  const [highReplans, setHighReplans] = useState<HighReplansResponse | null>(null);

  // State for filters
  const [filters, setFilters] = useState<IssueFilters>({
    page: 1,
    page_size: 25,
  });

  // State for replan details dialog
  const [detailsDialogOpen, setDetailsDialogOpen] = useState(false);
  const [selectedIssueDetails, setSelectedIssueDetails] = useState<IssueReplanDetails | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);

  // Load data
  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [summaryData, statsData, issuesResult, highReplansData] = await Promise.all([
        getReplanSummary(),
        getReplanStatistics(),
        getReplanIssues(filters),
        getHighReplanIssues(20),
      ]);
      setSummary(summaryData);
      setStatistics(statsData);
      setIssuesData(issuesResult);
      setHighReplans(highReplansData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [filters]);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleFilterChange = (field: keyof IssueFilters, value: any) => {
    setFilters(prev => ({ ...prev, [field]: value, page: 1 }));
  };

  const handlePageChange = (_event: unknown, newPage: number) => {
    setFilters(prev => ({ ...prev, page: newPage + 1 }));
  };

  const handleRowsPerPageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilters(prev => ({ ...prev, page_size: parseInt(event.target.value, 10), page: 1 }));
  };

  const handleReplanCountClick = async (issueKey: string) => {
    setDetailsDialogOpen(true);
    setDetailsLoading(true);
    setSelectedIssueDetails(null);
    
    try {
      const details = await getIssueReplanDetails(issueKey);
      setSelectedIssueDetails(details);
    } catch (err) {
      console.error('Error fetching replan details:', err);
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleCloseDetailsDialog = () => {
    setDetailsDialogOpen(false);
    setSelectedIssueDetails(null);
  };

  const handleExportIssuesCsv = async () => {
    try {
      setExportLoading(true);
      const csvBlob = await exportReplanIssuesCsv(filters);
      const url = window.URL.createObjectURL(csvBlob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `replan-tracker-all-issues-${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export replan issues CSV');
      console.error('Error exporting replan issues CSV:', err);
    } finally {
      setExportLoading(false);
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={3}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  // Helper functions for rendering
  const openEpicTree = (epicKey: string) => {
    navigate(`/reports/jira-epic-tree?epic=${encodeURIComponent(epicKey)}&insights=true`);
  };

  const EpicCell: React.FC<{ epicKey?: string | null; epicSummary?: string | null }> = ({ epicKey, epicSummary }) => {
    if (!epicKey || epicKey === 'NA') return <span style={{ color: '#999' }}>NA</span>;
    return (
      <Tooltip title={epicSummary || epicKey} arrow placement="top">
        <Link
          component="button"
          variant="body2"
          onClick={() => openEpicTree(epicKey)}
          sx={{ cursor: 'pointer', fontWeight: 500 }}
        >
          {epicKey}
        </Link>
      </Tooltip>
    );
  };

  const getReplanColor = (count: number): 'default' | 'success' | 'warning' | 'error' => {
    if (count === 0) return 'success';
    if (count <= 2) return 'default';
    if (count <= 5) return 'warning';
    return 'error';
  };

  const getPriorityColor = (priority: string): 'default' | 'error' | 'warning' | 'info' => {
    const p = priority.toLowerCase();
    if (p.includes('blocker') || p.includes('critical') || p.includes('highest') || p.includes('p1')) return 'error';
    if (p.includes('high') || p.includes('major') || p.includes('p2')) return 'warning';
    if (p.includes('medium') || p.includes('p3')) return 'info';
    return 'default';
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Replan Tracker Report
      </Typography>
      <Typography variant="body2" color="text.secondary" paragraph>
        Track sprint changes and replanning metrics for Stories, Epics, and Tasks
      </Typography>

      {/* Statistics Cards */}
      {statistics && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Total Issues
                </Typography>
                <Typography variant="h4">{statistics.total_issues.toLocaleString()}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Total Replans
                </Typography>
                <Typography variant="h4">{statistics.total_replans.toLocaleString()}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Replan Rate
                </Typography>
                <Typography variant="h4">{statistics.replan_rate_percent}%</Typography>
                <Typography variant="caption" color="text.secondary">
                  {statistics.issues_with_replans.toLocaleString()} issues replanned
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Avg Replans
                </Typography>
                <Typography variant="h4">{statistics.avg_replans_when_replanned}</Typography>
                <Typography variant="caption" color="text.secondary">
                  when replanned
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      <Paper>
        <Tabs value={tabValue} onChange={handleTabChange} sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tab label="Summary by Issue Type" />
          <Tab label="Summary by Team" />
          <Tab label="Summary by Scrum" />
          <Tab label="By Priority" />
          <Tab label="High Replans" />
          <Tab label="All Issues" />
        </Tabs>

        {/* Tab 0: Summary by Issue Type */}
        <TabPanel value={tabValue} index={0}>
          {summary && summary.by_issue_type.length > 0 ? (
            <>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Total Replans by Issue Type
                  </Typography>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={summary.by_issue_type}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="Issue_Type" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Bar dataKey="Total_Replans" fill="#2196F3" name="Total Replans" />
                      <Bar dataKey="Issue_Count" fill="#4CAF50" name="Issue Count" />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Avg Replans per Issue
                  </Typography>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={summary.by_issue_type}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="Issue_Type" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Bar dataKey="Avg_Replans_Per_Issue" fill="#FF9800" name="Avg Replans" />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
              </Grid>

              <TableContainer sx={{ mt: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Issue Type</strong></TableCell>
                      <TableCell align="right"><strong>Issue Count</strong></TableCell>
                      <TableCell align="right">
                        <HeaderWithTooltip
                          title="Total Replans"
                          tooltip="Total number of sprint changes across all issues"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <HeaderWithTooltip
                          title="Avg Replans"
                          tooltip="Average number of sprint changes per issue"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <HeaderWithTooltip
                          title="Max Replans"
                          tooltip="Maximum number of sprint changes for a single issue"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <HeaderWithTooltip
                          title="Avg Sprints"
                          tooltip="Average number of sprints an issue was in"
                        />
                      </TableCell>
                      <TableCell align="right"><strong>Story Points</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {summary.by_issue_type.map((row) => (
                      <TableRow key={row.Issue_Type}>
                        <TableCell>{row.Issue_Type}</TableCell>
                        <TableCell align="right">{row.Issue_Count}</TableCell>
                        <TableCell align="right">{row.Total_Replans}</TableCell>
                        <TableCell align="right">{row.Avg_Replans_Per_Issue.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Max_Replans}</TableCell>
                        <TableCell align="right">{row.Avg_Sprints_Per_Issue.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Total_Story_Points}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          ) : (
            <Alert severity="info">No issue type summary data available</Alert>
          )}
        </TabPanel>

        {/* Tab 1: Summary by Team */}
        <TabPanel value={tabValue} index={1}>
          {summary && summary.by_team.length > 0 ? (
            <>
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <Typography variant="h6" gutterBottom>
                    Replan Metrics by Team
                  </Typography>
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart data={summary.by_team}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="Team" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Bar dataKey="Total_Replans" fill="#2196F3" name="Total Replans" />
                      <Bar dataKey="Issue_Count" fill="#4CAF50" name="Issue Count" />
                      <Bar dataKey="Avg_Replans_Per_Issue" fill="#FF9800" name="Avg Replans" />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
              </Grid>

              <TableContainer sx={{ mt: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Team</strong></TableCell>
                      <TableCell align="right"><strong>Issue Count</strong></TableCell>
                      <TableCell align="right"><strong>Total Replans</strong></TableCell>
                      <TableCell align="right"><strong>Avg Replans</strong></TableCell>
                      <TableCell align="right"><strong>Max Replans</strong></TableCell>
                      <TableCell align="right">
                        <HeaderWithTooltip
                          title="Replan Rate"
                          tooltip="Percentage of issues that were replanned at least once"
                        />
                      </TableCell>
                      <TableCell align="right"><strong>Story Points</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {summary.by_team.map((row) => (
                      <TableRow key={row.Team}>
                        <TableCell><strong>{row.Team}</strong></TableCell>
                        <TableCell align="right">{row.Issue_Count}</TableCell>
                        <TableCell align="right">{row.Total_Replans}</TableCell>
                        <TableCell align="right">{row.Avg_Replans_Per_Issue.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Max_Replans}</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${row['Replan_Rate_%']}%`}
                            color={row['Replan_Rate_%'] > 50 ? 'error' : row['Replan_Rate_%'] > 30 ? 'warning' : 'success'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">{row.Total_Story_Points}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          ) : (
            <Alert severity="info">No team summary data available</Alert>
          )}
        </TabPanel>

        {/* Tab 2: Summary by Scrum */}
        <TabPanel value={tabValue} index={2}>
          {summary && summary.by_scrum.length > 0 ? (
            <>
              <Grid container spacing={3}>
                <Grid item xs={12}>
                  <Typography variant="h6" gutterBottom>
                    Replan Metrics by Scrum Team
                  </Typography>
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart data={summary.by_scrum}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="Scrum" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Bar dataKey="Total_Replans" fill="#2196F3" name="Total Replans" />
                      <Bar dataKey="Avg_Replans_Per_Issue" fill="#FF9800" name="Avg Replans" />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
              </Grid>

              <TableContainer sx={{ mt: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Scrum Team</strong></TableCell>
                      <TableCell align="right"><strong>Issue Count</strong></TableCell>
                      <TableCell align="right"><strong>Total Replans</strong></TableCell>
                      <TableCell align="right"><strong>Avg Replans</strong></TableCell>
                      <TableCell align="right"><strong>Max Replans</strong></TableCell>
                      <TableCell align="right"><strong>Replan Rate</strong></TableCell>
                      <TableCell align="right"><strong>Story Points</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {summary.by_scrum.map((row) => (
                      <TableRow key={row.Scrum}>
                        <TableCell><strong>{row.Scrum}</strong></TableCell>
                        <TableCell align="right">{row.Issue_Count}</TableCell>
                        <TableCell align="right">{row.Total_Replans}</TableCell>
                        <TableCell align="right">{row.Avg_Replans_Per_Issue.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Max_Replans}</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${row['Replan_Rate_%']}%`}
                            color={row['Replan_Rate_%'] > 50 ? 'error' : row['Replan_Rate_%'] > 30 ? 'warning' : 'success'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">{row.Total_Story_Points}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          ) : (
            <Alert severity="info">No scrum summary data available</Alert>
          )}
        </TabPanel>

        {/* Tab 3: By Priority */}
        <TabPanel value={tabValue} index={3}>
          {summary && summary.by_priority.length > 0 ? (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell><strong>Issue Type</strong></TableCell>
                    <TableCell><strong>Priority</strong></TableCell>
                    <TableCell align="right"><strong>Count</strong></TableCell>
                    <TableCell align="right"><strong>Total Replans</strong></TableCell>
                    <TableCell align="right"><strong>Avg Replans</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {summary.by_priority.map((row, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{row.Issue_Type}</TableCell>
                      <TableCell>
                        <Chip label={row.Priority} color={getPriorityColor(row.Priority)} size="small" />
                      </TableCell>
                      <TableCell align="right">{row.Count}</TableCell>
                      <TableCell align="right">{row.Total_Replans}</TableCell>
                      <TableCell align="right">{row.Avg_Replans.toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Alert severity="info">No priority breakdown data available</Alert>
          )}
        </TabPanel>

        {/* Tab 4: High Replans */}
        <TabPanel value={tabValue} index={4}>
          {highReplans && highReplans.high_replan_issues.length > 0 ? (
            <>
              <Typography variant="body2" color="text.secondary" paragraph>
                Showing top {highReplans.count} issues with highest replan counts
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Key</strong></TableCell>
                      <TableCell><strong>Project</strong></TableCell>
                      <TableCell><strong>Team</strong></TableCell>
                      <TableCell><strong>Issue Type</strong></TableCell>
                      <TableCell><strong>Epic</strong></TableCell>
                      <TableCell><strong>Priority</strong></TableCell>
                      <TableCell align="right"><strong>Replans</strong></TableCell>
                      <TableCell align="right"><strong>Sprints</strong></TableCell>
                      <TableCell><strong>Status</strong></TableCell>
                      <TableCell><strong>Assignee</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {highReplans.high_replan_issues.map((issue) => (
                      <TableRow key={issue.Key}>
                        <TableCell><strong>{issue.Key}</strong></TableCell>
                        <TableCell>{issue.Project}</TableCell>
                        <TableCell>{issue.Team}</TableCell>
                        <TableCell>{issue.Issue_Type}</TableCell>
                        <TableCell>
                          <EpicCell epicKey={issue.Epic_Key} epicSummary={issue.Epic_Summary} />
                        </TableCell>
                        <TableCell>
                          <Chip label={issue.Priority} color={getPriorityColor(issue.Priority)} size="small" />
                        </TableCell>
                        <TableCell align="right">
                          <Chip 
                            label={issue.Replan_Count} 
                            color={getReplanColor(issue.Replan_Count)} 
                            size="small" 
                            onClick={() => handleReplanCountClick(issue.Key)}
                            sx={{ cursor: 'pointer' }}
                          />
                        </TableCell>
                        <TableCell align="right">{issue.Total_Sprints}</TableCell>
                        <TableCell>{issue.Current_Status}</TableCell>
                        <TableCell>{issue.Assignee || 'Unassigned'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          ) : (
            <Alert severity="info">No high replan issues available</Alert>
          )}
        </TabPanel>

        {/* Tab 5: All Issues */}
        <TabPanel value={tabValue} index={5}>
          {issuesData && (
            <>
              {/* Filters */}
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} sm={6} md={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Team</InputLabel>
                    <Select
                      value={filters.team || ''}
                      label="Team"
                      onChange={(e: SelectChangeEvent) => handleFilterChange('team', e.target.value || undefined)}
                    >
                      <MenuItem value="">All</MenuItem>
                      {issuesData.filters.teams.map(team => (
                        <MenuItem key={team} value={team}>{team}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Scrum</InputLabel>
                    <Select
                      value={filters.scrum || ''}
                      label="Scrum"
                      onChange={(e: SelectChangeEvent) => handleFilterChange('scrum', e.target.value || undefined)}
                    >
                      <MenuItem value="">All</MenuItem>
                      {issuesData.filters.scrums.map(scrum => (
                        <MenuItem key={scrum} value={scrum}>{scrum}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Issue Type</InputLabel>
                    <Select
                      value={filters.issue_type || ''}
                      label="Issue Type"
                      onChange={(e: SelectChangeEvent) => handleFilterChange('issue_type', e.target.value || undefined)}
                    >
                      <MenuItem value="">All</MenuItem>
                      {issuesData.filters.issue_types.map(type => (
                        <MenuItem key={type} value={type}>{type}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Priority</InputLabel>
                    <Select
                      value={filters.priority || ''}
                      label="Priority"
                      onChange={(e: SelectChangeEvent) => handleFilterChange('priority', e.target.value || undefined)}
                    >
                      <MenuItem value="">All</MenuItem>
                      {issuesData.filters.priorities.map(priority => (
                        <MenuItem key={priority} value={priority}>{priority}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Component</InputLabel>
                    <Select
                      value={filters.component || ''}
                      label="Component"
                      onChange={(e: SelectChangeEvent) => handleFilterChange('component', e.target.value || undefined)}
                    >
                      <MenuItem value="">All</MenuItem>
                      {issuesData.filters.components.map(component => (
                        <MenuItem key={component} value={component}>{component}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={2}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Status</InputLabel>
                    <Select
                      value={filters.current_status || ''}
                      label="Status"
                      onChange={(e: SelectChangeEvent) => handleFilterChange('current_status', e.target.value || undefined)}
                    >
                      <MenuItem value="">All</MenuItem>
                      {issuesData.filters.statuses.map(status => (
                        <MenuItem key={status} value={status}>{status}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={2}>
                  <TextField
                    fullWidth
                    size="small"
                    label="Min Replans"
                    type="number"
                    value={filters.min_replans || ''}
                    onChange={(e) => handleFilterChange('min_replans', e.target.value ? parseInt(e.target.value) : undefined)}
                  />
                </Grid>
              </Grid>

              <Box
                sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: { xs: 'flex-start', sm: 'center' },
                  flexDirection: { xs: 'column', sm: 'row' },
                  gap: 1.5,
                  mb: 2,
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  Export all filtered issues and replan history rows across every page.
                </Typography>
                <Button
                  variant="outlined"
                  startIcon={<DownloadIcon />}
                  onClick={handleExportIssuesCsv}
                  disabled={exportLoading || issuesData.pagination.total_count === 0}
                >
                  {exportLoading ? 'Preparing CSV...' : 'Download CSV'}
                </Button>
              </Box>

              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell><strong>Key</strong></TableCell>
                      <TableCell><strong>Project</strong></TableCell>
                      <TableCell><strong>Team</strong></TableCell>
                      <TableCell><strong>Type</strong></TableCell>
                      <TableCell><strong>Epic</strong></TableCell>
                      <TableCell><strong>Priority</strong></TableCell>
                      <TableCell align="right"><strong>Replans</strong></TableCell>
                      <TableCell align="right"><strong>Sprints</strong></TableCell>
                      <TableCell align="right"><strong>Points</strong></TableCell>
                      <TableCell><strong>Status</strong></TableCell>
                      <TableCell><strong>Assignee</strong></TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {issuesData.issues.map((issue) => (
                      <TableRow key={issue.Key}>
                        <TableCell><strong>{issue.Key}</strong></TableCell>
                        <TableCell>{issue.Project}</TableCell>
                        <TableCell>{issue.Team}</TableCell>
                        <TableCell>{issue.Issue_Type}</TableCell>
                        <TableCell>
                          <EpicCell epicKey={issue.Epic_Key} epicSummary={issue.Epic_Summary} />
                        </TableCell>
                        <TableCell>
                          <Chip label={issue.Priority} color={getPriorityColor(issue.Priority)} size="small" />
                        </TableCell>
                        <TableCell align="right">
                          <Chip 
                            label={issue.Replan_Count} 
                            color={getReplanColor(issue.Replan_Count)} 
                            size="small" 
                            onClick={() => handleReplanCountClick(issue.Key)}
                            sx={{ cursor: 'pointer' }}
                          />
                        </TableCell>
                        <TableCell align="right">{issue.Total_Sprints}</TableCell>
                        <TableCell align="right">{issue.Story_Points}</TableCell>
                        <TableCell>{issue.Current_Status}</TableCell>
                        <TableCell>{issue.Assignee || 'Unassigned'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              <TablePagination
                component="div"
                count={issuesData.pagination.total_count}
                page={issuesData.pagination.page - 1}
                onPageChange={handlePageChange}
                rowsPerPage={issuesData.pagination.page_size}
                onRowsPerPageChange={handleRowsPerPageChange}
                rowsPerPageOptions={[25, 50, 100]}
              />
            </>
          )}
        </TabPanel>
      </Paper>

      {/* Replan Details Dialog */}
      <Dialog 
        open={detailsDialogOpen} 
        onClose={handleCloseDetailsDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">
              {selectedIssueDetails ? `Replan History: ${selectedIssueDetails.issue_key}` : 'Replan History'}
            </Typography>
            <IconButton onClick={handleCloseDetailsDialog} size="small">
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent dividers>
          {detailsLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : selectedIssueDetails ? (
            <>
              {/* Issue Summary */}
              <Paper elevation={0} sx={{ p: 2, mb: 3, backgroundColor: '#f5f5f5' }}>
                <Grid container spacing={2}>
                  {selectedIssueDetails.description && (
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">Description</Typography>
                      <Typography variant="body2"><strong>{selectedIssueDetails.description}</strong></Typography>
                    </Grid>
                  )}
                  {selectedIssueDetails.epic_key && (
                    <Grid item xs={12}>
                      <Typography variant="caption" color="text.secondary">Epic</Typography>
                      <Typography variant="body2">
                        <EpicCell epicKey={selectedIssueDetails.epic_key} epicSummary={selectedIssueDetails.epic_summary} />
                        {selectedIssueDetails.epic_summary && (
                          <Typography component="span" variant="body2" color="text.secondary" sx={{ ml: 1 }}>
                            — {selectedIssueDetails.epic_summary}
                          </Typography>
                        )}
                      </Typography>
                    </Grid>
                  )}
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Project</Typography>
                    <Typography variant="body2"><strong>{selectedIssueDetails.project}</strong></Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Team</Typography>
                    <Typography variant="body2"><strong>{selectedIssueDetails.team}</strong></Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Scrum</Typography>
                    <Typography variant="body2"><strong>{selectedIssueDetails.scrum}</strong></Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Assignee</Typography>
                    <Typography variant="body2">{selectedIssueDetails.assignee}</Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Type</Typography>
                    <Typography variant="body2">{selectedIssueDetails.issue_type}</Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Priority</Typography>
                    <Typography variant="body2">
                      <Chip 
                        label={selectedIssueDetails.priority} 
                        color={getPriorityColor(selectedIssueDetails.priority)} 
                        size="small" 
                      />
                    </Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Story Points</Typography>
                    <Typography variant="body2">{selectedIssueDetails.story_points}</Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Current Status</Typography>
                    <Typography variant="body2">{selectedIssueDetails.current_status}</Typography>
                  </Grid>
                  <Grid item xs={6} sm={4}>
                    <Typography variant="caption" color="text.secondary">Total Replans</Typography>
                    <Typography variant="body2">
                      <Chip 
                        label={selectedIssueDetails.replan_count} 
                        color={getReplanColor(selectedIssueDetails.replan_count)} 
                        size="small" 
                      />
                    </Typography>
                  </Grid>
                </Grid>
              </Paper>

              {/* Replan Timeline */}
              <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
                Sprint Timeline ({selectedIssueDetails.replan_history.length} changes)
              </Typography>
              
              {selectedIssueDetails.replan_history.length === 0 ? (
                <Alert severity="info">No sprint changes recorded for this issue.</Alert>
              ) : (
                <Stepper orientation="vertical">
                  {selectedIssueDetails.replan_history.map((entry, index) => (
                    <Step key={index} active={true} completed={index < selectedIssueDetails.replan_history.length - 1}>
                      <StepLabel
                        optional={
                          <Typography variant="caption" color="text.secondary">
                            {entry.date}
                          </Typography>
                        }
                      >
                        <Box display="flex" alignItems="center" gap={1}>
                          {entry.is_replan ? (
                            <Chip 
                              label={`Replan ${index}`} 
                              color="warning" 
                              size="small" 
                            />
                          ) : (
                            <Chip 
                              label="Initial Plan" 
                              color="success" 
                              size="small" 
                            />
                          )}
                        </Box>
                      </StepLabel>
                      <StepContent>
                        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                          {entry.sprint}
                        </Typography>
                      </StepContent>
                    </Step>
                  ))}
                </Stepper>
              )}
            </>
          ) : (
            <Alert severity="error">Failed to load replan details</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDetailsDialog}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ReplanTrackerPage;
