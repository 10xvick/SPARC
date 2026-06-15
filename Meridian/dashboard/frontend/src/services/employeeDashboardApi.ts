// API client for employee dashboard
import axios from 'axios'

const API_BASE = '/api/employee-dashboard'

export interface EmployeeProfile {
  Name: string
  SAPID: string
  Team: string
  Scrum: string
  'Primary Role': string
  'Secondary Role': string
  Manager: string
  'Manager Name': string
  [key: string]: any
}

export interface KPIPerformance {
  kpi_id: string
  kpi_name: string
  category: string
  goal_type: string
  role_type: string
  actual: number | null
  target: number
  prorated_target?: number
  period?: string
  prorate?: boolean
  rog_status: string
  percentage: number | null
  excluded_from_score?: boolean
  configuration_status?: string
  measurement_criteria?: string
  tool?: string
  measure?: string
}

export interface CategoryStatus {
  status: string
  green_count: number
  orange_count: number
  red_count: number
  total_count: number
  not_configured_count?: number
}

export interface DashboardTickerMessage {
  id: string
  text: string
  severity: 'critical' | 'high' | 'low' | 'warning' | 'info' | 'compliance'
  scope: 'all' | 'team' | 'scrum' | 'employee'
  target_values: string[]
  kpi_red_ids: string[]
  validity_days: number
  expires_at: string | null
}

export interface EmployeeDashboardData {
  success: boolean
  inactive?: boolean
  message?: string
  employee: EmployeeProfile
  employee_start_date?: string
  period: string
  category_status: {
    input: CategoryStatus
    output: CategoryStatus
    quality: CategoryStatus
    hygiene: CategoryStatus
  }
  kpi_performance: KPIPerformance[]
  total_kpis: number
  ticker_messages?: DashboardTickerMessage[]
}

export interface EmployeeOption {
  name: string
  sapid: string
  team: string
  role: string
}

export interface AssignedTask {
  key: string
  summary: string
  status: string
  priority: string
  issue_type: string
  due_date: string
  is_delayed: boolean
  days_delayed: number | null
}

export interface AssignedTasksResponse {
  success: boolean
  tasks: AssignedTask[]
  total: number
  message?: string
  employee_name?: string
}

export const employeeDashboardApi = {
  async getEmployeeDashboard(employeeIdentifier: string, period: string = 'Annual', asOfDate: string = ''): Promise<EmployeeDashboardData> {
    const response = await axios.get(`${API_BASE}/${encodeURIComponent(employeeIdentifier)}`, {
      params: { period, ...(asOfDate ? { as_of_date: asOfDate } : {}) }
    })
    return response.data
  },

  async listEmployees(): Promise<{ success: boolean, employees: EmployeeOption[], total: number }> {
    const response = await axios.get(`${API_BASE}/list/employees`)
    return response.data
  },

  async getAssignedTasks(employeeIdentifier: string): Promise<AssignedTasksResponse> {
    const response = await axios.get(`${API_BASE}/${encodeURIComponent(employeeIdentifier)}/assigned-tasks`)
    return response.data
  }
}
