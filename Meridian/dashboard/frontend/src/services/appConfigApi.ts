import axios from 'axios'

export interface AppConfigResponse {
  app_name: string
  version: string
  features?: Record<string, boolean>
}

export const appConfigApi = {
  async getConfig(): Promise<AppConfigResponse> {
    const response = await axios.get<AppConfigResponse>('/api/config')
    return response.data
  }
}
