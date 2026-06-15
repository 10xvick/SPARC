import axios from 'axios'

export interface AdminUser {
  id: number
  sapid: string
  name: string
  email: string | null
  role: string
  is_active: boolean
  team_ids: string[]
  managed_user_ids: number[]
  source: string
  last_login: string | null
  created_at: string
  updated_at: string
}

export interface AdminUserPayload {
  sapid: string
  name: string
  email?: string | null
  role: string
  password: string
  is_active?: boolean
  team_ids?: string[]
  managed_user_ids?: number[]
  source?: string
}

export interface UserSyncResult {
  created: number
  updated: number
  errors: string[]
}

export interface UserEmailNotificationResult {
  email_notification_status?: 'sent' | 'skipped' | 'failed'
  email_notification_message?: string | null
}

const BASE = '/api/admin'

export const adminUserApi = {
  async listUsers(): Promise<AdminUser[]> {
    const response = await axios.get<AdminUser[]>(`${BASE}/users`)
    return response.data
  },

  async createUser(payload: AdminUserPayload): Promise<{ user: AdminUser } & UserEmailNotificationResult> {
    const response = await axios.post<{ user: AdminUser } & UserEmailNotificationResult>(`${BASE}/users`, payload)
    return response.data
  },

  async updateUser(id: number, payload: Partial<AdminUserPayload>): Promise<AdminUser> {
    const response = await axios.put<AdminUser>(`${BASE}/users/${id}`, payload)
    return response.data
  },

  async deleteUser(id: number): Promise<void> {
    await axios.delete(`${BASE}/users/${id}`)
  },

  async resetPassword(id: number): Promise<{
    new_password: string
    user_email: string | null
    user_name: string | null
    user_sapid: string | null
    email_notification_status?: 'sent' | 'skipped' | 'failed'
    email_notification_message?: string | null
  }> {
    const response = await axios.post<{
      new_password: string
      user_email: string | null
      user_name: string | null
      user_sapid: string | null
      email_notification_status?: 'sent' | 'skipped' | 'failed'
      email_notification_message?: string | null
    }>(`${BASE}/users/${id}/reset-password`)
    return response.data
  },

  async syncFromResources(): Promise<UserSyncResult> {
    const response = await axios.post<UserSyncResult>(`${BASE}/users-sync`)
    return response.data
  }
}
