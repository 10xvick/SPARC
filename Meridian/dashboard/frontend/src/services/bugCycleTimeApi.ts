/**
 * Bug Cycle Time API Client
 * Handles API calls for bug cycle time analysis data
 */
import axios from 'axios';

const API_BASE_URL = '';

// TypeScript interfaces
export interface BugCycleTime {
  Key: string;
  Project: string;
  Team: string;
  Scrum: string;
  Assignee: string;
  Priority: string;
  Current_Status: string;
  Created: string;
  Total_Cycle_Time_Days: number;
  Total_Cycle_Time_Hours: number;
  Transition_Count: number;
  Rework_Count: number;
  First_Status: string;
  Final_Status: string;
  [key: string]: any; // For dynamic Time_in_* columns
}

export interface SummaryData {
  Priority?: string;
  Team?: string;
  Scrum?: string;
  Bug_Count: number;
  Avg_Cycle_Time_Days: number;
  Median_Cycle_Time_Days: number;
  Min_Cycle_Time_Days: number;
  Max_Cycle_Time_Days: number;
  Avg_Transitions: number;
  Avg_Rework_Count: number;
}

export interface BugCycleTimeSummary {
  by_priority: SummaryData[];
  by_team: SummaryData[];
  by_scrum: SummaryData[];
}

export interface BugsResponse {
  bugs: BugCycleTime[];
  pagination: {
    page: number;
    page_size: number;
    total_items: number;
    total_pages: number;
  };
  filters: {
    teams: string[];
    scrums: string[];
    priorities: string[];
    projects: string[];
  };
}

export interface TopIssuesResponse {
  top_issues: BugCycleTime[];
  sort_by: string;
  limit: number;
}

export interface Statistics {
  total_bugs: number;
  avg_cycle_time_days: number;
  median_cycle_time_days: number;
  min_cycle_time_days: number;
  max_cycle_time_days: number;
  avg_transitions: number;
  avg_rework_count: number;
  bugs_with_rework: number;
  rework_percentage: number;
}

export interface AssigneeRework {
  assignee: string;
  team: string;
  bugs_with_rework: number;
  total_rework_count: number;
  avg_rework_per_bug: number;
  avg_cycle_time: number;
}

export interface ReworkByAssigneeResponse {
  top_assignees: AssigneeRework[];
  total_assignees_with_rework: number;
  total_rework_cases: number;
}

export interface BugFilters {
  team?: string;
  scrum?: string;
  priority?: string;
  project?: string;
  min_cycle_time?: number;
  max_cycle_time?: number;
  page?: number;
  page_size?: number;
}

/**
 * Get bug cycle time summary statistics
 */
export const getBugCycleTimeSummary = async (): Promise<BugCycleTimeSummary> => {
  const response = await axios.get<BugCycleTimeSummary>(
    `${API_BASE_URL}/api/bug-cycle-time/summary`
  );
  return response.data;
};

/**
 * Get bugs with filtering and pagination
 */
export const getBugs = async (filters: BugFilters = {}): Promise<BugsResponse> => {
  const params = new URLSearchParams();
  
  if (filters.team) params.append('team', filters.team);
  if (filters.scrum) params.append('scrum', filters.scrum);
  if (filters.priority) params.append('priority', filters.priority);
  if (filters.project) params.append('project', filters.project);
  if (filters.min_cycle_time !== undefined) params.append('min_cycle_time', filters.min_cycle_time.toString());
  if (filters.max_cycle_time !== undefined) params.append('max_cycle_time', filters.max_cycle_time.toString());
  if (filters.page) params.append('page', filters.page.toString());
  if (filters.page_size) params.append('page_size', filters.page_size.toString());
  
  const response = await axios.get<BugsResponse>(
    `${API_BASE_URL}/api/bug-cycle-time/bugs?${params.toString()}`
  );
  return response.data;
};

/**
 * Get top issues by cycle time, rework count, or transitions
 */
export const getTopIssues = async (
  limit: number = 10,
  sortBy: 'cycle_time' | 'rework_count' | 'transitions' = 'cycle_time'
): Promise<TopIssuesResponse> => {
  const response = await axios.get<TopIssuesResponse>(
    `${API_BASE_URL}/api/bug-cycle-time/top-issues`,
    { params: { limit, sort_by: sortBy } }
  );
  return response.data;
};

/**
 * Get overall statistics
 */
export const getStatistics = async (): Promise<Statistics> => {
  const response = await axios.get<Statistics>(
    `${API_BASE_URL}/api/bug-cycle-time/statistics`
  );
  return response.data;
};

/**
 * Get rework statistics by assignee
 */
export const getReworkByAssignee = async (limit: number = 15): Promise<ReworkByAssigneeResponse> => {
  const response = await axios.get<ReworkByAssigneeResponse>(
    `${API_BASE_URL}/api/bug-cycle-time/rework-by-assignee`,
    { params: { limit } }
  );
  return response.data;
};
