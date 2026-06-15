import axios from 'axios'

export type AuditEventType =
  | 'login'
  | 'system_admin_access'
  | 'system_admin_change'
  | 'report_access'
  | 'dashboard_access'
  | 'configuration_access'
  | 'configuration_change'

export interface AuditEvent {
  timestamp: string
  event_type: AuditEventType
  event_name: string
  sapid: string
  user_id: number | null
  user_name: string
  role: string
  success: boolean | null
  failure_reason: string
  ip_address: string
  user_agent: string
  details?: Record<string, unknown> | null
}

export interface AuditDailyPoint {
  date: string
  count: number
  successful: number
  failed: number
  admin_access: number
  admin_change: number
  report_access: number
  dashboard_access: number
  configuration_access: number
  configuration_change: number
}

export interface AuditTopUser {
  sapid: string
  name: string
  count: number
  successful: number
  failed: number
  admin_changes: number
}

export interface AuditTrailResponse {
  data: AuditEvent[]
  total_filtered: number
  summary: {
    total_events: number
    total_logins: number
    successful_logins: number
    failed_logins: number
    admin_access_events: number
    admin_change_events: number
    report_access_events: number
    dashboard_access_events: number
    configuration_access_events: number
    configuration_change_events: number
    unique_users: number
    unique_targets: number
    last_event_at: string | null
    by_day: AuditDailyPoint[]
    top_users: AuditTopUser[]
  }
  filters: {
    sapids: string[]
    roles: string[]
    event_types: AuditEventType[]
  }
}

export interface AuditTrailQuery {
  event_type?: 'all' | AuditEventType
  sapid?: string
  role?: string
  success?: boolean
  search?: string
  start_date?: string
  end_date?: string
  offset?: number
  limit?: number
}

const BASE = '/api/audit-trail'

export const auditTrailApi = {
  async listEvents(query: AuditTrailQuery): Promise<AuditTrailResponse> {
    const response = await axios.get<AuditTrailResponse>(`${BASE}/events`, {
      params: query
    })
    return response.data
  }
}
