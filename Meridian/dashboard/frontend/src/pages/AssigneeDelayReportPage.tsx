import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Drawer,
  FormControl,
  Grid,
  InputLabel,
  Link as MuiLink,
  MenuItem,
  Paper,
  Select,
  SelectChangeEvent,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Tooltip as MuiTooltip,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import HistoryIcon from '@mui/icons-material/History';
import IconButton from '@mui/material/IconButton';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  AssigneeDelayAssigneesResponse,
  AssigneeDelayFilters,
  AssigneeDelayGroupRow,
  AssigneeDelayIssueDetailsResponse,
  AssigneeDelaySummaryResponse,
  getAssigneeDelayAssignees,
  getAssigneeDelayIssueDetails,
  getAssigneeDelaySummary,
} from '../services/assigneeDelayApi';
import {
  JiraIssueTransitionsResponse,
  reportsApi,
} from '../services/reportsApi';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

interface HeaderWithTooltipProps {
  title: string;
  tooltip: string;
  align?: 'left' | 'right' | 'center';
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index }) => (
  <div role="tabpanel" hidden={value !== index}>
    {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
  </div>
);

const HeaderWithTooltip: React.FC<HeaderWithTooltipProps> = ({ title, tooltip, align = 'left' }) => (
  <TableCell align={align}>
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: align === 'right' ? 'flex-end' : 'flex-start',
        gap: 0.5,
      }}
    >
      <Typography variant="body2" component="span" fontWeight="bold">
        {title}
      </Typography>
      <MuiTooltip title={tooltip} arrow placement="top">
        <InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary', cursor: 'help' }} />
      </MuiTooltip>
    </Box>
  </TableCell>
);

const formatNumber = (value: number): string => value.toLocaleString(undefined, { maximumFractionDigits: 2 });

function formatDateAsYyyyMmDd(value: string): string {
  const raw = String(value || '').trim();
  if (!raw) return 'NA';
  const m = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  if (m) return m[1];
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? raw : d.toISOString().slice(0, 10);
}

function formatDelayInDays(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value) || value < 0) return 'NA';
  return value.toFixed(1);
}

function formatDelayWithUnit(value: number | null | undefined): string {
  const f = formatDelayInDays(value);
  return f === 'NA' ? 'NA' : `${f}d`;
}

const AssigneeDelayReportPage: React.FC = () => {
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [loadingAssignees, setLoadingAssignees] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tabValue, setTabValue] = useState(0);

  const [summary, setSummary] = useState<AssigneeDelaySummaryResponse | null>(null);
  const [assigneesData, setAssigneesData] = useState<AssigneeDelayAssigneesResponse | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedAssignee, setSelectedAssignee] = useState<string>('');
  const [issueDetails, setIssueDetails] = useState<AssigneeDelayIssueDetailsResponse | null>(null);
  const [issueDetailsLoading, setIssueDetailsLoading] = useState(false);
  const [issueDetailsError, setIssueDetailsError] = useState<string | null>(null);

  // Issue transition history (layered drawer)
  const [transitionDrawerOpen, setTransitionDrawerOpen] = useState(false);
  const [selectedTransitionKey, setSelectedTransitionKey] = useState('');
  const [transitionDetails, setTransitionDetails] = useState<JiraIssueTransitionsResponse | null>(null);
  const [loadingTransitions, setLoadingTransitions] = useState(false);
  const [transitionError, setTransitionError] = useState<string | null>(null);

  const [filters, setFilters] = useState<AssigneeDelayFilters>({
    page: 1,
    page_size: 25,
    sort_by: 'total_delay',
    sort_order: 'desc',
  });

  useEffect(() => {
    const loadSummary = async () => {
      try {
        setLoadingSummary(true);
        setError(null);
        const summaryResponse = await getAssigneeDelaySummary(15);
        setSummary(summaryResponse);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load assignee delay summary');
      } finally {
        setLoadingSummary(false);
      }
    };

    loadSummary();
  }, []);

  useEffect(() => {
    const loadAssignees = async () => {
      try {
        setLoadingAssignees(true);
        const assigneesResponse = await getAssigneeDelayAssignees(filters);
        setAssigneesData(assigneesResponse);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load assignee delay details');
      } finally {
        setLoadingAssignees(false);
      }
    };

    loadAssignees();
  }, [filters]);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleFilterChange = (field: keyof AssigneeDelayFilters, value: string | number) => {
    setFilters((prev) => ({ ...prev, [field]: value, page: 1 }));
  };

  const handlePageChange = (_event: unknown, newPage: number) => {
    setFilters((prev) => ({ ...prev, page: newPage + 1 }));
  };

  const handleRowsPerPageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilters((prev) => ({ ...prev, page_size: Number(event.target.value), page: 1 }));
  };

  const handleOpenAssigneeDetails = async (assignee: string) => {
    const cleanAssignee = assignee.trim();
    if (!cleanAssignee) {
      return;
    }

    setSelectedAssignee(cleanAssignee);
    setDrawerOpen(true);
    setIssueDetails(null);
    setIssueDetailsError(null);
    setIssueDetailsLoading(true);

    try {
      const detailsResponse = await getAssigneeDelayIssueDetails(cleanAssignee);
      setIssueDetails(detailsResponse);
    } catch (err) {
      setIssueDetailsError(err instanceof Error ? err.message : 'Failed to load assignee issue details');
    } finally {
      setIssueDetailsLoading(false);
    }
  };

  const handleCloseDrawer = () => {
    setDrawerOpen(false);
  };

  const openIssueTransitions = async (issueKey: string) => {
    setSelectedTransitionKey(issueKey);
    setTransitionDrawerOpen(true);
    setTransitionDetails(null);
    setTransitionError(null);
    setLoadingTransitions(true);
    try {
      const data = await reportsApi.getJiraIssueTransitions(issueKey);
      setTransitionDetails(data);
    } catch (err: any) {
      setTransitionError(err.response?.data?.detail || `Failed to load transitions for ${issueKey}`);
    } finally {
      setLoadingTransitions(false);
    }
  };

  const individualChartData = useMemo(() => {
    return (assigneesData?.top_assignees ?? []).slice(0, 12).map((row) => ({
      name: row.Assignee,
      delay: row.Total_Attributable_Delay_Days,
    }));
  }, [assigneesData]);

  const teamChartData = useMemo(() => {
    return (summary?.by_team ?? []).slice(0, 12).map((row) => ({
      name: row.Team ?? 'Unknown',
      delay: row.Total_Attributable_Delay_Days,
    }));
  }, [summary]);

  const scrumChartData = useMemo(() => {
    return (summary?.by_scrum ?? []).slice(0, 12).map((row) => ({
      name: row.Scrum ?? 'Unknown',
      delay: row.Total_Attributable_Delay_Days,
    }));
  }, [summary]);

  const issueTableRows = useMemo(() => {
    return issueDetails?.issues ?? [];
  }, [issueDetails]);

  const renderGroupTable = (rows: AssigneeDelayGroupRow[], groupKey: 'Team' | 'Scrum') => (
    <TableContainer>
      <Table size="small">
        <TableHead>
          <TableRow>
            <HeaderWithTooltip
              title={groupKey}
              tooltip={
                groupKey === 'Team'
                  ? 'Team mapped from Resources configuration for each assignee.'
                  : 'Scrum mapped from Resources configuration for each assignee.'
              }
            />
            <HeaderWithTooltip
              title="Assignees"
              tooltip="Number of unique assignees in this group with attributable delay."
              align="right"
            />
            <HeaderWithTooltip
              title="Total Delay (Days)"
              tooltip="Sum of attributable delay days across all assignees in this group."
              align="right"
            />
            <HeaderWithTooltip
              title="Issues with Delay"
              tooltip="Total count of delayed issues contributed by assignees in this group."
              align="right"
            />
            <HeaderWithTooltip
              title="Avg Delay / Issue"
              tooltip="Average attributable delay days per delayed issue in this group."
              align="right"
            />
            <HeaderWithTooltip
              title="Delay Share %"
              tooltip="Percentage share of total attributable delay represented by this group."
              align="right"
            />
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={`${groupKey}-${index}`}>
              <TableCell>{(groupKey === 'Team' ? row.Team : row.Scrum) ?? 'Unknown'}</TableCell>
              <TableCell align="right">{row.Assignee_Count}</TableCell>
              <TableCell align="right">{formatNumber(row.Total_Attributable_Delay_Days)}</TableCell>
              <TableCell align="right">{row.Issues_With_Delay}</TableCell>
              <TableCell align="right">{formatNumber(row.Avg_Delay_Per_Issue_Days)}</TableCell>
              <TableCell align="right">{formatNumber(row.Delay_Share_Percent)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  if (loadingSummary) {
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
        Assignee Attributable Delay Report
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Analyze attributable delay distribution across Individual, Scrum, and Team levels.
      </Typography>
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'flex-end' }}>
        <MuiLink
          href="#assignee-delay-computation-logic"
          underline="hover"
          color="text.secondary"
          sx={{ fontSize: '0.75rem', opacity: 0.72 }}
        >
          Assignee Delay Computation Logic
        </MuiLink>
      </Box>

      {summary && (
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>Total Assignees</Typography>
                <Typography variant="h4">{summary.statistics.total_assignees}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>Total Delay Days</Typography>
                <Typography variant="h4">{formatNumber(summary.statistics.total_delay_days)}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>Issues with Delay</Typography>
                <Typography variant="h4">{summary.statistics.total_issues_with_delay}</Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>Avg Delay / Issue</Typography>
                <Typography variant="h4">{formatNumber(summary.statistics.avg_delay_per_issue_days)}</Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      <Paper>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="Individual" />
          <Tab label="Scrum" />
          <Tab label="Team" />
        </Tabs>

        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Team</InputLabel>
                <Select
                  label="Team"
                  value={(filters.team as string) || 'All'}
                  onChange={(event: SelectChangeEvent) => handleFilterChange('team', event.target.value)}
                >
                  <MenuItem value="All">All</MenuItem>
                  {(summary?.filters.teams ?? []).map((team) => (
                    <MenuItem key={team} value={team}>{team}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Scrum</InputLabel>
                <Select
                  label="Scrum"
                  value={(filters.scrum as string) || 'All'}
                  onChange={(event: SelectChangeEvent) => handleFilterChange('scrum', event.target.value)}
                >
                  <MenuItem value="All">All</MenuItem>
                  {(summary?.filters.scrums ?? []).map((scrum) => (
                    <MenuItem key={scrum} value={scrum}>{scrum}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Component</InputLabel>
                <Select
                  label="Component"
                  value={(filters.component as string) || 'All'}
                  onChange={(event: SelectChangeEvent) => handleFilterChange('component', event.target.value)}
                >
                  <MenuItem value="All">All</MenuItem>
                  {(summary?.filters.components ?? []).map((component) => (
                    <MenuItem key={component} value={component}>{component}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                fullWidth
                size="small"
                label="Search Assignee"
                value={(filters.search as string) ?? ''}
                onChange={(event) => handleFilterChange('search', event.target.value)}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Sort By</InputLabel>
                <Select
                  label="Sort By"
                  value={(filters.sort_by as string) || 'total_delay'}
                  onChange={(event: SelectChangeEvent) => handleFilterChange('sort_by', event.target.value)}
                >
                  <MenuItem value="total_delay">Total Delay</MenuItem>
                  <MenuItem value="issues">Issues with Delay</MenuItem>
                  <MenuItem value="avg_delay">Avg Delay / Issue</MenuItem>
                  <MenuItem value="assignee">Assignee Name</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>

          <Box sx={{ width: '100%', height: 380, color: 'primary.main', mb: 4 }}>
            <Typography variant="h6" gutterBottom>
              Top Assignees by Attributable Delay
            </Typography>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={individualChartData}
                margin={{ top: 16, right: 24, left: 8, bottom: 90 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" angle={-30} textAnchor="end" interval={0} height={100} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="delay"
                  name="Delay Days"
                  fill="currentColor"
                  cursor="pointer"
                  onClick={(payload: any) => {
                    const assigneeFromBar =
                      payload?.payload?.name ?? payload?.name ?? payload?.activeLabel ?? payload?.label;
                    if (typeof assigneeFromBar === 'string' && assigneeFromBar.trim()) {
                      handleOpenAssigneeDetails(assigneeFromBar);
                    }
                  }}
                />
              </BarChart>
            </ResponsiveContainer>
          </Box>

          {loadingAssignees ? (
            <Box display="flex" justifyContent="center" py={4}>
              <CircularProgress size={28} />
            </Box>
          ) : (
            <>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <HeaderWithTooltip
                        title="Assignee"
                        tooltip="JIRA assignee receiving attributable delay allocation."
                      />
                      <HeaderWithTooltip
                        title="Team"
                        tooltip="Team mapped to assignee from Resources configuration."
                      />
                      <HeaderWithTooltip
                        title="Scrum"
                        tooltip="Scrum mapped to assignee from Resources configuration."
                      />
                      <HeaderWithTooltip
                        title="Total Delay (Days)"
                        tooltip="Total delay days attributed to the assignee across delayed issues."
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Issues with Delay"
                        tooltip="Number of issues where this assignee has non-zero attributable delay."
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Avg Delay / Issue"
                        tooltip="Average attributable delay per delayed issue for this assignee."
                        align="right"
                      />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(assigneesData?.assignees ?? []).map((row) => (
                      <TableRow key={`${row.Assignee}-${row.Team}-${row.Scrum}`}>
                        <TableCell>
                          <MuiLink
                            component="button"
                            type="button"
                            underline="hover"
                            onClick={() => handleOpenAssigneeDetails(row.Assignee)}
                            sx={{ fontSize: '0.875rem' }}
                          >
                            {row.Assignee}
                          </MuiLink>
                        </TableCell>
                        <TableCell>{row.Team}</TableCell>
                        <TableCell>{row.Scrum}</TableCell>
                        <TableCell align="right">{formatNumber(row.Total_Attributable_Delay_Days)}</TableCell>
                        <TableCell align="right">{row.Issues_With_Delay}</TableCell>
                        <TableCell align="right">{formatNumber(row.Avg_Delay_Per_Issue_Days)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
              <TablePagination
                component="div"
                count={assigneesData?.pagination.total_count ?? 0}
                page={Math.max((assigneesData?.pagination.page ?? 1) - 1, 0)}
                onPageChange={handlePageChange}
                rowsPerPage={assigneesData?.pagination.page_size ?? 25}
                onRowsPerPageChange={handleRowsPerPageChange}
                rowsPerPageOptions={[10, 25, 50, 100]}
              />
            </>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          <Box sx={{ width: '100%', height: 380, color: 'secondary.main', mb: 4 }}>
            <Typography variant="h6" gutterBottom>
              Scrum-wise Attributable Delay
            </Typography>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={scrumChartData}
                margin={{ top: 16, right: 24, left: 8, bottom: 70 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" angle={-25} textAnchor="end" interval={0} height={80} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="delay" name="Delay Days" fill="currentColor" />
              </BarChart>
            </ResponsiveContainer>
          </Box>
          {renderGroupTable(summary?.by_scrum ?? [], 'Scrum')}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Box sx={{ width: '100%', height: 380, color: 'primary.main', mb: 4 }}>
            <Typography variant="h6" gutterBottom>
              Team-wise Attributable Delay
            </Typography>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={teamChartData}
                margin={{ top: 16, right: 24, left: 8, bottom: 70 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" angle={-25} textAnchor="end" interval={0} height={80} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="delay" name="Delay Days" fill="currentColor" />
              </BarChart>
            </ResponsiveContainer>
          </Box>
          {renderGroupTable(summary?.by_team ?? [], 'Team')}
        </TabPanel>
      </Paper>

      <Paper id="assignee-delay-computation-logic" sx={{ mt: 3, p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Assignee Delay Computation Logic
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          Delay is attributed by splitting each issue timeline using assignee change history and counting only the
          overlapping duration after the delay baseline.
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Baseline: max(Sprint End Date, First Active Status Date or Created Date). Effective End: first Done status
          change date for completed issues, otherwise current time. Attributable Delay: overlap of each assignee period
          with [Baseline, Effective End]. Epic issues and issues in Deferred/Defferred status are excluded from
          computation.
        </Typography>
      </Paper>

      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={handleCloseDrawer}
        PaperProps={{
          sx: {
            width: { xs: 360, sm: 760 },
            display: 'flex',
          },
        }}
      >
        <Box
          sx={{
            p: 2,
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
            <Typography variant="h6">{selectedAssignee || 'Assignee'} Delay Details</Typography>
            <IconButton onClick={handleCloseDrawer} size="small">
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>

          {issueDetailsLoading ? (
            <Box display="flex" justifyContent="center" alignItems="center" flex={1}>
              <CircularProgress size={28} />
            </Box>
          ) : issueDetailsError ? (
            <Alert severity="error" sx={{ mb: 2 }}>
              {issueDetailsError}
            </Alert>
          ) : (
            <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2, flexShrink: 0 }}>
                Issues with delay: {issueDetails?.total_issues ?? 0} • Total attributable delay:{' '}
                {formatNumber(issueDetails?.total_attributable_delay_days ?? 0)} days
              </Typography>

              <TableContainer sx={{ flex: 1, minHeight: 0 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <HeaderWithTooltip
                        title="Issue"
                        tooltip="JIRA issue key for which delay is attributable to the selected assignee."
                      />
                      <HeaderWithTooltip
                        title="Summary"
                        tooltip="Issue summary from JIRA issue snapshot."
                      />
                      <HeaderWithTooltip
                        title="Status"
                        tooltip="Current status of the issue."
                      />
                      <HeaderWithTooltip
                        title="Attributable Delay"
                        tooltip="Delay days assigned to this assignee for this issue based on assignment timeline overlap."
                        align="right"
                      />
                      <HeaderWithTooltip
                        title="Issue Delay"
                        tooltip="Total issue delay days after baseline, regardless of assignee split."
                        align="right"
                      />
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {issueTableRows.map((issue) => (
                      <TableRow key={issue.issue_key}>
                        <TableCell>
                          <Box
                            component="button"
                            onClick={() => openIssueTransitions(issue.issue_key)}
                            sx={{
                              background: 'none',
                              border: 'none',
                              padding: 0,
                              cursor: 'pointer',
                              color: 'primary.main',
                              fontFamily: 'monospace',
                              fontSize: '0.8125rem',
                              fontWeight: 600,
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 0.5,
                              '&:hover': { textDecoration: 'underline' },
                            }}
                          >
                            <HistoryIcon sx={{ fontSize: 14 }} />
                            {issue.issue_key}
                          </Box>
                        </TableCell>
                        <TableCell>{issue.summary || '-'}</TableCell>
                        <TableCell>{issue.status || '-'}</TableCell>
                        <TableCell align="right">{formatNumber(issue.attributable_delay_days)}</TableCell>
                        <TableCell align="right">{formatNumber(issue.issue_delay_days)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </Box>
          )}
        </Box>
      </Drawer>

      {/* Issue Transition History — layered drawer (zIndex above assignee drawer) */}
      <Drawer
        anchor="right"
        open={transitionDrawerOpen}
        onClose={() => setTransitionDrawerOpen(false)}
        sx={{ zIndex: (theme) => theme.zIndex.modal + 5 }}
        PaperProps={{
          sx: {
            width: { xs: '100%', md: 720 },
            p: 2.5,
            display: 'flex',
            flexDirection: 'column',
          },
        }}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
            <Typography variant="h6">Issue Transition History</Typography>
            <IconButton size="small" onClick={() => setTransitionDrawerOpen(false)}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Stack>

          {selectedTransitionKey && (
            <Chip
              label={`Issue: ${selectedTransitionKey}`}
              color="secondary"
              variant="outlined"
              size="small"
              sx={{ mb: 1.5, alignSelf: 'flex-start' }}
            />
          )}

          {loadingTransitions ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress size={24} />
            </Box>
          ) : transitionError ? (
            <Alert severity="error" sx={{ mb: 1 }}>{transitionError}</Alert>
          ) : transitionDetails ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
                <Chip label={`Delay: ${formatDelayWithUnit(transitionDetails.delay_computation.delay_days)}`} size="small" variant="outlined" />
                <Chip label={`Basis: ${transitionDetails.delay_computation.basis}`} size="small" variant="outlined" />
                <Chip label={`Status: ${transitionDetails.issue.status}`} size="small" variant="outlined" />
              </Stack>

              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                {transitionDetails.delay_computation.formula}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
                Sprint End: {formatDateAsYyyyMmDd(transitionDetails.delay_computation.sprint_end_date)}
                {' | '}Delay Baseline: {formatDateAsYyyyMmDd(transitionDetails.delay_computation.delay_baseline_date || transitionDetails.delay_computation.sprint_end_date)} ({transitionDetails.delay_computation.delay_baseline_source || 'sprint_end_date'})
                {' | '}Effective End: {formatDateAsYyyyMmDd(transitionDetails.delay_computation.effective_end_date)}
              </Typography>

              <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Assignment Timeline</Typography>
              {transitionDetails.assignee_timeline.length > 0 ? (
                <TableContainer sx={{ maxHeight: 220, mb: 1.5 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 140 }}>Assignee</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 120 }}>From</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', minWidth: 120 }}>To</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Duration (d)</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }} align="right">Delay Attributed (d)</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {transitionDetails.assignee_timeline.map((row, i) => (
                        <TableRow key={`${row.assignee}-${row.period_start}-${i}`} hover>
                          <TableCell>{row.assignee || 'Unassigned'}</TableCell>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(row.period_start)}</TableCell>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(row.period_end)}</TableCell>
                          <TableCell align="right">{formatDelayInDays(row.duration_days)}</TableCell>
                          <TableCell align="right">{formatDelayInDays(row.delay_days)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info" sx={{ mb: 1.5 }}>No assignee timeline available for this issue.</Alert>
              )}

              <Typography variant="subtitle2" sx={{ mb: 0.75 }}>Transition Events</Typography>
              {transitionDetails.transitions.length > 0 ? (
                <TableContainer sx={{ flex: 1, minHeight: 0 }}>
                  <Table stickyHeader size="small" sx={{ tableLayout: 'fixed' }}>
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 'bold', width: 130 }}>Change Date</TableCell>
                        <TableCell sx={{ fontWeight: 'bold', width: 120 }} align="right">
                          <Box sx={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.15 }}>
                            <span>Accumulated</span>
                            <span>Delay (d)</span>
                          </Box>
                        </TableCell>
                        <TableCell sx={{ fontWeight: 'bold', width: 110 }}>Field</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>From</TableCell>
                        <TableCell sx={{ fontWeight: 'bold' }}>To</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {transitionDetails.transitions.map((tr, i) => (
                        <TableRow key={`${tr.change_date}-${tr.field}-${i}`} hover>
                          <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateAsYyyyMmDd(tr.change_date)}</TableCell>
                          <TableCell align="right">{formatDelayInDays(tr.accumulated_delay_days)}</TableCell>
                          <TableCell>{tr.field || 'NA'}</TableCell>
                          <TableCell>{tr.from_value || 'NA'}</TableCell>
                          <TableCell>{tr.to_value || 'NA'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">No transition history found for this issue.</Alert>
              )}
            </Box>
          ) : null}
        </Box>
      </Drawer>
    </Box>
  );
};

export default AssigneeDelayReportPage;
