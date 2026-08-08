export interface ComponentStatus {
  status: string
  detail: string | null
}

export interface SystemStatus {
  status: string
  version: string
  database: ComponentStatus
  configuration: ComponentStatus
  scheduler: { enabled: boolean; running: boolean; jobs: number }
  integrations: Record<string, string>
}

export interface ConnectionTestResult {
  service: string
  status: string
  detail: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) throw new Error(`请求失败：HTTP ${response.status}`)
  return response.json() as Promise<T>
}

export const api = {
  status: () => request<SystemStatus>('/status'),
  settings: () => request<Record<string, unknown>>('/settings'),
  testConnection: (service: 'bangumi' | 'qbittorrent' | 'mpv') =>
    request<ConnectionTestResult>(`/settings/test/${service}`, { method: 'POST' }),
}
