import axios from 'axios'

const BASE = '/api/admin/notifications'

export interface MailConfig {
  enabled: boolean
  smtp_host: string
  smtp_port: number
  use_tls: boolean
  from_address: string
  timeout_seconds: number
}

export const adminNotificationApi = {
  async getMailConfig(): Promise<MailConfig> {
    const response = await axios.get<MailConfig>(`${BASE}/mail-config`)
    return response.data
  },

  async updateMailConfig(payload: Partial<MailConfig>): Promise<MailConfig> {
    const response = await axios.put<MailConfig>(`${BASE}/mail-config`, payload)
    return response.data
  },

  async sendCredentialsEmail(payload: {
    user_sapid: string
    password: string
    mode: 'create' | 'reset'
    dashboard_url?: string
  }): Promise<{ status: string; message: string }> {
    const response = await axios.post<{ status: string; message: string }>(
      `${BASE}/send-credentials-email`,
      payload
    )
    return response.data
  }
}
