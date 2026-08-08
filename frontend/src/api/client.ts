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

export interface BangumiSettings {
  username: string
  access_token: string
  base_url: string
}

export interface PublicSettings {
  bangumi: BangumiSettings
  [key: string]: unknown
}

export interface SyncStatus {
  task_id: string | null
  status: string
  started_at?: string
  finished_at?: string | null
  processed_count: number
  succeeded_count: number
  failed_count: number
  error_summary?: string | null
  reused?: boolean
}

export interface SyncStart {
  task_id: string
  status: string
  reused: boolean
}

export interface SubjectListItem {
  id: number
  bangumi_subject_id: number
  name: string
  name_cn: string
  display_name: string
  image_url: string
  subject_type: number | null
  air_date: string | null
  air_status: string
  platform: string
  collection_type: string | null
  total_main_episodes: number | null
  episode_count: number
  main_episode_count: number
  last_synced_at: string | null
}

export interface RelationView {
  subject_id: number
  bangumi_subject_id: number
  name: string
  name_cn: string
  relation_type: string
}

export interface EpisodeView {
  id: number
  bangumi_episode_id: number
  subject_id: number
  episode_type: string
  sort_number: number | null
  display_number: string
  name: string
  name_cn: string
  air_date: string | null
  bangumi_watch_status: string | null
  watched: boolean
  ignored: boolean
  last_synced_at: string | null
}

export interface SubjectDetail extends SubjectListItem {
  summary: string
  url: string
  relations: RelationView[]
  recent_sync: Record<string, unknown> | null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init)
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'object' && body.detail?.message) detail = body.detail.message
      else if (typeof body.detail === 'string') detail = body.detail
    } catch { /* keep the HTTP fallback */ }
    throw new Error(`请求失败：${detail}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  status: () => request<SystemStatus>('/status'),
  settings: () => request<Record<string, unknown>>('/settings'),
  updateSettings: (payload: { bangumi_username?: string; bangumi_access_token?: string }) =>
    request<PublicSettings>('/settings', {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    }),
  testConnection: (service: 'bangumi' | 'qbittorrent' | 'mpv') =>
    request<ConnectionTestResult>(`/settings/test/${service}`, { method: 'POST' }),
  startSync: () => request<SyncStart>('/bangumi/sync', { method: 'POST' }),
  syncStatus: (taskId?: string) => request<SyncStatus>(`/bangumi/sync/status${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''}`),
  subjects: (collectionType?: string) => request<SubjectListItem[]>(`/subjects${collectionType ? `?collection_type=${encodeURIComponent(collectionType)}` : ''}`),
  subject: (id: number) => request<SubjectDetail>(`/subjects/${id}`),
  episodes: (id: number) => request<EpisodeView[]>(`/subjects/${id}/episodes`),
}
