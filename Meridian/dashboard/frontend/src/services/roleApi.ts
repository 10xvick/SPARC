// API client for role management
import axios from 'axios'
import type { Role, PaginatedResponse } from '../types'

const API_BASE = '/api/roles'

export const roleApi = {
  async getRoles(params: {
    primary_role?: string
    secondary_role?: string
    goal_type?: string
    active?: boolean
    search?: string
    page?: number
    page_size?: number
    sort_by?: string
    sort_order?: string
  }): Promise<PaginatedResponse<Role>> {
    const response = await axios.get(API_BASE, { params })
    return response.data
  },

  async getRole(index: string): Promise<Role> {
    const response = await axios.get(`${API_BASE}/${index}`)
    return response.data
  },

  async updateTargets(index: string, data: {
    weekly_target: number
    quarterly_target: number
    annual_target: number
  }): Promise<{ success: boolean, message: string, data: Role }> {
    const response = await axios.put(`${API_BASE}/${index}/targets`, data)
    return response.data
  },

  async getGoalTypes(): Promise<string[]> {
    const response = await axios.get(`${API_BASE}/options/goal-types`)
    return response.data.goal_types
  },

  async getPrimaryRoles(): Promise<string[]> {
    const response = await axios.get(`${API_BASE}/options/primary-roles`)
    return response.data.primary_roles
  },

  async getAggregationTypes(): Promise<string[]> {
    const response = await axios.get(`${API_BASE}/options/aggregation-types`)
    return response.data.aggregation_types
  },

  async exportCSV(): Promise<Blob> {
    const response = await axios.get(`${API_BASE}/export/csv`, {
      responseType: 'blob'
    })
    return response.data
  },

  async importCSV(file: File): Promise<{ success: boolean, message: string, details: { added: number, updated: number, errors: string[] } }> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await axios.post(`${API_BASE}/import/csv`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  }
}
