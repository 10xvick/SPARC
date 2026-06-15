// API client for scrum dashboard
import axios from 'axios'

const API_BASE = '/api/scrum-dashboard'

export interface ScrumProfile {
  name: string
  member_count: number
  members: string[]
}

export interface KPIPerformance {
  kpi_id: string
  kpi_name: string
  category: string
  goal_type: string
  actual: number | null
  target: number
  prorated_target?: number
  period?: string
  prorate?: boolean
  rog_status: string
  percentage: number | null
  member_count?: number
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

export interface ScrumDashboardData {
  success: boolean
  scrum: ScrumProfile
  period: string
  category_status: {
    input: CategoryStatus
    output: CategoryStatus
    quality: CategoryStatus
    hygiene: CategoryStatus
  }
  kpi_performance: KPIPerformance[]
  total_kpis: number
}

export interface ScrumOption {
  name: string
  member_count: number
}

export const scrumDashboardApi = {
  async getScrumDashboard(scrumName: string, period: string = 'Annual', asOfDate: string = ''): Promise<ScrumDashboardData> {
    const response = await axios.get(`${API_BASE}/${encodeURIComponent(scrumName)}`, {
      params: { period, ...(asOfDate ? { as_of_date: asOfDate } : {}) }
    })
    return response.data
  },

  async listScrums(): Promise<{ success: boolean, scrums: ScrumOption[], total: number }> {
    const response = await axios.get(`${API_BASE}/list/scrums`)
    return response.data
  }
}
