// API client for reports
import axios from 'axios'

const API_BASE = '/api/reports'

export interface MatrixReportData {
  name: string
  [key: string]: string | number  // Dynamic KPI columns
}

export interface MatrixReportKpiMeta {
  kpp_goals: string
  measurement_criteria: string
  tool: string
  measure: string
  type_code: string
  goal_direction: 'Maximize' | 'Minimize'
  goal_type_category: string
  target: number
  prorated_target: number
  prorate: boolean
  weekly_target: number
  quarterly_target: number
  annual_target: number
}

export interface MatrixReportResponse {
  success: boolean
  data: MatrixReportData[]
  kpis: string[]
  kpi_meta?: Record<string, MatrixReportKpiMeta | null>
  period: string
  sort_by: string
  applied_team: string
  available_teams: string[]
  total_individuals: number
  total_kpis: number
}

export interface RoleKpiApplicabilityItem {
  index: string
  name: string
  source_role: string
  goal_type: string
  type_code: string
  aggregation_type: string
  measurement_criteria: string
  tool: string
  measure: string
  weekly_target: string
  quarterly_target: string
  annual_target: string
  prorate?: boolean
  implemented: boolean
  implementation_status: string
  implementation_type: string
  implementation_details: string
  base_kpi: string
}

export interface RoleKpiApplicabilityResponse {
  success: boolean
  roles: string[]
  selected_role: string
  shared_role_buckets: string[]
  applied_role_buckets: string[]
  data: RoleKpiApplicabilityItem[]
  total_kpis: number
  implemented_kpis: number
  pending_kpis: number
  source_counts: Record<string, number>
}

export interface JiraEpicListItem {
  epic_key: string
  summary: string
  status: string
  priority: string
  assignee: string
  team: string
  sprint: string
  story_points: number
  created: string
  updated: string
  total_related_issues: number
  total_descendants: number
  done_descendants: number
  open_descendants: number
  overdue_descendants: number
  avg_delay_days: number
}

export interface JiraEpicsListResponse {
  success: boolean
  data: JiraEpicListItem[]
  total_epics: number
  pagination?: {
    page: number
    page_size: number
    total_pages: number
    total_items: number
    has_next: boolean
    has_previous: boolean
  }
  applied_filters: {
    team: string
    state: string
    sprint: string
    assignee: string
    component: string
    search: string
  }
  filters: {
    teams: string[]
    states: string[]
    sprints: string[]
    assignees: string[]
    components: string[]
  }
  available_teams?: string[]
}

export interface JiraEpicTreeNode {
  key: string
  parent: string
  issue_type: string
  summary: string
  status: string
  priority: string
  story_points: number
  assignee: string
  team: string
  sprint: string
  created: string
  updated: string
  sprint_end_date: string
  completion_date: string
  age_days: number
  delay_days: number
  initial_sprint?: string
  initial_allocation_date?: string
  planned_duration_days?: number | null
  actual_duration_days?: number | null
  slippage_days?: number | null
  is_done: boolean
  is_overdue: boolean
  children: JiraEpicTreeNode[]
}

export interface JiraEpicAssigneeBreakdown {
  assignee: string
  team: string
  total_issues: number
  done_issues: number
  in_progress_issues: number
  todo_issues: number
  delayed_issues: number
  avg_age_days: number
  avg_delay_days: number
  max_delay_days: number
  initial_assigned_date: string
  initial_sprint: string
  next_transition_field: string
  next_transition_from: string
  next_transition_to: string
  next_transition_by: string
  next_transition_date: string
  next_transition_summary: string
}

export interface JiraEpicIssueTypeBreakdown {
  issue_type: string
  total_issues: number
  done_issues: number
  open_issues: number
  delayed_issues: number
  avg_delay_days: number
  max_delay_days: number
}

export interface JiraEpicChildTiming {
  key: string
  parent: string
  summary: string
  issue_type: string
  assignee: string
  team: string
  status: string
  initial_sprint: string
  initial_allocation_date: string
  planned_days: number | null
  actual_days: number | null
  slippage_days: number | null
}

export interface JiraEpicTimingSummary {
  total_children: number
  timed_children: number
  overrun_children: number
  on_track_children: number
  avg_planned_days: number
  avg_actual_days: number
  avg_slippage_days: number
  truncated: boolean
  returned_children: number
}

export interface JiraIssueTransitionRow {
  change_date: string
  accumulated_delay_days?: number | null
  field: string
  from_value: string
  to_value: string
  changed_by: string
}

export interface JiraIssueDelayComputation {
  formula: string
  basis: string
  sprint_end_date: string
  delay_baseline_date?: string
  delay_baseline_source?: string
  effective_end_date: string
  completion_date: string
  current_reference_date: string
  raw_delay_days: number | null
  delay_days: number
}

export interface JiraIssueAssigneeTimelineRow {
  assignee: string
  period_start: string
  period_end: string
  duration_days: number
  delay_days: number
}

export interface JiraIssueTransitionsResponse {
  success: boolean
  issue: {
    key: string
    summary: string
    issue_type: string
    status: string
    assignee: string
    team: string
    sprint: string
    created: string
    updated: string
    sprint_end_date: string
    completion_date: string
    is_done: boolean
    delay_days: number
  }
  delay_computation: JiraIssueDelayComputation
  assignee_timeline: JiraIssueAssigneeTimelineRow[]
  transitions: JiraIssueTransitionRow[]
  transition_count: number
}

export interface JiraEpicDetailsResponse {
  success: boolean
  epic: {
    key: string
    summary: string
    status: string
    priority: string
    assignee: string
    team: string
    sprint: string
    story_points: number
    created: string
    updated: string
    completion_date: string
    delay_days: number
  }
  tree: JiraEpicTreeNode
  analysis: {
    total_related_issues: number
    total_descendants: number
    done_issues: number
    open_issues: number
    delayed_issues: number
    avg_age_days: number
    avg_delay_days: number
    max_delay_days: number
    status_counts: Record<string, number>
    assignee_breakdown: JiraEpicAssigneeBreakdown[]
    issue_type_breakdown: JiraEpicIssueTypeBreakdown[]
    timing_summary: JiraEpicTimingSummary
    child_timing: JiraEpicChildTiming[]
  }
}

export interface EmployeePeriodScore {
  overall: number
  input: number
  output: number
  quality: number
  hygiene: number
}

export interface EmployeeScoreComparisonData {
  name: string
  sapid: string
  team: string
  scrum: string
  primary_role: string
  secondary_role: string
  scores: {
    Weekly: EmployeePeriodScore
    Quarterly: EmployeePeriodScore
    Annual: EmployeePeriodScore
  }
}

export interface EmployeeScoreComparisonResponse {
  success: boolean
  data: EmployeeScoreComparisonData[]
  score_display_thresholds?: {
    green_min: number
    orange_min: number
    red_max: number
  }
  category_weightages?: {
    input: number
    output: number
    quality: number
    hygiene: number
  }
  available_filters: {
    teams: string[]
    scrums: string[]
    primary_roles: string[]
    secondary_roles: string[]
  }
  applied_filters: {
    team: string
    scrum: string
    primary_role: string
    secondary_role: string
  }
  as_of_date?: string
  total_employees: number
}

export interface GitActivityPersonRow {
  date: string
  name: string
  author_email: string
  sapid: string
  team: string
  scrum: string
  daily_counts: Record<string, number>
  metric_total: number
  merge_commits: number
  non_merge_commits: number
  git_activity_score?: {
    overall_score: number
    productivity_score: number
    consistency_score: number
    collaboration_score: number
    actual: {
      productivity_per_working_day: number
      consistency_ratio: number
      collaboration_merge_ratio: number
    }
    target: {
      productivity_per_working_day: number
      consistency_ratio: number
      collaboration_merge_ratio: number
    }
    active_working_days: number
  }
}

export interface GitActivityReportResponse {
  success: boolean
  data: GitActivityPersonRow[]
  date_columns: string[]
  score_display_thresholds?: {
    green_min: number
    orange_min: number
    red_max: number
  }
  metric_label: 'Total Commits' | 'Merges' | 'Commits' | 'Lines Added' | 'Lines Deleted' | 'Lines Changed' | 'Files Changed' | 'Repos Touched'
  summary: {
    total_rows: number
    metric_total: number
    git_activity_scorecard?: {
      overall_score: number
      productivity_score: number
      consistency_score: number
      collaboration_score: number
      weights: {
        productivity: number
        consistency: number
        collaboration: number
      }
      strictness: 'balanced'
      display_format: 'integer'
      baseline_months: string[]
      selected_month: string
      gauge_layout: 'overall+3-components'
      rows_scored: number
    }
  }
  available_months: string[]
  selected_month: string
  available_filters: {
    teams: string[]
    scrums: string[]
  }
  applied_filters: {
    month: string
    team: string
    scrum: string
    activity_type: 'total_commits' | 'merges' | 'commits' | 'lines_added' | 'lines_deleted' | 'lines_changed' | 'files_changed' | 'repos_touched'
    employee_scope: 'active' | 'inactive' | 'all'
  }
}

export interface GitActivityMetadataResponse {
  success: boolean
  available_months: string[]
  selected_month: string
  available_filters: {
    teams: string[]
    scrums: string[]
  }
}

export interface GitActivityCommitDetail {
  commit_sha: string
  date: string
  author: string
  author_email: string
  repository: string
  message: string
  jira_id: string
  files_changed: number
  lines_added: number
  lines_deleted: number
  lines_changed: number
  pr_number: string
  approver: string
  review_comments: number
  is_merge: boolean
}

export interface GitActivityEmployeeDetailsResponse {
  success: boolean
  selected_month: string
  person: {
    name: string
    sapid: string
    author_email: string
    team: string
    scrum: string
  }
  summary: {
    total_commits: number
    merge_commits: number
    non_merge_commits: number
    total_lines_changed: number
    total_files_changed: number
  }
  commits: GitActivityCommitDetail[]
}

export interface GitActivityDetailedExportStatus {
  success: boolean
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress_percent: number
  message: string
  current_step: string
  started_at: string
  completed_at: string
  error_message: string
  download_ready: boolean
  download_filename: string
  selected_month: string
  team: string
  scrum: string
  activity_type: 'total_commits' | 'merges' | 'commits' | 'lines_added' | 'lines_deleted' | 'lines_changed' | 'files_changed' | 'repos_touched'
  employee_scope: 'active' | 'inactive' | 'all'
  rows_written: number
}

export interface GitActivityDetailedExportStartResponse {
  success: boolean
  job_id: string
  status: GitActivityDetailedExportStatus
}

export interface GitActivityCommitFileDetail {
  component: string
  filepath: string
  filename: string
  file_extension: string
  status: string
  lines_added: number
  lines_deleted: number
  lines_changed: number
}

export interface GitActivityCommitComponentSummary {
  component: string
  files_count: number
  lines_added: number
  lines_deleted: number
  lines_changed: number
}

export interface GitActivityCommitFileDetailsResponse {
  success: boolean
  selected_month: string
  warning?: string
  commit: {
    commit_sha: string
    repository: string
    date: string
    author: string
    author_email: string
    message: string
    jira_id: string
    person: {
      name: string
      sapid: string
      team: string
      scrum: string
    }
  }
  summary: {
    files_count: number
    lines_added: number
    lines_deleted: number
    lines_changed: number
  }
  components: GitActivityCommitComponentSummary[]
  files: GitActivityCommitFileDetail[]
}

export interface UdeInstallationsReportRow {
  current_date: string
  week: string
  month: string
  quarter: string
  year: string
  sapid: string
  name: string
  team: string
  scrum: string
  row_type: 'EMPLOYEE_SUMMARY' | 'DEVICE' | 'DEVICE_EXCEPTION'
  compliance_status: 'COMPLIANT' | 'NON_COMPLIANT'
  current_version: string
  current_delay_days: number
  total_devices: number
  compliant_devices: number
  non_compliant_devices: number
  device_id: string
  device_label: string
  device_version: string
  device_delay_days: number
}

export interface UdeInstallationsReportResponse {
  success: boolean
  data: UdeInstallationsReportRow[]
  summary: {
    total_rows: number
    filtered_rows: number
    total_employees: number
    fully_compliant_employees: number
    employee_compliance_percent: number
    total_devices: number
    compliant_devices: number
    device_compliance_percent: number
  }
  available_filters: {
    teams: string[]
    scrums: string[]
    versions: string[]
    compliance: Array<'all' | 'compliant' | 'non_compliant'>
  }
  applied_filters: {
    team: string
    scrum: string
    version: string
    compliance_filter: 'all' | 'compliant' | 'non_compliant'
    employee_scope: 'active' | 'all'
  }
  default_compliance_filter: 'non_compliant'
}

export interface UdeInstallationsFiltersResponse {
  teams: string[]
  scrums: string[]
  versions: string[]
  compliance: Array<'all' | 'compliant' | 'non_compliant'>
}

export interface UdeInstallationDetailRow {
  sapid: string
  name: string
  team: string
  scrum: string
  device_id: string
  device_label: string
  ude_version: string
  installed_date: string
  release_date: string
  computed_delay_days: number
  is_latest_target_version: boolean
}

export interface UdeInstallationEmployeeDetailsResponse {
  success: boolean
  employee: {
    sapid: string
    name: string
    team: string
    scrum: string
  }
  latest_target_version: string
  data: UdeInstallationDetailRow[]
}

export const reportsApi = {
  async getMatrixReport(params: {
    period?: string
    kpis?: string
    sort_by?: string
    team?: string
    as_of_date?: string
  }): Promise<MatrixReportResponse> {
    const response = await axios.get(`${API_BASE}/matrix`, { params })
    return response.data
  },

  async getAvailableKpis(): Promise<{ success: boolean, kpis: string[] }> {
    const response = await axios.get(`${API_BASE}/available-kpis`)
    return response.data
  },

  async getRoleKpiApplicabilityReport(role?: string): Promise<RoleKpiApplicabilityResponse> {
    const response = await axios.get(`${API_BASE}/role-kpi-applicability`, {
      params: role ? { role } : undefined
    })
    return response.data
  },

  async getJiraEpics(params?: {
    team?: string
    state?: string
    sprint?: string
    assignee?: string
    component?: string
    search?: string
    page?: number
    page_size?: number
  }): Promise<JiraEpicsListResponse> {
    const response = await axios.get(`${API_BASE}/jira-epics`, { params })
    return response.data
  },

  async getJiraEpicDetails(epicKey: string): Promise<JiraEpicDetailsResponse> {
    const response = await axios.get(`${API_BASE}/jira-epics/${encodeURIComponent(epicKey)}/details`)
    return response.data
  },

  async getJiraIssueTransitions(issueKey: string): Promise<JiraIssueTransitionsResponse> {
    const response = await axios.get(`${API_BASE}/jira-issues/${encodeURIComponent(issueKey)}/transitions`)
    return response.data
  },

  async getEmployeeScoreComparison(params?: {
    team?: string
    scrum?: string
    primary_role?: string
    secondary_role?: string
    as_of_date?: string
  }): Promise<EmployeeScoreComparisonResponse> {
    const response = await axios.get(`${API_BASE}/employee-score-comparison`, { params })
    return response.data
  },

  async getGitActivityReport(params?: {
    month?: string
    team?: string
    scrum?: string
    activity_type?: 'total_commits' | 'merges' | 'commits' | 'lines_added' | 'lines_deleted' | 'lines_changed' | 'files_changed' | 'repos_touched'
    employee_scope?: 'active' | 'inactive' | 'all'
  }): Promise<GitActivityReportResponse> {
    const response = await axios.get(`${API_BASE}/git-activity`, { params })
    return response.data
  },

  async getGitActivityMetadata(): Promise<GitActivityMetadataResponse> {
    const response = await axios.get(`${API_BASE}/git-activity/metadata`)
    return response.data
  },

  async getGitActivityEmployeeDetails(params: {
    month: string
    sapid?: string
    author_email?: string
  }): Promise<GitActivityEmployeeDetailsResponse> {
    const response = await axios.get(`${API_BASE}/git-activity/employee-details`, { params })
    return response.data
  },

  async startGitActivityDetailedExport(params: {
    month: string
    team: string
    scrum?: string
    activity_type?: 'total_commits' | 'merges' | 'commits' | 'lines_added' | 'lines_deleted' | 'lines_changed' | 'files_changed' | 'repos_touched'
    employee_scope?: 'active' | 'inactive' | 'all'
  }): Promise<GitActivityDetailedExportStartResponse> {
    const response = await axios.post(`${API_BASE}/git-activity/export-details`, null, { params })
    return response.data
  },

  async getGitActivityDetailedExportStatus(jobId: string): Promise<GitActivityDetailedExportStatus> {
    const response = await axios.get(`${API_BASE}/git-activity/export-details/status`, {
      params: { job_id: jobId },
    })
    return response.data
  },

  async downloadGitActivityDetailedExport(jobId: string): Promise<Blob> {
    const response = await axios.get(`${API_BASE}/git-activity/export-details/download`, {
      params: { job_id: jobId },
      responseType: 'blob',
    })
    return response.data
  },

  async getGitActivityCommitFileDetails(params: {
    month: string
    commit_sha: string
    repository?: string
    sapid?: string
    author_email?: string
  }): Promise<GitActivityCommitFileDetailsResponse> {
    const response = await axios.get(`${API_BASE}/git-activity/commit-file-details`, { params })
    return response.data
  },

  async getUdeInstallationsFilters(params?: {
    employee_scope?: 'active' | 'all'
  }): Promise<UdeInstallationsFiltersResponse> {
    const response = await axios.get(`${API_BASE}/ude-installations/filters`, { params })
    return response.data
  },

  async getUdeInstallationsReport(params?: {
    team?: string
    scrum?: string
    version?: string
    compliance_filter?: 'all' | 'compliant' | 'non_compliant'
    employee_scope?: 'active' | 'all'
  }): Promise<UdeInstallationsReportResponse> {
    const response = await axios.get(`${API_BASE}/ude-installations`, { params })
    return response.data
  },

  async getUdeInstallationEmployeeDetails(
    sapid: string,
    params?: {
      employee_scope?: 'active' | 'all'
    }
  ): Promise<UdeInstallationEmployeeDetailsResponse> {
    const response = await axios.get(`${API_BASE}/ude-installations/${encodeURIComponent(sapid)}/details`, { params })
    return response.data
  }
}
