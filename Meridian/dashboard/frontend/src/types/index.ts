// TypeScript types for the dashboard

export interface Employee {
  ref?: string
  sapid: string
  name: string
  team: string
  scrum: string
  primary_role: string
  secondary_role?: string
  reporting?: number
  manager?: string
  manager_name?: string
  email?: string
  resource_sheet_name?: string
  resource_sheet_id?: string
  jira_name?: string
  git_email?: string
  udeid?: string
  tacid?: string
  url?: string
  github_name?: string
  copilot_user?: string
  employment_status?: 'Active' | 'Inactive'
  start_date?: string
  create_rbac_user?: boolean
  last_modified?: string
}

export interface Role {
  index: string
  name: string
  primary_role: string
  secondary_role?: string
  goal_type: string
  kpp_goals?: string
  measurement_criteria?: string
  tool?: string
  measure?: string
  weekly_target: number
  quarterly_target: number
  annual_target: number
  aggregation_type: string
  prorate?: boolean
  active: boolean
  employee_count?: number
  last_modified?: string
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface RoleOption {
  value: string
  label: string
}
