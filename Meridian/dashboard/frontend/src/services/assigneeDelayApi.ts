import axios from 'axios';

const API_BASE_URL = '';

export interface AssigneeDelayRow {
  Assignee: string;
  Team: string;
  Scrum: string;
  Total_Attributable_Delay_Days: number;
  Issues_With_Delay: number;
  Avg_Delay_Per_Issue_Days: number;
}

export interface AssigneeDelayGroupRow {
  Team?: string;
  Scrum?: string;
  Assignee_Count: number;
  Total_Attributable_Delay_Days: number;
  Issues_With_Delay: number;
  Avg_Delay_Per_Issue_Days: number;
  Delay_Share_Percent: number;
}

export interface AssigneeDelaySummaryResponse {
  statistics: {
    total_assignees: number;
    total_delay_days: number;
    total_issues_with_delay: number;
    avg_delay_per_issue_days: number;
    avg_delay_per_assignee_days: number;
    mapped_assignees: number;
    unmapped_assignees: number;
  };
  by_team: AssigneeDelayGroupRow[];
  by_scrum: AssigneeDelayGroupRow[];
  top_assignees: AssigneeDelayRow[];
  filters: {
    teams: string[];
    scrums: string[];
    components: string[];
  };
  data_timestamp: string | null;
}

export interface AssigneeDelayAssigneesResponse {
  assignees: AssigneeDelayRow[];
  top_assignees: AssigneeDelayRow[];
  pagination: {
    page: number;
    page_size: number;
    total_count: number;
    total_pages: number;
  };
  applied_filters: {
    team: string;
    scrum: string;
    component: string;
    search: string;
    sort_by: string;
    sort_order: string;
  };
}

export interface AssigneeDelayFilters {
  page?: number;
  page_size?: number;
  team?: string;
  scrum?: string;
  component?: string;
  search?: string;
  sort_by?: 'total_delay' | 'issues' | 'avg_delay' | 'assignee';
  sort_order?: 'asc' | 'desc';
}

export interface AssigneeDelayIssueRow {
  issue_key: string;
  summary: string;
  issue_type: string;
  status: string;
  team: string;
  scrum: string;
  attributable_delay_days: number;
  issue_delay_days: number;
  delay_baseline_date: string;
  effective_end_date: string;
}

export interface AssigneeDelayIssueDetailsResponse {
  assignee: string;
  issues: AssigneeDelayIssueRow[];
  total_issues: number;
  total_attributable_delay_days: number;
}

export const getAssigneeDelaySummary = async (topN: number = 15): Promise<AssigneeDelaySummaryResponse> => {
  const response = await axios.get<AssigneeDelaySummaryResponse>(
    `${API_BASE_URL}/api/assignee-delay/summary`,
    { params: { top_n: topN } }
  );
  return response.data;
};

export const getAssigneeDelayAssignees = async (
  filters: AssigneeDelayFilters = {}
): Promise<AssigneeDelayAssigneesResponse> => {
  const response = await axios.get<AssigneeDelayAssigneesResponse>(
    `${API_BASE_URL}/api/assignee-delay/assignees`,
    { params: filters }
  );
  return response.data;
};

export const getAssigneeDelayIssueDetails = async (
  assignee: string
): Promise<AssigneeDelayIssueDetailsResponse> => {
  const response = await axios.get<AssigneeDelayIssueDetailsResponse>(
    `${API_BASE_URL}/api/assignee-delay/assignee-issues`,
    { params: { assignee } }
  );
  return response.data;
};
