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
  storage?: { library_roots?: string[]; library_path?: string }
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
  collection_updated_at: string | null
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
  local_status: string
  media_files: Array<{ id: number; path: string; exists: boolean; primary: boolean; locked: boolean }>
  playback: PlaybackStateView | null
  last_synced_at: string | null
}

export interface PlaybackStateView {
  episode_id?: number
  media_file_id?: number | null
  position_seconds: number
  duration_seconds: number | null
  progress_ratio: number
  watched: boolean
  watched_source: string | null
  last_played_at: string | null
  completed_at?: string | null
}

export interface CurrentPlayback {
  status: 'IDLE' | 'PLAYING' | 'PAUSED'
  episode_id: number | null
  media_file_id?: number
  path?: string
  position_seconds?: number
  duration_seconds?: number | null
  progress_ratio?: number
  has_next?: boolean
}

export interface WebPlayback {
  session_id: string
  episode_id: number
  media_file_id: number
  playlist_url: string
  start_seconds: number
  initial_position_seconds: number
  duration_seconds: number | null
}

export interface ContinueWatching extends PlaybackStateView {
  episode_id: number
  episode: { id: number; subject_id: number; display_number: string; name: string }
  subject: { id: number; name: string; image_url: string }
  media: { id: number; path: string; exists: boolean } | null
  playable: boolean
}

export interface MediaFileView {
  id: number
  path: string
  filename: string
  file_size: number
  partial_hash: string | null
  full_hash: string | null
  hardlink_paths: string[]
  duration_seconds: number | null
  video_codec: string | null
  resolution: string | null
  exists: boolean
  ignored: boolean
  review_reason: string | null
  parse_result: Record<string, unknown>
  subject: { id: number; name: string } | null
  subject_mapping_source: string | null
  subject_confidence: number | null
  subject_reasons: string[]
  locked: boolean
  episodes: Array<{ id: number; display_number: string; type: string; name: string; source: string; confidence: number; primary: boolean; locked: boolean; reasons: string[] }>
}

export interface ReviewQueue {
  needs_review: MediaFileView[]
  automatic: MediaFileView[]
  manually_linked: MediaFileView[]
  duplicates: MediaFileView[]
  locked: MediaFileView[]
  ignored: MediaFileView[]
  missing: MediaFileView[]
}

export interface LibraryScanStatus {
  task_id: string | null
  status: string
  discovered_count?: number
  added_count?: number
  changed_count?: number
  moved_count?: number
  missing_count?: number
  matched_count?: number
  review_count?: number
  error_summary?: string | null
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
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  status: () => request<SystemStatus>('/status'),
  settings: () => request<Record<string, unknown>>('/settings'),
  updateSettings: (payload: { bangumi_username?: string; bangumi_access_token?: string; library_roots?: string[]; auto_play_next?: boolean; bangumi_writeback_enabled?: boolean }) =>
    request<PublicSettings>('/settings', {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    }),
  testConnection: (service: 'bangumi' | 'qbittorrent' | 'mpv' | 'ffmpeg') =>
    request<ConnectionTestResult>(`/settings/test/${service}`, { method: 'POST' }),
  startSync: () => request<SyncStart>('/bangumi/sync', { method: 'POST' }),
  syncStatus: (taskId?: string) => request<SyncStatus>(`/bangumi/sync/status${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''}`),
  subjects: (collectionType?: string, localOnly = false) => {
    const params = new URLSearchParams()
    if (collectionType) params.set('collection_type', collectionType)
    if (localOnly) params.set('local_only', 'true')
    return request<SubjectListItem[]>(`/subjects${params.size ? `?${params}` : ''}`)
  },
  subject: (id: number) => request<SubjectDetail>(`/subjects/${id}`),
  episodes: (id: number) => request<EpisodeView[]>(`/subjects/${id}/episodes`),
  reviewQueue: () => request<ReviewQueue>('/library/review'),
  rematchReview: () => request<{ processed_count: number; matched_count: number; review_count: number }>('/library/review/rematch', { method: 'POST' }),
  startLibraryScan: () => request<{ task_id: string; status: string; reused: boolean }>('/library/scan', { method: 'POST' }),
  libraryScanStatus: (taskId?: string) => request<LibraryScanStatus>(`/library/scan/status${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''}`),
  matchFile: (fileId: number, payload: { subject_id: number; episode_ids: number[]; primary: boolean; lock: boolean; write_manifest: boolean }) =>
    request<MediaFileView>(`/library/files/${fileId}/match`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  unlinkFile: (fileId: number) => request<MediaFileView>(`/library/files/${fileId}/match`, { method: 'DELETE' }),
  ignoreFile: (fileId: number, ignored: boolean) => request<MediaFileView>(`/library/files/${fileId}/ignore`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ignored }) }),
  reparseFile: (fileId: number) => request<{ task_id: string; status: string }>(`/library/files/${fileId}/reparse`, { method: 'POST' }),
  fullHashFile: (fileId: number) => request<MediaFileView>(`/library/files/${fileId}/full-hash`, { method: 'POST' }),
  currentPlayback: () => request<CurrentPlayback>('/playback/current'),
  continueWatching: () => request<ContinueWatching[]>('/playback/continue'),
  startPlayback: (episodeId: number, fromStart = false) => request<CurrentPlayback>('/playback/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ episode_id: episodeId, from_start: fromStart }) }),
  pausePlayback: () => request<CurrentPlayback>('/playback/pause', { method: 'POST' }),
  resumePlayback: () => request<CurrentPlayback>('/playback/resume', { method: 'POST' }),
  stopPlayback: () => request<CurrentPlayback>('/playback/stop', { method: 'POST' }),
  nextPlayback: () => request<CurrentPlayback>('/playback/next', { method: 'POST' }),
  seekPlayback: (positionSeconds: number) => request<CurrentPlayback>('/playback/seek', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ position_seconds: positionSeconds }) }),
  markWatched: (episodeId: number) => request<PlaybackStateView>(`/episodes/${episodeId}/mark-watched`, { method: 'POST' }),
  markUnwatched: (episodeId: number) => request<PlaybackStateView>(`/episodes/${episodeId}/mark-unwatched`, { method: 'POST' }),
  nextUnwatched: (subjectId: number) => request<{ episode_id: number; display_number: string; name: string; ready: boolean } | null>(`/subjects/${subjectId}/next-unwatched`),
  startWebPlayback: (episodeId: number, fromStart = false, positionSeconds?: number) => request<WebPlayback>('/playback/web/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ episode_id: episodeId, from_start: fromStart, position_seconds: positionSeconds }),
  }),
  saveWebProgress: (sessionId: string, positionSeconds: number, durationSeconds: number | null, ended = false) => request<PlaybackStateView>(`/playback/web/${sessionId}/progress`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ position_seconds: positionSeconds, duration_seconds: durationSeconds, ended }) }),
  stopWebPlayback: (sessionId: string) => request<void>(`/playback/web/${sessionId}`, { method: 'DELETE' }),
}
