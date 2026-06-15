// API client for team dashboard
import axios from 'axios'

const API_BASE = '/api/team-dashboard'

export interface TeamProfile {
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

export interface TeamDashboardData {
  success: boolean
  team: TeamProfile
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

export interface TeamOption {
  name: string
  member_count: number
}

export const teamDashboardApi = {
  async getTeamDashboard(teamName: string, period: string = 'Annual', asOfDate: string = ''): Promise<TeamDashboardData> {
    const response = await axios.get(`${API_BASE}/by-name`, {
      params: { team_name: teamName, period, ...(asOfDate ? { as_of_date: asOfDate } : {}) }
    })
    return response.data
  },

  async listTeams(): Promise<{ success: boolean, teams: TeamOption[], total: number }> {
    const response = await axios.get(`${API_BASE}/list/teams`)
    return response.data
  }
}

export async function fetchAvailableDates(): Promise<string[]> {
  const response = await axios.get('/api/home/available-dates')
  return response.data.dates ?? []
}
