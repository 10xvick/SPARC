/**
 * Bug Cycle Time Report Page
 * Displays bug cycle time analysis with charts and detailed tables
 */
import React, { useEffect, useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  CircularProgress,
  Alert,
  Chip,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tabs,
  Tab,
  Tooltip as MuiTooltip,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import {
  getBugCycleTimeSummary,
  getBugs,
  getTopIssues,
  getStatistics,
  getReworkByAssignee,
  BugCycleTimeSummary,
  BugsResponse,
  TopIssuesResponse,
  Statistics,
  BugFilters,
  ReworkByAssigneeResponse,
} from '../services/bugCycleTimeApi';

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <div hidden={value !== index}>
    {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
  </div>
);

// Helper component for table headers with tooltips
interface HeaderWithTooltipProps {
  title: string;
  tooltip: string;
  align?: 'left' | 'right' | 'center';
}

const HeaderWithTooltip: React.FC<HeaderWithTooltipProps> = ({ title, tooltip, align = 'left' }) => (
  <TableCell align={align}>
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: align === 'right' ? 'flex-end' : 'flex-start', gap: 0.5 }}>
      <Typography variant="body2" component="span">{title}</Typography>
      <MuiTooltip title={tooltip} arrow placement="top">
        <InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary', cursor: 'help' }} />
      </MuiTooltip>
    </Box>
  </TableCell>
);

const BugCycleTimeReportPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // State for data
  const [summary, setSummary] = useState<BugCycleTimeSummary | null>(null);
  const [statistics, setStatistics] = useState<Statistics | null>(null);
  const [bugsData, setBugsData] = useState<BugsResponse | null>(null);
  const [topIssues, setTopIssues] = useState<TopIssuesResponse | null>(null);
  const [reworkByAssignee, setReworkByAssignee] = useState<ReworkByAssigneeResponse | null>(null);
    
  // Filter state
  const [filters, setFilters] = useState<BugFilters>({ page: 1, page_size: 25 });
  const [tabValue, setTabValue] = useState(0);
  const [topIssuesSortBy, setTopIssuesSortBy] = useState<'cycle_time' | 'rework_count' | 'transitions'>('cycle_time');

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (bugsData) {
      loadBugs();
    }
  }, [filters]);

  useEffect(() => {
    loadTopIssues();
  }, [topIssuesSortBy]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const [summaryData, statsData, bugsData, topData, reworkData] = await Promise.all([
        getBugCycleTimeSummary(),
        getStatistics(),
        getBugs(filters),
        getTopIssues(10, topIssuesSortBy),
        getReworkByAssignee(15),
      ]);
      
      setSummary(summaryData);
      setStatistics(statsData);
      setBugsData(bugsData);
      setTopIssues(topData);
      setReworkByAssignee(reworkData);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load bug cycle time data');
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadBugs = async () => {
    try {
      const data = await getBugs(filters);
      setBugsData(data);
    } catch (err: any) {
      console.error('Error loading bugs:', err);
    }
  };

  const loadTopIssues = async () => {
    try {
      const data = await getTopIssues(10, topIssuesSortBy);
      setTopIssues(data);
    } catch (err: any) {
      console.error('Error loading top issues:', err);
    }
  };

  const handleFilterChange = (field: keyof BugFilters, value: any) => {
    setFilters(prev => ({ ...prev, [field]: value, page: 1 }));
  };

  const handlePageChange = (_event: unknown, newPage: number) => {
    setFilters(prev => ({ ...prev, page: newPage + 1 }));
  };

  const handleRowsPerPageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilters(prev => ({ ...prev, page_size: parseInt(event.target.value, 10), page: 1 }));
  };

  const getCycleTimeColor = (days: number): string => {
    if (days < 7) return '#4CAF50';
    if (days < 30) return '#FFA726';
    return '#EF5350';
  };

  const getPriorityColor = (priority: string): string => {
    const lowerPriority = priority.toLowerCase();
    if (lowerPriority.includes('blocker') || lowerPriority.includes('critical')) return '#EF5350';
    if (lowerPriority.includes('high') || lowerPriority.includes('p1')) return '#FF9800';
    if (lowerPriority.includes('medium') || lowerPriority.includes('p2')) return '#FFC107';
    return '#9E9E9E';
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

  return (
    <Box p={3}>
      <Typography variant="h4" gutterBottom>
        Bug Cycle Time Analysis
      </Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 3 }}>
        Analyze bug resolution times, transitions, and rework patterns
      </Typography>

      {/* Statistics Cards */}
      {statistics && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Total Bugs
                </Typography>
                <Typography variant="h4">{statistics.total_bugs}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Avg Cycle Time
                </Typography>
                <Typography variant="h4">{statistics.avg_cycle_time_days.toFixed(1)}</Typography>
                <Typography variant="caption" color="text.secondary">
                  days
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Median Cycle Time
                </Typography>
                <Typography variant="h4">{statistics.median_cycle_time_days.toFixed(1)}</Typography>
                <Typography variant="caption" color="text.secondary">
                  days
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Bugs with Rework
                </Typography>
                <Typography variant="h4">{statistics.rework_percentage.toFixed(1)}%</Typography>
                <Typography variant="caption" color="text.secondary">
                  {statistics.bugs_with_rework} bugs
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Tabs for different views */}
      <Paper sx={{ mb: 3 }}>
        <Tabs value={tabValue} onChange={(_e, newValue) => setTabValue(newValue)}>
          <Tab label="Summary by Priority" />
          <Tab label="Summary by Team" />
          <Tab label="Summary by Scrum" />
          <Tab label="Rework Analysis" />
          <Tab label="Top Issues" />
          <Tab label="All Bugs" />
        </Tabs>

        {/* Summary by Priority */}
        <TabPanel value={tabValue} index={0}>
          {summary?.by_priority && summary.by_priority.length > 0 && (
            <>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Average Cycle Time by Priority
                  </Typography>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={summary.by_priority}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="Priority" />
                      <YAxis label={{ value: 'Days', angle: -90, position: 'insideLeft' }} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="Avg_Cycle_Time_Days" fill="#8884d8" name="Avg Cycle Time" />
                      <Bar dataKey="Median_Cycle_Time_Days" fill="#82ca9d" name="Median Cycle Time" />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Bug Count by Priority
                  </Typography>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={summary.by_priority}
                        dataKey="Bug_Count"
                        nameKey="Priority"
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        fill="#8884d8"
                        label
                      >
                        {summary.by_priority.map((_entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </Grid>
              </Grid>
              <TableContainer sx={{ mt: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Priority</TableCell>
                      <TableCell align="right">Bug Count</TableCell>
                      <HeaderWithTooltip
                        title="Avg Cycle Time"
                        tooltip="Average time in days from bug creation to resolution"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Median"
                        tooltip="Middle value of cycle times - less affected by extreme outliers than average"
                        align="right"
                      />
                      <TableCell align="right">Min</TableCell>
                      <TableCell align="right">Max</TableCell>
                      <HeaderWithTooltip
                        title="Avg Transitions"
                        tooltip="Average number of status changes from creation to resolution"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Rework"
                        tooltip="Average number of times a bug returned to a previous status (indicates rework)"
                        align="right"
                      />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {summary.by_priority.map((row) => (
                      <TableRow key={row.Priority}>
                        <TableCell>
                          <Chip
                            label={row.Priority}
                            size="small"
                            sx={{ bgcolor: getPriorityColor(row.Priority!), color: 'white' }}
                          />
                        </TableCell>
                        <TableCell align="right">{row.Bug_Count}</TableCell>
                        <TableCell align="right">{row.Avg_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Median_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Min_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Max_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Avg_Transitions.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Avg_Rework_Count.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </TabPanel>

        {/* Summary by Team */}
        <TabPanel value={tabValue} index={1}>
          {summary?.by_team && summary.by_team.length > 0 && (
            <>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={summary.by_team}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="Team" />
                  <YAxis label={{ value: 'Days', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Avg_Cycle_Time_Days" fill="#8884d8" name="Avg Cycle Time" />
                  <Bar dataKey="Median_Cycle_Time_Days" fill="#82ca9d" name="Median Cycle Time" />
                </BarChart>
              </ResponsiveContainer>
              <TableContainer sx={{ mt: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Team</TableCell>
                      <TableCell align="right">Bug Count</TableCell>
                      <HeaderWithTooltip
                        title="Avg Cycle Time"
                        tooltip="Average time in days from bug creation to resolution"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Median"
                        tooltip="Middle value of cycle times - less affected by extreme outliers than average"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Transitions"
                        tooltip="Average number of status changes from creation to resolution"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Rework"
                        tooltip="Average number of times a bug returned to a previous status (indicates rework)"
                        align="right"
                      />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {summary.by_team.map((row) => (
                      <TableRow key={row.Team}>
                        <TableCell>{row.Team}</TableCell>
                        <TableCell align="right">{row.Bug_Count}</TableCell>
                        <TableCell align="right">{row.Avg_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Median_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Avg_Transitions.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Avg_Rework_Count.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </TabPanel>

        {/* Summary by Scrum */}
        <TabPanel value={tabValue} index={2}>
          {summary?.by_scrum && summary.by_scrum.length > 0 && (
            <>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={summary.by_scrum}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="Scrum" />
                  <YAxis label={{ value: 'Days', angle: -90, position: 'insideLeft' }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="Avg_Cycle_Time_Days" fill="#8884d8" name="Avg Cycle Time" />
                  <Bar dataKey="Median_Cycle_Time_Days" fill="#82ca9d" name="Median Cycle Time" />
                </BarChart>
              </ResponsiveContainer>
              <TableContainer sx={{ mt: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Scrum</TableCell>
                      <TableCell align="right">Bug Count</TableCell>
                      <HeaderWithTooltip
                        title="Avg Cycle Time"
                        tooltip="Average time in days from bug creation to resolution"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Median"
                        tooltip="Middle value of cycle times - less affected by extreme outliers than average"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Transitions"
                        tooltip="Average number of status changes from creation to resolution"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Rework"
                        tooltip="Average number of times a bug returned to a previous status (indicates rework)"
                        align="right"
                      />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {summary.by_scrum.map((row) => (
                      <TableRow key={row.Scrum}>
                        <TableCell>{row.Scrum}</TableCell>
                        <TableCell align="right">{row.Bug_Count}</TableCell>
                        <TableCell align="right">{row.Avg_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Median_Cycle_Time_Days.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Avg_Transitions.toFixed(2)}</TableCell>
                        <TableCell align="right">{row.Avg_Rework_Count.toFixed(2)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </TabPanel>

        {/* Rework Analysis */}
        <TabPanel value={tabValue} index={3}>
          {reworkByAssignee && (
            <>
              <Box sx={{ mb: 3 }}>
                <Typography variant="h6" gutterBottom>
                  Individuals with Most Rework Cases
                </Typography>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Total assignees with rework: {reworkByAssignee.total_assignees_with_rework} | 
                  Total bugs with rework: {reworkByAssignee.total_rework_cases}
                </Typography>
              </Box>

              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle1" gutterBottom>
                    Total Rework Count by Assignee
                  </Typography>
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart data={reworkByAssignee.top_assignees} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis dataKey="assignee" type="category" width={120} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="total_rework_count" fill="#EF5350" name="Total Rework Count" />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle1" gutterBottom>
                    Bugs with Rework by Assignee
                  </Typography>
                  <ResponsiveContainer width="100%" height={400}>
                    <BarChart data={reworkByAssignee.top_assignees} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis type="number" />
                      <YAxis dataKey="assignee" type="category" width={120} />
                      <Tooltip />
                      <Legend />
                      <Bar dataKey="bugs_with_rework" fill="#FF9800" name="Bugs with Rework" />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
              </Grid>

              <TableContainer sx={{ mt: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Assignee</TableCell>
                      <TableCell>Team</TableCell>
                      <TableCell align="right">Bugs with Rework</TableCell>
                      <HeaderWithTooltip
                        title="Total Rework Count"
                        tooltip="Sum of all rework instances across all bugs for this assignee"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Rework/Bug"
                        tooltip="Average number of rework instances per bug with rework"
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Cycle Time"
                        tooltip="Average cycle time in days for bugs with rework"
                        align="right"
                      />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {reworkByAssignee.top_assignees.map((assignee) => (
                      <TableRow key={assignee.assignee}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="medium">
                            {assignee.assignee}
                          </Typography>
                        </TableCell>
                        <TableCell>{assignee.team}</TableCell>
                        <TableCell align="right">
                          <Chip 
                            label={assignee.bugs_with_rework} 
                            size="small" 
                            color="warning"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Chip 
                            label={assignee.total_rework_count} 
                            size="small" 
                            sx={{ bgcolor: '#EF5350', color: 'white' }}
                          />
                        </TableCell>
                        <TableCell align="right">{assignee.avg_rework_per_bug.toFixed(2)}</TableCell>
                        <TableCell align="right">{assignee.avg_cycle_time.toFixed(1)} days</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </TabPanel>

        {/* Top Issues */}
        <TabPanel value={tabValue} index={4}>
          {topIssues && (
            <>
              <Box sx={{ mb: 2 }}>
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <InputLabel>Sort By</InputLabel>
                  <Select
                    value={topIssuesSortBy}
                    label="Sort By"
                    onChange={(e) => setTopIssuesSortBy(e.target.value as any)}
                  >
                    <MenuItem value="cycle_time">Cycle Time</MenuItem>
                    <MenuItem value="rework_count">Rework Count</MenuItem>
                    <MenuItem value="transitions">Transitions</MenuItem>
                  </Select>
                </FormControl>
              </Box>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Key</TableCell>
                      <TableCell>Project</TableCell>
                      <TableCell>Team</TableCell>
                      <TableCell>Priority</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Cycle Time (days)</TableCell>
                      <TableCell align="right">Transitions</TableCell>
                      <TableCell align="right">Rework</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {topIssues.top_issues.map((bug) => (
                      <TableRow key={bug.Key}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {bug.Key}
                          </Typography>
                        </TableCell>
                        <TableCell>{bug.Project}</TableCell>
                        <TableCell>{bug.Team}</TableCell>
                        <TableCell>
                          <Chip
                            label={bug.Priority}
                            size="small"
                            sx={{ bgcolor: getPriorityColor(bug.Priority), color: 'white' }}
                          />
                        </TableCell>
                        <TableCell>
                          <Chip label={bug.Current_Status} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell align="right">
                          <Chip
                            label={bug.Total_Cycle_Time_Days.toFixed(1)}
                            size="small"
                            sx={{ bgcolor: getCycleTimeColor(bug.Total_Cycle_Time_Days), color: 'white' }}
                          />
                        </TableCell>
                        <TableCell align="right">{bug.Transition_Count}</TableCell>
                        <TableCell align="right">
                          {bug.Rework_Count > 0 ? (
                            <Chip label={bug.Rework_Count} size="small" color="warning" />
                          ) : (
                            bug.Rework_Count
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </TabPanel>

        {/* All Bugs with Filters */}
        <TabPanel value={tabValue} index={5}>
          {bugsData && (
            <>
              {/* Filters */}
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Team</InputLabel>
                    <Select
                      value={filters.team || 'All'}
                      label="Team"
                      onChange={(e) => handleFilterChange('team', e.target.value === 'All' ? undefined : e.target.value)}
                    >
                      <MenuItem value="All">All Teams</MenuItem>
                      {bugsData.filters.teams.map((team) => (
                        <MenuItem key={team} value={team}>{team}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Scrum</InputLabel>
                    <Select
                      value={filters.scrum || 'All'}
                      label="Scrum"
                      onChange={(e) => handleFilterChange('scrum', e.target.value === 'All' ? undefined : e.target.value)}
                    >
                      <MenuItem value="All">All Scrums</MenuItem>
                      {bugsData.filters.scrums.map((scrum) => (
                        <MenuItem key={scrum} value={scrum}>{scrum}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Priority</InputLabel>
                    <Select
                      value={filters.priority || 'All'}
                      label="Priority"
                      onChange={(e) => handleFilterChange('priority', e.target.value === 'All' ? undefined : e.target.value)}
                    >
                      <MenuItem value="All">All Priorities</MenuItem>
                      {bugsData.filters.priorities.map((priority) => (
                        <MenuItem key={priority} value={priority}>{priority}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Project</InputLabel>
                    <Select
                      value={filters.project || 'All'}
                      label="Project"
                      onChange={(e) => handleFilterChange('project', e.target.value === 'All' ? undefined : e.target.value)}
                    >
                      <MenuItem value="All">All Projects</MenuItem>
                      {bugsData.filters.projects.map((project) => (
                        <MenuItem key={project} value={project}>{project}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
              </Grid>

              {/* Bugs Table */}
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Key</TableCell>
                      <TableCell>Project</TableCell>
                      <TableCell>Team</TableCell>
                      <TableCell>Assignee</TableCell>
                      <TableCell>Priority</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell align="right">Cycle Time (days)</TableCell>
                      <TableCell align="right">Transitions</TableCell>
                      <TableCell align="right">Rework</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {bugsData.bugs.map((bug) => (
                      <TableRow key={bug.Key}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {bug.Key}
                          </Typography>
                        </TableCell>
                        <TableCell>{bug.Project}</TableCell>
                        <TableCell>{bug.Team}</TableCell>
                        <TableCell>{bug.Assignee}</TableCell>
                        <TableCell>
                          <Chip
                            label={bug.Priority}
                            size="small"
                            sx={{ bgcolor: getPriorityColor(bug.Priority), color: 'white' }}
                          />
                        </TableCell>
                        <TableCell>
                          <Chip label={bug.Current_Status} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell align="right">
                          <Chip
                            label={bug.Total_Cycle_Time_Days.toFixed(1)}
                            size="small"
                            sx={{ bgcolor: getCycleTimeColor(bug.Total_Cycle_Time_Days), color: 'white' }}
                          />
                        </TableCell>
                        <TableCell align="right">{bug.Transition_Count}</TableCell>
                        <TableCell align="right">
                          {bug.Rework_Count > 0 ? (
                            <Chip label={bug.Rework_Count} size="small" color="warning" />
                          ) : (
                            bug.Rework_Count
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              {/* Pagination */}
              <TablePagination
                component="div"
                count={bugsData.pagination.total_items}
                page={bugsData.pagination.page - 1}
                onPageChange={handlePageChange}
                rowsPerPage={bugsData.pagination.page_size}
                onRowsPerPageChange={handleRowsPerPageChange}
                rowsPerPageOptions={[10, 25, 50, 100]}
              />
            </>
          )}
        </TabPanel>
      </Paper>
    </Box>
  );
};

export default BugCycleTimeReportPage;
