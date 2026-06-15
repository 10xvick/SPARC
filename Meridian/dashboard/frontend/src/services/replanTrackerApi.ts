import axios from 'axios';

const API_BASE_URL = '';

// Interfaces
export interface ReplanIssue {
  Key: string;
  Project: string;
  Team: string;
  Scrum: string;
  Assignee: string;
  Issue_Type: string;
  Priority: string;
  Component?: string;
  Story_Points: number;
  Current_Sprint: string;
  Current_Status: string;
  Created: string;
  Replan_Count: number;
  Total_Sprints: number;
  First_Sprint: string;
  Final_Sprint: string;
  Sprint_Timeline: string;
  Epic_Key?: string | null;
  Epic_Summary?: string | null;
  Description?: string | null;
}

export interface IssueSummaryByType {
  Issue_Type: string;
  Issue_Count: number;
  Total_Replans: number;
  Avg_Replans_Per_Issue: number;
  Max_Replans: number;
  Avg_Sprints_Per_Issue: number;
  Total_Story_Points: number;
}

export interface TeamSummary {
  Team: string;
  Issue_Count: number;
  Total_Replans: number;
  Avg_Replans_Per_Issue: number;
  Max_Replans: number;
  Avg_Sprints_Per_Issue: number;
  Total_Story_Points: number;
  'Replan_Rate_%': number;
}

export interface ScrumSummary {
  Scrum: string;
  Issue_Count: number;
  Total_Replans: number;
  Avg_Replans_Per_Issue: number;
  Max_Replans: number;
  Avg_Sprints_Per_Issue: number;
  Total_Story_Points: number;
  'Replan_Rate_%': number;
}

export interface PrioritySummary {
  Issue_Type: string;
  Priority: string;
  Count: number;
  Total_Replans: number;
  Avg_Replans: number;
}

export interface ReplanSummary {
  by_issue_type: IssueSummaryByType[];
  by_team: TeamSummary[];
  by_scrum: ScrumSummary[];
  by_priority: PrioritySummary[];
}

export interface ReplanStatistics {
  total_issues: number;
  total_replans: number;
  issues_with_replans: number;
  issues_without_replans: number;
  replan_rate_percent: number;
  avg_replans_per_issue: number;
  avg_replans_when_replanned: number;
  max_replans: number;
  median_replans: number;
  avg_sprints_per_issue: number;
  total_story_points: number;
  by_issue_type: {
    [key: string]: {
      count: number;
      total_replans: number;
    };
  };
}

export interface IssuesResponse {
  issues: ReplanIssue[];
  pagination: {
    page: number;
    page_size: number;
    total_count: number;
    total_pages: number;
  };
  filters: {
    teams: string[];
    scrums: string[];
    issue_types: string[];
    priorities: string[];
    components: string[];
    projects: string[];
    statuses: string[];
  };
}

export interface HighReplansResponse {
  high_replan_issues: ReplanIssue[];
  count: number;
}

export interface IssueFilters {
  page?: number;
  page_size?: number;
  team?: string;
  scrum?: string;
  issue_type?: string;
  priority?: string;
  component?: string;
  project?: string;
  min_replans?: number;
  current_status?: string;
}

export interface ReplanHistoryEntry {
  sequence: number;
  sprint: string;
  date: string;
  is_replan: boolean;
}

export interface IssueReplanDetails {
  issue_key: string;
  project: string;
  team: string;
  scrum: string;
  assignee: string;
  issue_type: string;
  priority: string;
  story_points: number;
  current_sprint: string;
  current_status: string;
  created: string;
  replan_count: number;
  total_sprints: number;
  first_sprint: string | null;
  final_sprint: string | null;
  replan_history: ReplanHistoryEntry[];
  description?: string | null;
  epic_key?: string | null;
  epic_summary?: string | null;
}

// API Functions
export const getReplanSummary = async (): Promise<ReplanSummary> => {
  const response = await axios.get(`${API_BASE_URL}/api/replan-tracker/summary`);
  return response.data;
};

export const getReplanIssues = async (filters: IssueFilters = {}): Promise<IssuesResponse> => {
  const response = await axios.get(`${API_BASE_URL}/api/replan-tracker/issues`, {
    params: filters
  });
  return response.data;
};

export const getHighReplanIssues = async (limit: number = 10): Promise<HighReplansResponse> => {
  const response = await axios.get(`${API_BASE_URL}/api/replan-tracker/high-replans`, {
    params: { limit }
  });
  return response.data;
};

export const getReplanStatistics = async (): Promise<ReplanStatistics> => {
  const response = await axios.get(`${API_BASE_URL}/api/replan-tracker/statistics`);
  return response.data;
};

export const getTrendsByTeam = async (): Promise<{ teams: TeamSummary[] }> => {
  const response = await axios.get(`${API_BASE_URL}/api/replan-tracker/trends-by-team`);
  return response.data;
};

export const getIssueReplanDetails = async (issueKey: string): Promise<IssueReplanDetails> => {
  const response = await axios.get(`${API_BASE_URL}/api/replan-tracker/issue/${issueKey}/replan-details`);
  return response.data;
};

export const exportReplanIssuesCsv = async (filters: IssueFilters = {}): Promise<Blob> => {
  const { page: _page, page_size: _pageSize, ...exportFilters } = filters;
  const response = await axios.get(`${API_BASE_URL}/api/replan-tracker/issues/export/csv`, {
    params: exportFilters,
    responseType: 'blob',
  });
  return response.data;
};
