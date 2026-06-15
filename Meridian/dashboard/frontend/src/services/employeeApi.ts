// API client for employee management
import axios from 'axios'
import type { Employee, PaginatedResponse, RoleOption } from '../types'

const API_BASE = '/api/employees'

export const employeeApi = {
  async getEmployees(params: {
    team?: string
    scrum?: string
    primary_role?: string
    secondary_role?: string
    search?: string
    include_inactive?: boolean
    page?: number
    page_size?: number
  }): Promise<PaginatedResponse<Employee>> {
    const response = await axios.get(API_BASE, { params })
    return response.data
  },

  async getEmployee(sapid: string): Promise<Employee> {
    const response = await axios.get(`${API_BASE}/${sapid}`)
    return response.data
  },

  async getTeams(): Promise<string[]> {
    const response = await axios.get(`${API_BASE}/options/teams`)
    return response.data.teams
  },

  async getScrums(): Promise<string[]> {
    const response = await axios.get(`${API_BASE}/options/scrums`)
    return response.data.scrums
  },

  async getRoleOptions(): Promise<{ primary_roles: RoleOption[], secondary_roles: RoleOption[] }> {
    const response = await axios.get(`${API_BASE}/options/roles`)
    return response.data
  },

  async getManagerOptions(): Promise<RoleOption[]> {
    const response = await axios.get(`${API_BASE}/options/managers`)
    return response.data.managers
  },

  async updateEmployee(sapid: string, updates: Partial<Employee>): Promise<{ success: boolean, message: string, data: Employee }> {
    const response = await axios.put(`${API_BASE}/${sapid}`, updates)
    return response.data
  },

  async addEmployee(employee: Partial<Employee>): Promise<{
    success: boolean
    message: string
    data: Employee
    rbac_user_created?: boolean
    rbac_default_password?: string | null
    rbac_email_notification_status?: 'sent' | 'skipped' | 'failed' | null
    rbac_email_notification_message?: string | null
  }> {
    const response = await axios.post(API_BASE, employee)
    return response.data
  },

  async updateEmployeeStatus(sapid: string, status: 'Active' | 'Inactive'): Promise<{ success: boolean, message: string, data: Employee }> {
    const response = await axios.put(`${API_BASE}/${sapid}/status`, { status })
    return response.data
  },

  async deleteEmployee(sapid: string): Promise<{ success: boolean, message: string }> {
    const response = await axios.delete(`${API_BASE}/${sapid}`)
    return response.data
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
