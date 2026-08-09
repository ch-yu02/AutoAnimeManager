<script setup lang="ts">
import type Hls from 'hls.js'
import { NCard, NSpin } from 'naive-ui'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { api, type WebPlayback } from '../api/client'

const props = defineProps<{ episodeId: number; fromStart: boolean; requestKey: number }>()
const emit = defineEmits<{ ended: [] }>()
const video = ref<HTMLVideoElement | null>(null)
const session = ref<WebPlayback | null>(null)
const loading = ref(false)
const error = ref('')
const seekPosition = ref(0)
const draggingTimeline = ref(false)
let hls: Hls | null = null
let lastSavedAt = 0
let startGeneration = 0
const duration = computed(() => session.value?.duration_seconds || 0)

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return '--:--'
  const whole = Math.floor(seconds)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const remainder = whole % 60
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`
    : `${minutes}:${String(remainder).padStart(2, '0')}`
}

async function saveProgress(ended = false) {
  const current = session.value
  const element = video.value
  if (!current || !element) return
  try {
    await api.saveWebProgress(
      current.session_id,
      Number.isFinite(element.currentTime) ? element.currentTime : 0,
      Number.isFinite(element.duration) ? element.duration : null,
      ended,
    )
  } catch { /* A replaced/closed stream no longer needs progress updates. */ }
}

async function closeSession() {
  const current = session.value
  if (current) {
    await saveProgress().catch(() => undefined)
    session.value = null
  }
  hls?.destroy()
  hls = null
  if (current) await api.stopWebPlayback(current.session_id).catch(() => undefined)
}

async function start(positionSeconds?: number) {
  const generation = ++startGeneration
  loading.value = true
  error.value = ''
  await closeSession()
  try {
    const created = await api.startWebPlayback(props.episodeId, props.fromStart, positionSeconds)
    if (generation !== startGeneration) {
      await api.stopWebPlayback(created.session_id).catch(() => undefined)
      return
    }
    session.value = created
    seekPosition.value = created.initial_position_seconds
    await nextTick()
    const element = video.value
    if (!element) return
    const HlsClass = (await import('hls.js')).default
    if (HlsClass.isSupported()) {
      hls = new HlsClass({ enableWorker: true, backBufferLength: 60 })
      hls.loadSource(created.playlist_url)
      hls.attachMedia(element)
      hls.on(HlsClass.Events.MANIFEST_PARSED, () => {
        element.currentTime = created.initial_position_seconds
        element.play().catch(() => undefined)
      })
      hls.on(HlsClass.Events.ERROR, (_event, data) => {
        if (data.fatal) error.value = `网页播放器错误：${data.details}`
      })
    } else if (element.canPlayType('application/vnd.apple.mpegurl')) {
      element.addEventListener('loadedmetadata', () => {
        element.currentTime = created.initial_position_seconds
        element.play().catch(() => undefined)
      }, { once: true })
      element.src = created.playlist_url
    } else {
      throw new Error('当前浏览器不支持 HLS 播放')
    }
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '创建网页播放流失败'
  } finally {
    if (generation === startGeneration) loading.value = false
  }
}

function onTimeUpdate() {
  if (!draggingTimeline.value && session.value && video.value) {
    seekPosition.value = Math.min(
      duration.value || Number.POSITIVE_INFINITY,
      video.value.currentTime,
    )
  }
  const now = Date.now()
  if (now - lastSavedAt >= 10_000) {
    lastSavedAt = now
    void saveProgress()
  }
}

function onSeekInput(event: Event) {
  draggingTimeline.value = true
  seekPosition.value = Number((event.target as HTMLInputElement).value)
}

async function commitSeek(event: Event) {
  const target = Number((event.target as HTMLInputElement).value)
  draggingTimeline.value = false
  if (video.value) video.value.currentTime = target
}

async function onEnded() {
  await saveProgress(true)
  emit('ended')
}

watch(() => props.requestKey, () => { void start() }, { immediate: true })
onBeforeUnmount(() => { startGeneration += 1; void closeSession() })
</script>

<template>
  <NCard title="网页播放器" class="web-player-card">
    <NSpin :show="loading">
      <p v-if="loading" class="transcode-message">正在完成整集转码，完成后开始播放……</p>
      <p v-if="error" class="error">{{ error }}</p>
      <video
        ref="video"
        class="web-player"
        controls
        playsinline
        @timeupdate="onTimeUpdate"
        @pause="saveProgress()"
        @ended="onEnded"
      />
      <div v-if="duration" class="full-timeline">
        <input
          :value="seekPosition"
          type="range"
          min="0"
          :max="duration"
          step="1"
          aria-label="整集播放位置"
          :disabled="loading"
          @input="onSeekInput"
          @change="commitSeek"
        />
        <span>{{ formatTime(seekPosition) }} / {{ formatTime(duration) }}</span>
      </div>
      <small v-if="duration" class="timeline-hint">整集已转码完成，可在完整时间轴内任意前后跳转。</small>
    </NSpin>
  </NCard>
</template>

<style scoped>
.web-player-card {
  margin-top: 16px;
}

.web-player {
  aspect-ratio: 16 / 9;
  background: #000;
  display: block;
  width: 100%;
}

.full-timeline {
  align-items: center;
  display: grid;
  gap: 12px;
  grid-template-columns: minmax(0, 1fr) auto;
  margin-top: 10px;
}

.full-timeline input {
  cursor: pointer;
  margin: 0;
  width: 100%;
}

.full-timeline span,
.timeline-hint {
  color: var(--muted);
  font-size: 12px;
}

.transcode-message {
  color: var(--muted);
  margin: 0;
  text-align: center;
}
</style>
