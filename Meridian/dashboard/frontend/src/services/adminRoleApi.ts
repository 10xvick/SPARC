import axios from 'axios'

export interface AdminRole {
  name: string
  permissions: string[]
  is_built_in: boolean
}

export interface RoleListResponse {
  built_in: AdminRole[]
  custom: AdminRole[]
}

const BASE = '/api/admin'

export const adminRoleApi = {
  async listRoles(): Promise<RoleListResponse> {
    const response = await axios.get<RoleListResponse>(`${BASE}/roles`)
    return response.data
  },

  async listAvailablePermissions(): Promise<string[]> {
    const response = await axios.get<string[]>(`${BASE}/roles/available-permissions`)
    return response.data
  },

  async createRole(name: string, permissions: string[]): Promise<AdminRole> {
    const response = await axios.post<AdminRole>(`${BASE}/roles`, { name, permissions })
    return response.data
  },

  async updateRole(name: string, permissions: string[]): Promise<AdminRole> {
    const response = await axios.put<AdminRole>(`${BASE}/roles/${encodeURIComponent(name)}`, { permissions })
    return response.data
  },

  async deleteRole(name: string): Promise<void> {
    await axios.delete(`${BASE}/roles/${encodeURIComponent(name)}`)
  }
}
